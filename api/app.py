"""
Flask приложение для TradingView-style платформы.

Endpoints:
- / - Watchlist (главная страница)
- /strategy/<id> - Детальная страница стратегии
- /screener - Скринер сигналов
- /analytics - Аналитика и сравнение
- /positions - Активные позиции
- /history - История сделок

API Blueprints:
- /api/live/* - Live trading
- /api/paper/* - Paper trading
- /api/analytics/* - Аналитика
- /api/strategies/* - CRUD стратегий
"""
import logging
from pathlib import Path

from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO
from flask_cors import CORS

# Настройка путей
PROJECT_ROOT = Path(__file__).parent.parent
TEMPLATE_FOLDER = PROJECT_ROOT / "frontend" / "templates"
STATIC_FOLDER = PROJECT_ROOT / "frontend" / "static"

# Создание приложения
app = Flask(__name__,
            template_folder=str(TEMPLATE_FOLDER),
            static_folder=str(STATIC_FOLDER),
            static_url_path='/static')

# Конфигурация
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'change-me-in-production')
app.config['JSON_AS_ASCII'] = False

# CORS для разработки
CORS(app)

# SocketIO
socketio = SocketIO(app,
                    cors_allowed_origins="*",
                    async_mode='eventlet',
                    logger=True,
                    engineio_logger=False)

# Логирование
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# Импорт PriceService
import sys
sys.path.insert(0, str(PROJECT_ROOT))
from core.price_service import get_price_service


# ============================================================
# Routes (HTML страницы)
# ============================================================

@app.route('/')
def index():
    """Главная страница - редирект на BTC watchlist."""
    from flask import redirect
    return redirect('/watchlist/btc')


@app.route('/watchlist/<symbol>')
def watchlist_symbol(symbol):
    """Watchlist для конкретной монеты (BTC, ETH, SOL, LTC, TON)."""
    valid_symbols = ['btc', 'eth', 'sol', 'ltc', 'ton']
    if symbol.lower() not in valid_symbols:
        return "Invalid symbol", 404

    return render_template('watchlist.html', symbol=symbol.upper())


@app.route('/strategy/<int:strategy_id>')
def strategy_detail(strategy_id):
    """Детальная страница стратегии."""
    return render_template('strategy.html', strategy_id=strategy_id)


@app.route('/screener')
def screener():
    """Скринер активных сигналов."""
    return render_template('screener.html')


@app.route('/analytics')
def analytics():
    """Аналитика и сравнение стратегий."""
    return render_template('analytics.html')


@app.route('/positions')
def positions():
    """Активные позиции."""
    return render_template('positions.html')


@app.route('/history')
def history():
    """История сделок."""
    return render_template('history.html')


@app.route('/strategies')
def strategies_catalog():
    """Каталог всех стратегий."""
    return render_template('strategies.html')


# ============================================================
# Health check
# ============================================================

@app.route('/api/positions')
def get_open_positions():
    """Получить все открытые позиции (БЕЗ расчёта PnL - это делает frontend)."""
    from core.database import get_database

    db = get_database()

    # Получить все открытые позиции
    positions = db.conn.execute("""
        SELECT
            t.id, t.strategy_id, t.symbol, t.side, t.direction,
            t.qty, t.entry_price, t.sl_price, t.opened_at, t.fees,
            s.name as strategy_name, s.timeframe, s.type as strategy_type
        FROM trades t
        JOIN strategies s ON t.strategy_id = s.id
        WHERE t.status = 'open'
        ORDER BY t.opened_at DESC
    """).fetchall()

    if not positions:
        return jsonify({
            'status': 'ok',
            'total': 0,
            'long_count': 0,
            'short_count': 0,
            'positions': []
        })

    # Просто преобразовать в список (БЕЗ расчёта PnL)
    positions_list = []

    for p in positions:
        positions_list.append({
            'id': p['id'],
            'strategy_id': p['strategy_id'],
            'strategy_name': p['strategy_name'],
            'strategy_type': p['strategy_type'],
            'timeframe': p['timeframe'],
            'symbol': p['symbol'],
            'side': p['side'],
            'direction': p['direction'],
            'qty': p['qty'],
            'entry_price': p['entry_price'],
            'sl_price': p['sl_price'],
            'opened_at': p['opened_at'],
            'fees': p['fees'],
        })

    # Подсчитать статистику
    long_count = sum(1 for p in positions_list if p['direction'] == 'long')
    short_count = sum(1 for p in positions_list if p['direction'] == 'short')

    return jsonify({
        'status': 'ok',
        'total': len(positions_list),
        'long_count': long_count,
        'short_count': short_count,
        'positions': positions_list
    })


@app.route('/api/health')
def health():
    """Health check endpoint."""
    return jsonify({
        'status': 'ok',
        'service': 'trading-platform',
        'version': '1.0.0'
    })


@app.route('/api/prices')
def get_live_prices():
    """Получить текущие цены с PriceService (легковесный endpoint)."""
    price_service = get_price_service()

    # Получить все цены
    all_prices = price_service.get_all_prices()

    # Преобразовать в удобный формат для frontend
    prices = {}
    for symbol, data in all_prices.items():
        # Убрать /USDT suffix для удобства
        coin = symbol.replace('/USDT', '').replace('USDT', '')
        prices[coin] = {
            'price': data['price'],
            'exchange': data['exchange'],
            'timestamp': data['timestamp']
        }

    return jsonify({
        'status': 'ok',
        'prices': prices,
        'exchanges_status': price_service.get_exchanges_status()
    })


@app.route('/api/strategies/counts')
def get_strategy_counts():
    """Получить количество стратегий по монетам для sidebar."""
    from core.database import get_database

    db = get_database()
    rows = db.conn.execute("""
        SELECT
            CASE
                WHEN symbol LIKE 'BTC%' THEN 'BTC'
                WHEN symbol LIKE 'ETH%' THEN 'ETH'
                WHEN symbol LIKE 'SOL%' THEN 'SOL'
                WHEN symbol LIKE 'LTC%' THEN 'LTC'
                WHEN symbol LIKE 'TON%' THEN 'TON'
                ELSE 'OTHER'
            END as coin,
            COUNT(*) as count
        FROM strategies
        GROUP BY coin
    """).fetchall()

    counts = {row['coin']: row['count'] for row in rows}
    return jsonify({'status': 'ok', 'counts': counts})


@app.route('/api/strategies/all')
def get_all_strategies():
    """Получить ВСЕ стратегии из БД (110+ стратегий)."""
    from core.database import get_database
    from datetime import datetime, timedelta

    db = get_database()
    strategies = db.get_all_strategies()

    # Преобразовать в формат для фронтенда
    strategies_list = []
    for s in strategies:
        strategy_id = s['id']

        # Получить все сделки этой стратегии
        trades = db.conn.execute("""
            SELECT pnl, closed_at
            FROM trades
            WHERE strategy_id = ? AND status = 'closed'
        """, (strategy_id,)).fetchall()

        # Рассчитать статистику
        total_pnl = sum(t['pnl'] if t['pnl'] is not None else 0 for t in trades)
        trades_count = len(trades)

        # Также посчитать открытые сделки
        open_count = db.conn.execute("""
            SELECT COUNT(*) FROM trades
            WHERE strategy_id = ? AND status = 'open'
        """, (strategy_id,)).fetchone()[0]

        # PnL за последние 24 часа
        cutoff_time = datetime.now() - timedelta(hours=24)
        pnl_24h = sum(t['pnl'] for t in trades
                      if t['closed_at'] and datetime.fromisoformat(t['closed_at']) > cutoff_time)

        # Win Rate
        win_count = sum(1 for t in trades if t['pnl'] and t['pnl'] > 0)
        win_rate = (win_count / trades_count * 100) if trades_count > 0 else 0

        # Баланс = начальный (1000) + сумма всех закрытых PnL
        INITIAL_BALANCE = 1000.0
        current_balance = INITIAL_BALANCE + total_pnl

        strategies_list.append({
            'id': s['id'],
            'name': s['name'],
            'type': s['type'],
            'category': s['category'],
            'symbol': s.get('symbol', 'BTC/USDT:USDT'),
            'timeframe': s['timeframe'],
            'direction': s['direction'],
            'leverage': s['leverage'],
            'status': s['status'],
            'params': s['params'],
            'initial_balance': INITIAL_BALANCE,
            'current_balance': current_balance,
            'pnl_24h': pnl_24h,
            'total_pnl': total_pnl,
            'win_rate': win_rate,
            'trades_count': trades_count,
            'open_trades': open_count,
        })

    return jsonify({
        'status': 'ok',
        'count': len(strategies_list),
        'strategies': strategies_list
    })


@app.route('/api/strategies/start-all', methods=['POST'])
def start_all_strategies():
    """Запустить ВСЕ стратегии (массовый запуск)."""
    from core.database import get_database
    from flask import request

    db = get_database()

    # Получить параметры (опционально - фильтр по символу)
    data = request.get_json() or {}
    symbol = data.get('symbol')  # 'BTC', 'ETH', и т.д.

    # Получить все stopped стратегии
    all_strategies = db.get_strategies_by_status('stopped')

    # Фильтровать по символу если указан
    if symbol:
        # TODO: добавить поле symbol в таблицу strategies
        pass

    # Обновить статус на 'running'
    started_count = 0
    for strategy in all_strategies:
        db.update_strategy_status(strategy['id'], 'running')
        started_count += 1

    logger.info(f"Started {started_count} strategies")

    return jsonify({
        'status': 'ok',
        'message': f'Started {started_count} strategies',
        'count': started_count
    })


@app.route('/api/strategies/stop-all', methods=['POST'])
def stop_all_strategies():
    """Остановить ВСЕ стратегии (массовая остановка)."""
    from core.database import get_database

    db = get_database()

    # Получить все running стратегии
    all_strategies = db.get_strategies_by_status('running')

    # Обновить статус на 'stopped'
    stopped_count = 0
    for strategy in all_strategies:
        db.update_strategy_status(strategy['id'], 'stopped')
        stopped_count += 1

    logger.info(f"Stopped {stopped_count} strategies")

    return jsonify({
        'status': 'ok',
        'message': f'Stopped {stopped_count} strategies',
        'count': stopped_count
    })


# ============================================================
# Регистрация Blueprints
# ============================================================

def register_blueprints():
    """Регистрация всех API blueprints."""
    import sys
    sys.path.insert(0, str(PROJECT_ROOT))

    try:
        from api.live import live_bp
        app.register_blueprint(live_bp, url_prefix='/api/live')
        logger.info("✓ Registered blueprint: /api/live")
    except ImportError as e:
        logger.warning(f"Could not register live_bp: {e}")

    try:
        from api.paper import paper_bp
        app.register_blueprint(paper_bp, url_prefix='/api/paper')
        logger.info("✓ Registered blueprint: /api/paper")
    except ImportError as e:
        logger.warning(f"Could not register paper_bp: {e}")

    try:
        from api.analytics import analytics_bp
        app.register_blueprint(analytics_bp, url_prefix='/api/analytics')
        logger.info("✓ Registered blueprint: /api/analytics")
    except ImportError as e:
        logger.warning(f"Could not register analytics_bp: {e}")


# ============================================================
# WebSocket handlers
# ============================================================

def init_websocket():
    """Инициализация WebSocket обработчиков."""
    import sys
    sys.path.insert(0, str(PROJECT_ROOT))

    try:
        from api.websocket import init_websocket_handlers
        init_websocket_handlers(socketio, app)
        logger.info("✓ WebSocket handlers initialized")
    except ImportError as e:
        logger.warning(f"Could not initialize WebSocket: {e}")


# ============================================================
# Application factory
# ============================================================

def create_app():
    """Создать и настроить Flask приложение."""
    register_blueprints()
    init_websocket()

    # Запустить Price Service (фоновый поток для получения цен)
    price_service = get_price_service()
    price_service.start()

    logger.info("=" * 60)
    logger.info("🚀 Trading Platform API started")
    logger.info("=" * 60)
    logger.info(f"Templates: {TEMPLATE_FOLDER}")
    logger.info(f"Static: {STATIC_FOLDER}")
    logger.info("💰 Price Service: 10 exchanges, 5 coins, 1req/sec rotation")
    logger.info("=" * 60)

    return app


@app.route('/api/strategies/<int:strategy_id>')
def get_strategy_detail(strategy_id):
    """Получить детальную информацию о стратегии."""
    from core.database import get_database
    from datetime import datetime

    db = get_database()

    # Получить стратегию
    strategy = db.get_strategy(strategy_id)
    if not strategy:
        return jsonify({
            'status': 'error',
            'message': 'Strategy not found'
        }), 404

    # Получить ВСЕ сделки (без лимита - для полной статистики)
    trades = db.conn.execute("""
        SELECT id, symbol, side, direction, qty, entry_price, close_price, sl_price,
               opened_at, closed_at, close_reason, pnl, pnl_percent, fees, status
        FROM trades
        WHERE strategy_id = ?
        ORDER BY opened_at ASC
    """, (strategy_id,)).fetchall()

    # Разделить на закрытые и открытые
    closed_trades = [t for t in trades if t['status'] == 'closed']
    open_trades = [t for t in trades if t['status'] == 'open']

    # === Базовая статистика ===
    INITIAL_BALANCE = 1000.0
    total_pnl = sum(t['pnl'] or 0 for t in closed_trades)
    total_fees = sum(t['fees'] or 0 for t in closed_trades)
    current_balance = INITIAL_BALANCE + total_pnl

    win_trades = [t for t in closed_trades if (t['pnl'] or 0) > 0]
    loss_trades = [t for t in closed_trades if (t['pnl'] or 0) < 0]
    even_trades = [t for t in closed_trades if (t['pnl'] or 0) == 0]

    win_count = len(win_trades)
    loss_count = len(loss_trades)
    win_rate = (win_count / len(closed_trades) * 100) if closed_trades else 0

    # === Прибыль/Убыток ===
    gross_profit = sum(t['pnl'] for t in win_trades) if win_trades else 0
    gross_loss = sum(t['pnl'] for t in loss_trades) if loss_trades else 0
    avg_win = gross_profit / win_count if win_count > 0 else 0
    avg_loss = gross_loss / loss_count if loss_count > 0 else 0
    profit_factor = abs(gross_profit / gross_loss) if gross_loss != 0 else 0

    # === Лучшая/Худшая сделка ===
    best_trade = max((t['pnl'] or 0 for t in closed_trades), default=0)
    worst_trade = min((t['pnl'] or 0 for t in closed_trades), default=0)
    best_trade_pct = max((t['pnl_percent'] or 0 for t in closed_trades), default=0)
    worst_trade_pct = min((t['pnl_percent'] or 0 for t in closed_trades), default=0)

    # === Серии выигрышей/проигрышей ===
    max_consec_wins = 0
    max_consec_losses = 0
    current_wins = 0
    current_losses = 0
    for t in closed_trades:
        pnl = t['pnl'] or 0
        if pnl > 0:
            current_wins += 1
            current_losses = 0
            max_consec_wins = max(max_consec_wins, current_wins)
        elif pnl < 0:
            current_losses += 1
            current_wins = 0
            max_consec_losses = max(max_consec_losses, current_losses)
        else:
            current_wins = 0
            current_losses = 0

    # === Equity curve (кумулятивный PnL) ===
    equity_curve = []
    cumulative_pnl = 0
    # Добавляем начальную точку (первая сделка opened_at, начальный баланс)
    if closed_trades:
        equity_curve.append({
            'time': closed_trades[0]['opened_at'],
            'value': INITIAL_BALANCE,
            'pnl': 0
        })
    for t in closed_trades:
        cumulative_pnl += (t['pnl'] or 0)
        equity_curve.append({
            'time': t['closed_at'],
            'value': round(INITIAL_BALANCE + cumulative_pnl, 2),
            'pnl': round(cumulative_pnl, 2)
        })

    # === Max Drawdown ===
    peak = INITIAL_BALANCE
    max_drawdown = 0
    max_drawdown_pct = 0
    for point in equity_curve:
        if point['value'] > peak:
            peak = point['value']
        drawdown = peak - point['value']
        drawdown_pct = (drawdown / peak * 100) if peak > 0 else 0
        if drawdown > max_drawdown:
            max_drawdown = drawdown
            max_drawdown_pct = drawdown_pct

    # === Средняя длительность сделки ===
    durations = []
    for t in closed_trades:
        if t['opened_at'] and t['closed_at']:
            try:
                opened = datetime.fromisoformat(t['opened_at'])
                closed = datetime.fromisoformat(t['closed_at'])
                durations.append((closed - opened).total_seconds())
            except (ValueError, TypeError):
                pass
    avg_duration_sec = sum(durations) / len(durations) if durations else 0

    # Форматировать длительность
    if avg_duration_sec < 60:
        avg_duration_str = f"{avg_duration_sec:.0f}s"
    elif avg_duration_sec < 3600:
        avg_duration_str = f"{avg_duration_sec / 60:.1f}m"
    elif avg_duration_sec < 86400:
        avg_duration_str = f"{avg_duration_sec / 3600:.1f}h"
    else:
        avg_duration_str = f"{avg_duration_sec / 86400:.1f}d"

    # === Expectancy ===
    expectancy = total_pnl / len(closed_trades) if closed_trades else 0

    # === SL Hits ===
    sl_hits = sum(1 for t in closed_trades if t['close_reason'] == 'sl_hit')

    # === Sharpe Ratio (упрощённый) ===
    import math
    pnl_list = [t['pnl'] or 0 for t in closed_trades]
    if len(pnl_list) >= 2:
        mean_pnl = sum(pnl_list) / len(pnl_list)
        variance = sum((p - mean_pnl) ** 2 for p in pnl_list) / (len(pnl_list) - 1)
        std_pnl = math.sqrt(variance) if variance > 0 else 0
        sharpe_ratio = (mean_pnl / std_pnl) if std_pnl > 0 else 0
    else:
        sharpe_ratio = 0

    # Преобразовать trades в JSON-friendly формат (с кумулятивным PnL)
    trades_list = []
    cum_pnl = 0
    for t in (closed_trades + open_trades):  # Сначала закрытые (ASC), потом открытые
        if t['status'] == 'closed':
            cum_pnl += (t['pnl'] or 0)
        trades_list.append({
            'id': t['id'],
            'symbol': t['symbol'],
            'side': t['side'],
            'direction': t['direction'],
            'qty': t['qty'],
            'entry_price': t['entry_price'],
            'close_price': t['close_price'],
            'sl_price': t['sl_price'],
            'opened_at': t['opened_at'],
            'closed_at': t['closed_at'],
            'close_reason': t['close_reason'],
            'pnl': t['pnl'],
            'pnl_percent': t['pnl_percent'],
            'fees': t['fees'],
            'status': t['status'],
            'cumulative_pnl': round(cum_pnl, 4)
        })

    # Обратный порядок для отображения (новые сверху)
    trades_list.reverse()

    # Парсинг params из JSON строки
    import json as json_module
    try:
        parsed_params = json_module.loads(strategy['params']) if strategy['params'] else {}
    except (json_module.JSONDecodeError, TypeError):
        parsed_params = {}

    return jsonify({
        'status': 'ok',
        'strategy': {
            'id': strategy['id'],
            'name': strategy['name'],
            'type': strategy['type'],
            'category': strategy['category'],
            'symbol': strategy.get('symbol', 'BTC/USDT:USDT'),
            'timeframe': strategy['timeframe'],
            'direction': strategy['direction'],
            'leverage': strategy['leverage'],
            'status': strategy['status'],
            'params': parsed_params,
        },
        'statistics': {
            'initial_balance': INITIAL_BALANCE,
            'current_balance': round(current_balance, 2),
            'total_pnl': round(total_pnl, 2),
            'total_pnl_pct': round((total_pnl / INITIAL_BALANCE * 100), 2) if INITIAL_BALANCE else 0,
            'total_fees': round(total_fees, 4),
            'total_trades': len(closed_trades),
            'open_trades': len(open_trades),
            'win_count': win_count,
            'loss_count': loss_count,
            'even_count': len(even_trades),
            'win_rate': round(win_rate, 1),
            'gross_profit': round(gross_profit, 2),
            'gross_loss': round(gross_loss, 2),
            'avg_win': round(avg_win, 4),
            'avg_loss': round(avg_loss, 4),
            'best_trade': round(best_trade, 4),
            'worst_trade': round(worst_trade, 4),
            'best_trade_pct': round(best_trade_pct, 2),
            'worst_trade_pct': round(worst_trade_pct, 2),
            'profit_factor': round(profit_factor, 2),
            'expectancy': round(expectancy, 4),
            'sharpe_ratio': round(sharpe_ratio, 2),
            'max_drawdown': round(max_drawdown, 2),
            'max_drawdown_pct': round(max_drawdown_pct, 2),
            'max_consec_wins': max_consec_wins,
            'max_consec_losses': max_consec_losses,
            'avg_duration': avg_duration_str,
            'sl_hits': sl_hits,
        },
        'equity_curve': equity_curve,
        'trades': trades_list
    })


@app.route('/api/trades')
def get_all_trades():
    """Получить ВСЕ закрытые сделки (и live, и paper)."""
    from core.database import get_database
    from flask import request

    db = get_database()

    # Параметры
    limit = request.args.get('limit', 100, type=int)
    category = request.args.get('category', 'all')  # 'all', 'live', 'paper'

    # SQL запрос
    sql = """
        SELECT
            t.id, t.strategy_id, t.symbol, t.side, t.direction,
            t.qty, t.entry_price, t.close_price, t.sl_price,
            t.opened_at, t.closed_at, t.close_reason, t.pnl, t.pnl_percent, t.fees,
            s.name as strategy_name, s.timeframe, s.type as strategy_type, s.category
        FROM trades t
        JOIN strategies s ON t.strategy_id = s.id
        WHERE t.status = 'closed'
    """

    params = []
    if category != 'all':
        sql += " AND s.category = ?"
        params.append(category)

    sql += " ORDER BY t.closed_at DESC LIMIT ?"
    params.append(limit)

    trades = db.conn.execute(sql, params).fetchall()

    trades_list = []
    for t in trades:
        trades_list.append({
            'id': t['id'],
            'strategy_id': t['strategy_id'],
            'strategy_name': t['strategy_name'],
            'strategy_type': t['strategy_type'],
            'category': t['category'],
            'symbol': t['symbol'],
            'side': t['side'],
            'direction': t['direction'],
            'qty': t['qty'],
            'entry_price': t['entry_price'],
            'close_price': t['close_price'],
            'sl_price': t['sl_price'],
            'opened_at': t['opened_at'],
            'closed_at': t['closed_at'],
            'close_reason': t['close_reason'],
            'pnl': t['pnl'],
            'pnl_percent': t['pnl_percent'],
            'fees': t['fees'],
            'timeframe': t['timeframe']
        })

    return jsonify({
        'status': 'ok',
        'count': len(trades_list),
        'trades': trades_list
    })


# ============================================================
# Auto-initialize при импорте модуля
# ============================================================

# Вызвать create_app() при импорте, чтобы blueprints были зарегистрированы
create_app()

# ============================================================
# Main
# ============================================================

if __name__ == '__main__':
    socketio.run(app,
                host='0.0.0.0',
                port=5001,
                debug=True,
                use_reloader=False)  # Отключить reloader для работы с eventlet
