"""Entry point: starts the ScalperBot + Flask-SocketIO web dashboard."""

import asyncio
import logging
import os
import sys
from threading import Thread

from scalper.config import Config
from scalper.bot import ScalperBot
from scalper.storage import Storage
from scalper.web.app import create_app, socketio

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('scalper.log', encoding='utf-8'),
    ],
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Ensure data directory exists
# ---------------------------------------------------------------------------
os.makedirs('data', exist_ok=True)

# ---------------------------------------------------------------------------
# Bot runner (separate thread)
# ---------------------------------------------------------------------------

def run_bot(bot: ScalperBot):
    """Run the async bot loop in a new event loop on a daemon thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(bot.run())
    except KeyboardInterrupt:
        pass
    except Exception:
        log.error('Bot thread crashed', exc_info=True)
    finally:
        loop.close()


def main():
    config = Config.from_env()
    log.info('Config loaded: balance=%.2f, leverage=%d, port=%d',
             config.balance, config.leverage, config.web_port)

    # Shared storage instance for both bot and web
    storage = Storage()
    bot = ScalperBot(config)
    # Replace bot's internal storage with our shared one
    bot._storage = storage

    # Create Flask app
    app = create_app(bot=bot, storage=storage)

    # Start bot in daemon thread
    bot_thread = Thread(target=run_bot, args=(bot,), daemon=True)
    bot_thread.start()
    log.info('Bot thread started')

    # Start web server (main thread, use threading mode — no eventlet)
    log.info('Starting web dashboard on 0.0.0.0:%d', config.web_port)
    socketio.run(app, host='0.0.0.0', port=config.web_port, debug=False,
                 use_reloader=False, log_output=False, allow_unsafe_werkzeug=True)


if __name__ == '__main__':
    main()
