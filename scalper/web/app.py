"""Flask + SocketIO web dashboard for the scalper bot."""

import ccxt
import numpy as np
from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO
from flask_cors import CORS

socketio = SocketIO()

# Sync ccxt exchange for web API requests (separate from bot's async exchange)
_sync_exchange = None


def _get_sync_exchange(bot):
    """Get or create a sync ccxt exchange for web API calls."""
    global _sync_exchange
    if _sync_exchange is None and bot:
        _sync_exchange = ccxt.bybit({
            'apiKey': bot.cfg.bybit_api_key,
            'secret': bot.cfg.bybit_api_secret,
            'options': {'defaultType': 'swap'},
            'enableRateLimit': True,
        })
        if bot.cfg.bybit_demo:
            _sync_exchange.enable_demo_trading(True)
        _sync_exchange.load_markets()
    return _sync_exchange


def create_app(bot=None, storage=None):
    app = Flask(__name__)
    CORS(app)
    socketio.init_app(app, cors_allowed_origins="*", async_mode='threading')

    strategy_name = getattr(bot, 'strategy_name', 'default') if bot else 'default'

    @app.route('/')
    def index():
        return render_template('index.html', strategy_name=strategy_name)

    @app.route('/api/status')
    def api_status():
        if bot:
            return jsonify(bot.get_status())
        return jsonify({'running': False, 'balance': 0})

    @app.route('/api/trades')
    def api_trades():
        if storage:
            return jsonify(storage.get_trade_history(100))
        return jsonify([])

    @app.route('/api/stats/daily')
    def api_daily_stats():
        if storage:
            return jsonify(storage.get_daily_stats())
        return jsonify({})

    @app.route('/api/stats/all')
    def api_all_stats():
        if storage:
            return jsonify(storage.get_all_stats())
        return jsonify({})

    @app.route('/api/equity')
    def api_equity():
        if storage:
            return jsonify(storage.get_equity_history())
        return jsonify([])

    # ------------------------------------------------------------------
    # Trade detail page & APIs
    # ------------------------------------------------------------------

    @app.route('/trade/<int:trade_id>')
    def trade_page(trade_id):
        return render_template('trade.html', trade_id=trade_id)

    @app.route('/api/trade/<int:trade_id>/events')
    def api_trade_events(trade_id):
        """Events log for a trade."""
        if storage:
            return jsonify(storage.get_trade_events(trade_id))
        return jsonify([])

    @app.route('/api/ohlcv/<symbol_key>/<timeframe>')
    def api_ohlcv(symbol_key, timeframe):
        """Fetch OHLCV candles for charting (sync ccxt)."""
        try:
            ex = _get_sync_exchange(bot)
            if not ex:
                return jsonify({'error': 'exchange not ready'}), 503
            symbol = symbol_key.replace('-', '/', 1)
            raw = ex.fetch_ohlcv(symbol, timeframe, limit=200)
            candles = [{
                'time': int(c[0] / 1000),
                'open': c[1],
                'high': c[2],
                'low': c[3],
                'close': c[4],
                'volume': c[5],
            } for c in raw]
            return jsonify(candles)
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/position/<int:trade_id>')
    def api_position(trade_id):
        """Detailed position info including unrealized PnL."""
        if not bot:
            return jsonify({'error': 'no bot'}), 404

        status = bot.get_status()
        pos = None
        for p in status['positions']:
            if p['trade_id'] == trade_id:
                pos = p
                break

        if not pos:
            if storage:
                trades = storage.get_trade_history(100)
                for t in trades:
                    if t['id'] == trade_id:
                        return jsonify({**t, 'status': 'closed'})
            return jsonify({'error': 'not found'}), 404

        # Get current price via sync exchange
        try:
            ex = _get_sync_exchange(bot)
            ticker = ex.fetch_ticker(pos['symbol'])
            current_price = float(ticker['last'])
        except Exception:
            current_price = pos['entry_price']

        qty = pos['qty']
        entry = pos['entry_price']

        if pos['direction'] == 'long':
            pnl_gross = (current_price - entry) * qty
        else:
            pnl_gross = (entry - current_price) * qty

        entry_fee = entry * qty * bot.cfg.taker_fee
        exit_fee = current_price * qty * bot.cfg.taker_fee
        pnl_net = pnl_gross - entry_fee - exit_fee
        margin = entry * qty / bot.cfg.leverage
        pnl_pct = (pnl_net / margin) * 100 if margin else 0
        position_value = entry * qty

        return jsonify({
            **pos,
            'status': 'open',
            'current_price': current_price,
            'pnl': round(pnl_net, 4),
            'pnl_pct': round(pnl_pct, 2),
            'pnl_gross': round(pnl_gross, 4),
            'fees': round(entry_fee + exit_fee, 4),
            'margin': round(margin, 2),
            'position_value': round(position_value, 2),
            'leverage': bot.cfg.leverage,
        })

    if bot:
        def on_bot_event(event, data):
            socketio.emit(event, data)
        bot.on_update(on_bot_event)

    return app
