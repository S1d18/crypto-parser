"""Multi-strategy launcher — runs strategy dashboards on dedicated ports.

Each strategy:
- Has its own signal engine
- Has its own SQLite DB (data/scalper_<name>.db)
- Has its own web dashboard on a separate port
- Shares the same Bybit API credentials

Usage:
    python run_multi.py              # launch all configured strategies
    python run_multi.py trend        # only Trend Rider on 5001
    python run_multi.py breakout     # only Breakout on 5002
    python run_multi.py reversal     # only Scalp Reversal on 5003
    python run_multi.py vwap         # only VWAP Bounce on 5004
    python run_multi.py ema_retest   # EMA Retest on 5006
    python run_multi.py donchian     # Donchian Breakout on 5007
    python run_multi.py vwap_revert  # VWAP Reversion on 5008
"""

import asyncio
import logging
import os
import sys
from copy import deepcopy
from threading import Thread

from scalper.config import Config
from scalper.bot import ScalperBot
from scalper.storage import Storage
from scalper.scanner_multi import MultiScanner
from scalper.scanner import Scanner
from scalper.signals import SignalEngine
from scalper.strategies.trend_rider import TrendRiderEngine
from scalper.strategies.breakout import BreakoutEngine
from scalper.strategies.scalp_reversal import ScalpReversalEngine
from scalper.strategies.vwap_bounce import VwapBounceEngine
from scalper.strategies.ema_retest import EmaRetestEngine
from scalper.strategies.donchian_breakout import DonchianBreakoutEngine
from scalper.strategies.vwap_reversion import VwapReversionEngine
from scalper.web.app import create_app

from flask_socketio import SocketIO

# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('scalper_multi.log', encoding='utf-8'),
    ],
)
log = logging.getLogger(__name__)

os.makedirs('data', exist_ok=True)


# ---------------------------------------------------------------------------
# Strategy definitions
# ---------------------------------------------------------------------------

STRATEGIES = {
    'trend': {
        'name': 'trend_rider',
        'label': 'Trend Rider',
        'port': 5001,
        'engine_cls': TrendRiderEngine,
        'use_trend_filter': True,
        'config_overrides': {
            'scan_interval': 15,
            'scalp_timeframe': '5m',
            'max_open_positions': 5,
        },
    },
    'breakout': {
        'name': 'breakout',
        'label': 'Breakout',
        'port': 5002,
        'engine_cls': BreakoutEngine,
        'use_trend_filter': False,
        'config_overrides': {
            'scan_interval': 10,
            'scalp_timeframe': '5m',
            'max_open_positions': 5,
        },
    },
    'reversal': {
        'name': 'scalp_reversal',
        'label': 'Scalp Reversal',
        'port': 5003,
        'engine_cls': ScalpReversalEngine,
        'use_trend_filter': False,
        'config_overrides': {
            'scan_interval': 10,
            'scalp_timeframe': '5m',
            'max_open_positions': 5,
        },
    },
    'vwap': {
        'name': 'vwap_bounce',
        'label': 'VWAP Bounce',
        'port': 5004,
        'engine_cls': VwapBounceEngine,
        'use_trend_filter': True,
        'config_overrides': {
            'scan_interval': 10,
            'scalp_timeframe': '5m',
            'max_open_positions': 5,
        },
    },
    'ema_retest': {
        'name': 'ema_retest',
        'label': 'EMA Retest',
        'port': 5006,
        'engine_cls': EmaRetestEngine,
        'use_trend_filter': True,
        'config_overrides': {
            'scan_interval': 10,
            'scalp_timeframe': '5m',
            'max_open_positions': 5,
        },
    },
    'donchian': {
        'name': 'donchian_breakout',
        'label': 'Donchian Breakout',
        'port': 5007,
        'engine_cls': DonchianBreakoutEngine,
        'use_trend_filter': False,
        'config_overrides': {
            'scan_interval': 10,
            'scalp_timeframe': '5m',
            'max_open_positions': 5,
        },
    },
    'vwap_revert': {
        'name': 'vwap_reversion',
        'label': 'VWAP Reversion',
        'port': 5008,
        'engine_cls': VwapReversionEngine,
        'use_trend_filter': False,
        'config_overrides': {
            'scan_interval': 10,
            'scalp_timeframe': '5m',
            'max_open_positions': 5,
        },
    },
}


def make_config(base_config: Config, overrides: dict) -> Config:
    """Clone config with strategy-specific overrides."""
    cfg = deepcopy(base_config)
    for k, v in overrides.items():
        if hasattr(cfg, k):
            setattr(cfg, k, v)
    return cfg


def run_bot_thread(bot: ScalperBot):
    """Run bot's async loop in a dedicated thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(bot.run())
    except KeyboardInterrupt:
        pass
    except Exception:
        log.error('Bot thread %s crashed', bot.strategy_name, exc_info=True)
    finally:
        loop.close()


def run_web_thread(app, socketio_inst, port: int, label: str):
    """Run Flask-SocketIO in a thread."""
    log.info('Starting %s dashboard on 0.0.0.0:%d', label, port)
    socketio_inst.run(app, host='0.0.0.0', port=port, debug=False,
                      use_reloader=False, log_output=False,
                      allow_unsafe_werkzeug=True)


def launch_strategy(strat_key: str, base_config: Config) -> tuple:
    """Create and launch a single strategy (bot + web).

    Each strategy can use its own Bybit sub-account API keys via env vars:
        BYBIT_API_KEY_<STRATEGY_NAME>=...
        BYBIT_API_SECRET_<STRATEGY_NAME>=...
    Falls back to the global BYBIT_API_KEY/SECRET if not set.
    """
    strat = STRATEGIES[strat_key]
    cfg = make_config(base_config, strat['config_overrides'])
    cfg.web_port = strat['port']

    # Per-strategy API keys (sub-accounts)
    env_suffix = strat['name'].upper()
    sub_key = os.getenv(f'BYBIT_API_KEY_{env_suffix}', '')
    sub_secret = os.getenv(f'BYBIT_API_SECRET_{env_suffix}', '')
    if sub_key and sub_secret:
        cfg.bybit_api_key = sub_key
        cfg.bybit_api_secret = sub_secret
        log.info('%s: using sub-account API keys', strat['label'])

    engine = strat['engine_cls']()

    from scalper.exchange import Exchange
    exchange = Exchange(cfg)

    scanner = MultiScanner(
        config=cfg,
        signal_engine=engine,
        exchange=exchange,
        use_trend_filter=strat['use_trend_filter'],
    )

    bot = ScalperBot(
        config=cfg,
        strategy_name=strat['name'],
        signal_engine=engine,
        scanner=scanner,
    )

    storage = Storage(db_path=f"data/scalper_{strat['name']}.db")
    bot._storage = storage
    bot._exchange = exchange

    sio = SocketIO()
    app = create_app(bot=bot, storage=storage)
    sio.init_app(app, cors_allowed_origins="*", async_mode='threading')

    # Start bot thread
    bot_thread = Thread(target=run_bot_thread, args=(bot,), daemon=True,
                        name=f"bot-{strat['name']}")
    bot_thread.start()

    # Start web thread
    web_thread = Thread(target=run_web_thread,
                        args=(app, sio, strat['port'], strat['label']),
                        daemon=True, name=f"web-{strat['name']}")
    web_thread.start()

    log.info('Launched %s on port %d', strat['label'], strat['port'])
    return bot_thread, web_thread


def launch_overview(selected_keys: list[str], port: int = 5000):
    """Launch overview dashboard that aggregates all strategies."""
    import json
    from flask import Flask, render_template
    from flask_cors import CORS

    strategies_info = [
        {'name': 'default', 'label': 'Sniper Original', 'port': 5000},
    ]
    for key in selected_keys:
        strat = STRATEGIES[key]
        strategies_info.append({
            'name': strat['name'],
            'label': strat['label'],
            'port': strat['port'],
        })

    app = Flask(__name__,
                template_folder='scalper/web/templates',
                static_folder='scalper/web/static')
    CORS(app)

    @app.route('/')
    def index():
        return render_template('overview.html',
                               strategies_json=json.dumps(strategies_info))

    sio = SocketIO()
    sio.init_app(app, cors_allowed_origins="*", async_mode='threading')

    web_thread = Thread(target=run_web_thread,
                        args=(app, sio, port, 'Overview'),
                        daemon=True, name='web-overview')
    web_thread.start()
    return web_thread


def launch_original(base_config: Config, port: int = 5000) -> tuple:
    """Launch the original Sniper bot on given port."""
    cfg = deepcopy(base_config)
    cfg.web_port = port

    # Per-strategy API keys (sub-accounts)
    sub_key = os.getenv('BYBIT_API_KEY_DEFAULT', '')
    sub_secret = os.getenv('BYBIT_API_SECRET_DEFAULT', '')
    if sub_key and sub_secret:
        cfg.bybit_api_key = sub_key
        cfg.bybit_api_secret = sub_secret
        log.info('Sniper Original: using sub-account API keys')

    bot = ScalperBot(
        config=cfg,
        strategy_name='default',
    )

    # Use the original DB so it picks up existing positions
    storage = Storage(db_path='data/scalper.db')
    bot._storage = storage

    sio = SocketIO()
    app = create_app(bot=bot, storage=storage)
    sio.init_app(app, cors_allowed_origins="*", async_mode='threading')

    bot_thread = Thread(target=run_bot_thread, args=(bot,), daemon=True,
                        name='bot-original')
    bot_thread.start()

    web_thread = Thread(target=run_web_thread,
                        args=(app, sio, port, 'Sniper Original'),
                        daemon=True, name='web-original')
    web_thread.start()

    log.info('Launched Sniper Original on port %d', port)
    return bot_thread, web_thread


def main():
    base_config = Config.from_env()
    log.info('Base config: balance=%.2f, leverage=%d', base_config.balance, base_config.leverage)

    # Parse args
    selected = sys.argv[1:] if len(sys.argv) > 1 else list(STRATEGIES.keys())

    # Validate
    for s in selected:
        if s not in STRATEGIES:
            print(f"Unknown strategy: {s}")
            print(f"Available: {', '.join(STRATEGIES.keys())}")
            sys.exit(1)

    threads = []
    print()
    print("=" * 60)
    print("  MULTI-STRATEGY LAUNCHER")
    print("=" * 60)

    # Launch original Sniper on 5000
    bt, wt = launch_original(base_config, port=5000)
    threads.extend([bt, wt])
    print(f"  {'Sniper (original)':20s} -> http://localhost:5000")

    for key in selected:
        strat = STRATEGIES[key]
        bt, wt = launch_strategy(key, base_config)
        threads.extend([bt, wt])
        print(f"  {strat['label']:20s} -> http://localhost:{strat['port']}")

    # Launch overview dashboard on 5005
    ov_thread = launch_overview(selected, port=5005)
    threads.append(ov_thread)

    print(f"  {'Overview':20s} -> http://localhost:5005")
    print("=" * 60)
    print()

    # Keep main thread alive
    try:
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        log.info('Shutting down all strategies...')
        print('\nShutting down...')


if __name__ == '__main__':
    main()
