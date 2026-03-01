"""
API для аналитики и сравнения стратегий.

Endpoints:
- GET /api/analytics/heatmap - heatmap доходности (24x7)
- GET /api/analytics/comparison - сравнение нескольких стратегий
- GET /api/analytics/top-performers - топ стратегий
- GET /api/analytics/metrics - детальные метрики
"""
from flask import Blueprint, jsonify, request
from datetime import datetime, timedelta
from core.database import get_database

analytics_bp = Blueprint('analytics', __name__)


@analytics_bp.route('/heatmap')
def get_heatmap():
    """
    Получить heatmap доходности по часам и дням недели.

    Returns:
        {
            'heatmap': [[hour0_mon, hour0_tue, ...], [hour1_mon, ...], ...],  # 24x7
            'min_value': float,
            'max_value': float
        }
    """
    try:
        db = get_database()
        conn = db.get_connection()

        # TODO: Реализовать реальную агрегацию по часам/дням
        # Пока возвращаем заглушку
        heatmap = [[0.0] * 7 for _ in range(24)]

        return jsonify({
            'status': 'ok',
            'heatmap': heatmap,
            'min_value': -100,
            'max_value': 100
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@analytics_bp.route('/comparison')
def get_comparison():
    """
    Сравнить несколько стратегий.

    Query params:
        strategy_ids: comma-separated list (e.g., "1,2,3")
    """
    try:
        strategy_ids = request.args.get('strategy_ids', '').split(',')
        if not strategy_ids or strategy_ids == ['']:
            return jsonify({'status': 'error', 'message': 'strategy_ids required'}), 400

        # TODO: Реализовать сравнение стратегий
        # Получить equity curves, метрики, и т.д.

        return jsonify({
            'status': 'ok',
            'strategies': [],
            'comparison': {}
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@analytics_bp.route('/top-performers')
def get_top_performers():
    """Получить топ-10 стратегий по разным метрикам."""
    try:
        period = request.args.get('period', '7d')  # 24h, 7d, 30d

        # TODO: Реализовать получение топ стратегий

        return jsonify({
            'status': 'ok',
            'period': period,
            'top_by_pnl': [],
            'top_by_win_rate': [],
            'top_by_sharpe': []
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@analytics_bp.route('/metrics/<int:strategy_id>')
def get_metrics(strategy_id):
    """Получить детальные метрики стратегии."""
    try:
        db = get_database()
        conn = db.get_connection()

        # TODO: Рассчитать метрики из trades
        metrics = {
            'total_trades': 0,
            'win_rate': 0.0,
            'profit_factor': 0.0,
            'sharpe_ratio': 0.0,
            'max_drawdown': 0.0,
            'expectancy': 0.0,
            'avg_win': 0.0,
            'avg_loss': 0.0
        }

        return jsonify({
            'status': 'ok',
            'strategy_id': strategy_id,
            'metrics': metrics
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
