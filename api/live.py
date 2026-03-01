"""
API для Live Trading.

Endpoints:
- GET /api/live/status - статус бота и открытые позиции
- GET /api/live/statistics - статистика сделок
- GET /api/live/trades - история сделок
"""
from flask import Blueprint, jsonify, request
from core.storage import TradeStorage

live_bp = Blueprint('live', __name__)


@live_bp.route('/status')
def get_status():
    """Получить статус live бота и открытые позиции."""
    try:
        storage = TradeStorage()
        open_trades = storage.get_open_trades()

        # TODO: Проверить что bot процесс запущен
        bot_running = False  # Временно

        return jsonify({
            'status': 'ok',
            'bot_running': bot_running,
            'positions': open_trades,
            'positions_count': len(open_trades)
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@live_bp.route('/statistics')
def get_statistics():
    """Получить статистику сделок."""
    try:
        storage = TradeStorage()
        timeframe = request.args.get('timeframe')  # опционально

        stats = storage.get_statistics(timeframe)

        return jsonify({
            'status': 'ok',
            'statistics': stats
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@live_bp.route('/trades')
def get_trades():
    """Получить историю сделок."""
    try:
        storage = TradeStorage()
        timeframe = request.args.get('timeframe')
        limit = int(request.args.get('limit', 100))

        trades = storage.get_trade_history(timeframe, limit)

        return jsonify({
            'status': 'ok',
            'trades': trades,
            'count': len(trades)
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
