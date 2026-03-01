"""
API для Paper Trading.

Endpoints:
- GET /api/paper/strategies - список всех paper стратегий
- GET /api/paper/strategy/<id> - детали стратегии
- GET /api/paper/statistics - агрегированная статистика
"""
from flask import Blueprint, jsonify, request
from strategies.paper.paper_storage import PaperTradeStorage
from strategies.paper.strategies import PAPER_STRATEGIES

paper_bp = Blueprint('paper', __name__)


@paper_bp.route('/strategies')
def get_strategies():
    """Получить список всех paper стратегий."""
    try:
        strategies_list = []
        for strategy in PAPER_STRATEGIES:
            strategies_list.append({
                'id': strategy.strategy_id,
                'group': strategy.group,
                'timeframe': strategy.timeframe,
                'direction': strategy.direction,
                'params': {
                    'period': strategy.st_period,
                    'multiplier': strategy.st_multiplier
                },
                'sl_percent': strategy.sl_percent
            })

        return jsonify({
            'status': 'ok',
            'strategies': strategies_list,
            'count': len(strategies_list)
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@paper_bp.route('/strategy/<strategy_id>')
def get_strategy(strategy_id):
    """Получить детали paper стратегии."""
    try:
        storage = PaperTradeStorage()

        # Найти стратегию
        strategy = next((s for s in PAPER_STRATEGIES if s.strategy_id == strategy_id), None)
        if not strategy:
            return jsonify({'status': 'error', 'message': 'Strategy not found'}), 404

        # Получить статистику
        stats = storage.get_statistics(strategy_id)

        # Получить историю сделок
        trades = storage.get_trade_history(strategy_id, limit=50)

        return jsonify({
            'status': 'ok',
            'strategy': {
                'id': strategy.strategy_id,
                'group': strategy.group,
                'timeframe': strategy.timeframe,
                'direction': strategy.direction,
                'params': {
                    'period': strategy.st_period,
                    'multiplier': strategy.st_multiplier
                },
                'sl_percent': strategy.sl_percent
            },
            'statistics': stats,
            'recent_trades': trades
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@paper_bp.route('/statistics')
def get_statistics():
    """Получить агрегированную статистику всех paper стратегий."""
    try:
        storage = PaperTradeStorage()

        # Агрегировать по группам
        groups = {}
        for strategy in PAPER_STRATEGIES:
            if strategy.group not in groups:
                groups[strategy.group] = {
                    'strategies': [],
                    'total_pnl': 0,
                    'total_trades': 0
                }

            stats = storage.get_statistics(strategy.strategy_id)
            groups[strategy.group]['strategies'].append({
                'id': strategy.strategy_id,
                'timeframe': strategy.timeframe,
                'pnl': stats.get('total_pnl', 0),
                'trades': stats.get('total', 0),
                'win_rate': stats.get('win_rate', 0)
            })
            groups[strategy.group]['total_pnl'] += stats.get('total_pnl', 0)
            groups[strategy.group]['total_trades'] += stats.get('total', 0)

        return jsonify({
            'status': 'ok',
            'groups': groups
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
