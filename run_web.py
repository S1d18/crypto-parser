#!/usr/bin/env python
"""
Запуск TradingView-style веб-платформы.

Usage:
    python run_web.py
    python run_web.py --port 5001
    python run_web.py --host 0.0.0.0 --port 8000
"""
import sys
from pathlib import Path

# Добавить корень проекта в PYTHONPATH
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Trading Platform Web Server')
    parser.add_argument('--host', default='0.0.0.0', help='Host (default: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=5001, help='Port (default: 5001)')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')

    args = parser.parse_args()

    # Импортировать и запустить
    from api.app import create_app, socketio

    app = create_app()

    print("\n" + "=" * 60)
    print("TradingView-style Trading Platform")
    print("=" * 60)
    print(f"Server: http://{args.host}:{args.port}")
    print(f"Watchlist: http://localhost:{args.port}/")
    print(f"API: http://localhost:{args.port}/api/health")
    print("=" * 60)
    print("Press CTRL+C to stop\n")

    socketio.run(app,
                host=args.host,
                port=args.port,
                debug=args.debug,
                use_reloader=False)
