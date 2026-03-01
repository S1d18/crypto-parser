"""
API для аналитики — 4 endpoint'а с SQL-агрегацией.

Endpoints:
- GET /api/analytics/dashboard - Summary + chart data
- GET /api/analytics/heatmap  - Parameter heatmap (period × multiplier)
- GET /api/analytics/rating   - Top-N filterable ranking
- GET /api/analytics/groups   - Group comparison (by TF, direction, coin)
"""
import math
from flask import Blueprint, jsonify, request
from core.database import get_database

analytics_bp = Blueprint('analytics', __name__)


def _build_filters(prefix_t='t', prefix_s='s'):
    """Build WHERE parts from common query params. Returns (where_parts, params)."""
    where_parts = []
    params = []

    symbol = request.args.get('symbol', '')
    direction = request.args.get('direction', '')
    timeframe = request.args.get('timeframe', '')

    if symbol:
        where_parts.append(f"{prefix_s}.symbol LIKE ?")
        params.append(f"{symbol}%")
    if direction:
        where_parts.append(f"{prefix_s}.direction = ?")
        params.append(direction)
    if timeframe:
        where_parts.append(f"{prefix_s}.timeframe = ?")
        params.append(timeframe)

    return where_parts, params


@analytics_bp.route('/dashboard')
def get_dashboard():
    """Summary stats + chart data for all strategies."""
    db = get_database()

    filters, params = _build_filters()
    trade_where = "t.status = 'closed'"
    if filters:
        trade_where += " AND " + " AND ".join(filters)

    # === Summary cards ===
    summary_sql = f"""
        WITH strategy_pnl AS (
            SELECT
                t.strategy_id,
                SUM(t.pnl) as total_pnl,
                COUNT(*) as trades,
                SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END) as wins
            FROM trades t
            JOIN strategies s ON t.strategy_id = s.id
            WHERE {trade_where}
            GROUP BY t.strategy_id
        )
        SELECT
            (SELECT COUNT(*) FROM strategies s WHERE 1=1
                {(' AND ' + ' AND '.join(filters).replace('t.', 's.')) if filters else ''}) as total_strategies,
            COUNT(*) as with_trades,
            SUM(CASE WHEN total_pnl > 0 THEN 1 ELSE 0 END) as profitable,
            SUM(CASE WHEN total_pnl <= 0 THEN 1 ELSE 0 END) as losing,
            ROUND(SUM(total_pnl), 2) as sum_pnl,
            ROUND(AVG(total_pnl), 2) as avg_pnl,
            SUM(trades) as total_trades
        FROM strategy_pnl
    """
    # The subquery for total_strategies is tricky with dynamic filters, let's do it separately
    strat_where_parts = []
    strat_params = []
    symbol = request.args.get('symbol', '')
    direction = request.args.get('direction', '')
    timeframe = request.args.get('timeframe', '')
    if symbol:
        strat_where_parts.append("symbol LIKE ?")
        strat_params.append(f"{symbol}%")
    if direction:
        strat_where_parts.append("direction = ?")
        strat_params.append(direction)
    if timeframe:
        strat_where_parts.append("timeframe = ?")
        strat_params.append(timeframe)

    strat_where = " AND ".join(strat_where_parts) if strat_where_parts else "1=1"
    total_strategies = db.conn.execute(
        f"SELECT COUNT(*) FROM strategies WHERE {strat_where}", strat_params
    ).fetchone()[0]

    # Strategy-level aggregation
    spnl_sql = f"""
        SELECT
            t.strategy_id,
            SUM(t.pnl) as total_pnl,
            COUNT(*) as trades,
            SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END) as wins
        FROM trades t
        JOIN strategies s ON t.strategy_id = s.id
        WHERE {trade_where}
        GROUP BY t.strategy_id
    """
    rows = db.conn.execute(spnl_sql, params).fetchall()

    with_trades = len(rows)
    profitable = sum(1 for r in rows if r['total_pnl'] > 0)
    losing = sum(1 for r in rows if r['total_pnl'] <= 0)
    sum_pnl = round(sum(r['total_pnl'] for r in rows), 2)
    avg_pnl = round(sum_pnl / with_trades, 2) if with_trades else 0
    total_trades_count = sum(r['trades'] for r in rows)

    # Best/worst strategy
    best_strat = None
    worst_strat = None
    if rows:
        best_row = max(rows, key=lambda r: r['total_pnl'])
        worst_row = min(rows, key=lambda r: r['total_pnl'])
        # Get names
        best_name = db.conn.execute("SELECT name FROM strategies WHERE id=?", (best_row['strategy_id'],)).fetchone()
        worst_name = db.conn.execute("SELECT name FROM strategies WHERE id=?", (worst_row['strategy_id'],)).fetchone()
        best_strat = {'name': best_name['name'] if best_name else '?', 'pnl': round(best_row['total_pnl'], 2)}
        worst_strat = {'name': worst_name['name'] if worst_name else '?', 'pnl': round(worst_row['total_pnl'], 2)}

    # === PnL by coin ===
    coin_sql = f"""
        SELECT
            CASE
                WHEN s.symbol LIKE 'BTC%' THEN 'BTC'
                WHEN s.symbol LIKE 'ETH%' THEN 'ETH'
                WHEN s.symbol LIKE 'SOL%' THEN 'SOL'
                WHEN s.symbol LIKE 'LTC%' THEN 'LTC'
                WHEN s.symbol LIKE 'TON%' THEN 'TON'
                ELSE 'OTHER'
            END as coin,
            COUNT(DISTINCT s.id) as strategies,
            COUNT(*) as trades,
            ROUND(SUM(t.pnl), 2) as pnl,
            SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END) as wins
        FROM trades t
        JOIN strategies s ON t.strategy_id = s.id
        WHERE {trade_where}
        GROUP BY coin
        ORDER BY pnl DESC
    """
    pnl_by_coin = [dict(r) for r in db.conn.execute(coin_sql, params).fetchall()]

    # === PnL by timeframe ===
    tf_sql = f"""
        SELECT
            s.timeframe,
            COUNT(DISTINCT s.id) as strategies,
            COUNT(*) as trades,
            ROUND(SUM(t.pnl), 2) as pnl,
            SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END) as wins
        FROM trades t
        JOIN strategies s ON t.strategy_id = s.id
        WHERE {trade_where}
        GROUP BY s.timeframe
    """
    pnl_by_tf_raw = [dict(r) for r in db.conn.execute(tf_sql, params).fetchall()]

    # Sort by timeframe order
    tf_order = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '12h', '1d']
    tf_map = {r['timeframe']: r for r in pnl_by_tf_raw}
    pnl_by_tf = [tf_map[tf] for tf in tf_order if tf in tf_map]

    # === PnL by direction ===
    dir_sql = f"""
        SELECT
            s.direction,
            COUNT(DISTINCT s.id) as strategies,
            COUNT(*) as trades,
            ROUND(SUM(t.pnl), 2) as pnl,
            SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END) as wins
        FROM trades t
        JOIN strategies s ON t.strategy_id = s.id
        WHERE {trade_where}
        GROUP BY s.direction
        ORDER BY pnl DESC
    """
    pnl_by_dir = [dict(r) for r in db.conn.execute(dir_sql, params).fetchall()]

    # === Win Rate distribution ===
    wr_sql = f"""
        SELECT bucket * 10 as wr_from, bucket * 10 + 10 as wr_to, COUNT(*) as count
        FROM (
            SELECT
                MIN(CAST(SUM(CASE WHEN t.pnl > 0 THEN 1.0 ELSE 0 END) / COUNT(*) * 10 AS INT), 9) as bucket
            FROM trades t
            JOIN strategies s ON t.strategy_id = s.id
            WHERE {trade_where}
            GROUP BY t.strategy_id
            HAVING COUNT(*) >= 3
        )
        GROUP BY bucket
        ORDER BY bucket
    """
    wr_dist = [dict(r) for r in db.conn.execute(wr_sql, params).fetchall()]

    return jsonify({
        'status': 'ok',
        'summary': {
            'total_strategies': total_strategies,
            'with_trades': with_trades,
            'profitable': profitable,
            'losing': losing,
            'sum_pnl': sum_pnl,
            'avg_pnl': avg_pnl,
            'total_trades': total_trades_count,
            'best_strategy': best_strat,
            'worst_strategy': worst_strat,
        },
        'pnl_by_coin': pnl_by_coin,
        'pnl_by_timeframe': pnl_by_tf,
        'pnl_by_direction': pnl_by_dir,
        'winrate_distribution': wr_dist,
    })


@analytics_bp.route('/heatmap')
def get_heatmap():
    """Parameter heatmap: avg PnL by (st_period, st_multiplier)."""
    db = get_database()

    filters, params = _build_filters()
    trade_where = "t.status = 'closed'"
    if filters:
        trade_where += " AND " + " AND ".join(filters)

    sql = f"""
        WITH strategy_stats AS (
            SELECT
                t.strategy_id,
                SUM(t.pnl) as total_pnl,
                COUNT(*) as trades,
                CAST(SUM(CASE WHEN t.pnl > 0 THEN 1.0 ELSE 0 END) / COUNT(*) * 100 AS REAL) as win_rate
            FROM trades t
            JOIN strategies s ON t.strategy_id = s.id
            WHERE {trade_where}
            GROUP BY t.strategy_id
            HAVING COUNT(*) >= 2
        )
        SELECT
            CAST(json_extract(s.params, '$.st_period') AS INT) as period,
            CAST(json_extract(s.params, '$.st_multiplier') AS REAL) as multiplier,
            COUNT(*) as count,
            ROUND(AVG(ss.total_pnl), 4) as avg_pnl,
            ROUND(AVG(ss.win_rate), 1) as avg_winrate,
            ROUND(SUM(ss.total_pnl), 2) as sum_pnl,
            ROUND(AVG(ss.trades), 1) as avg_trades
        FROM strategies s
        JOIN strategy_stats ss ON s.id = ss.strategy_id
        WHERE json_extract(s.params, '$.st_period') IS NOT NULL
        GROUP BY period, multiplier
        ORDER BY period, multiplier
    """
    rows = db.conn.execute(sql, params).fetchall()

    cells = []
    for r in rows:
        cells.append({
            'period': r['period'],
            'multiplier': r['multiplier'],
            'count': r['count'],
            'avg_pnl': r['avg_pnl'],
            'avg_winrate': r['avg_winrate'],
            'sum_pnl': r['sum_pnl'],
            'avg_trades': r['avg_trades'],
        })

    # Get unique axis values
    periods = sorted(set(c['period'] for c in cells))
    multipliers = sorted(set(c['multiplier'] for c in cells))

    return jsonify({
        'status': 'ok',
        'cells': cells,
        'periods': periods,
        'multipliers': multipliers,
    })


@analytics_bp.route('/rating')
def get_rating():
    """Top-N strategy ranking with all metrics."""
    db = get_database()

    filters, params = _build_filters()
    trade_where = "t.status = 'closed'"
    if filters:
        trade_where += " AND " + " AND ".join(filters)

    min_trades = request.args.get('min_trades', 3, type=int)
    limit = request.args.get('limit', 25, type=int)
    limit = min(limit, 200)
    sort_by = request.args.get('sort_by', 'total_pnl')
    sort_dir = request.args.get('sort_dir', 'desc')

    # Validate sort_by
    valid_sorts = ['total_pnl', 'win_rate', 'profit_factor', 'trades', 'avg_pnl', 'max_drawdown']
    if sort_by not in valid_sorts:
        sort_by = 'total_pnl'
    order_dir = 'DESC' if sort_dir == 'desc' else 'ASC'

    sql = f"""
        WITH strategy_stats AS (
            SELECT
                t.strategy_id,
                COUNT(*) as trades,
                SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN t.pnl <= 0 THEN 1 ELSE 0 END) as losses,
                ROUND(SUM(t.pnl), 4) as total_pnl,
                ROUND(AVG(t.pnl), 4) as avg_pnl,
                ROUND(MAX(t.pnl), 4) as best_trade,
                ROUND(MIN(t.pnl), 4) as worst_trade,
                SUM(CASE WHEN t.pnl > 0 THEN t.pnl ELSE 0 END) as gross_profit,
                SUM(CASE WHEN t.pnl < 0 THEN ABS(t.pnl) ELSE 0 END) as gross_loss
            FROM trades t
            JOIN strategies s ON t.strategy_id = s.id
            WHERE {trade_where}
            GROUP BY t.strategy_id
            HAVING COUNT(*) >= ?
        )
        SELECT
            s.id, s.name, s.symbol, s.timeframe, s.direction, s.params,
            ss.trades, ss.wins, ss.losses,
            ss.total_pnl,
            ss.avg_pnl,
            ss.best_trade,
            ss.worst_trade,
            ROUND(CAST(ss.wins AS REAL) / ss.trades * 100, 1) as win_rate,
            ROUND(CASE WHEN ss.gross_loss > 0 THEN ss.gross_profit / ss.gross_loss ELSE 0 END, 2) as profit_factor,
            ss.gross_profit,
            ss.gross_loss,
            (SELECT COUNT(*) FROM trades WHERE strategy_id = s.id AND status = 'open') as open_trades
        FROM strategies s
        JOIN strategy_stats ss ON s.id = ss.strategy_id
        ORDER BY {sort_by} {order_dir}
        LIMIT ?
    """
    rows = db.conn.execute(sql, params + [min_trades, limit]).fetchall()

    strategies = []
    for r in rows:
        strategies.append({
            'id': r['id'],
            'name': r['name'],
            'symbol': (r['symbol'] or '').split('/')[0],
            'timeframe': r['timeframe'],
            'direction': r['direction'],
            'trades': r['trades'],
            'wins': r['wins'],
            'losses': r['losses'],
            'total_pnl': r['total_pnl'],
            'avg_pnl': r['avg_pnl'],
            'win_rate': r['win_rate'],
            'profit_factor': r['profit_factor'],
            'best_trade': r['best_trade'],
            'worst_trade': r['worst_trade'],
            'open_trades': r['open_trades'],
        })

    return jsonify({
        'status': 'ok',
        'count': len(strategies),
        'strategies': strategies,
    })


@analytics_bp.route('/groups')
def get_groups():
    """Aggregated group comparison."""
    db = get_database()

    filters, params = _build_filters()
    trade_where = "t.status = 'closed'"
    if filters:
        trade_where += " AND " + " AND ".join(filters)

    group_by = request.args.get('group_by', 'timeframe')

    # Map group_by to SQL expression
    group_map = {
        'timeframe': ("s.timeframe", "s.timeframe"),
        'direction': ("s.direction", "s.direction"),
        'symbol': ("""CASE
            WHEN s.symbol LIKE 'BTC%' THEN 'BTC'
            WHEN s.symbol LIKE 'ETH%' THEN 'ETH'
            WHEN s.symbol LIKE 'SOL%' THEN 'SOL'
            WHEN s.symbol LIKE 'LTC%' THEN 'LTC'
            WHEN s.symbol LIKE 'TON%' THEN 'TON'
            ELSE 'OTHER' END""", "coin"),
        'tf_direction': ("s.timeframe || ' ' || s.direction", "s.timeframe || ' ' || s.direction"),
        'symbol_tf': ("""CASE
            WHEN s.symbol LIKE 'BTC%' THEN 'BTC'
            WHEN s.symbol LIKE 'ETH%' THEN 'ETH'
            WHEN s.symbol LIKE 'SOL%' THEN 'SOL'
            WHEN s.symbol LIKE 'LTC%' THEN 'LTC'
            WHEN s.symbol LIKE 'TON%' THEN 'TON'
            ELSE 'OTHER' END || ' ' || s.timeframe""", "group_key"),
    }

    if group_by not in group_map:
        group_by = 'timeframe'

    group_expr, group_alias = group_map[group_by]

    sql = f"""
        WITH strategy_stats AS (
            SELECT
                t.strategy_id,
                SUM(t.pnl) as total_pnl,
                COUNT(*) as trades,
                SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN t.pnl > 0 THEN t.pnl ELSE 0 END) as gross_profit,
                SUM(CASE WHEN t.pnl < 0 THEN ABS(t.pnl) ELSE 0 END) as gross_loss
            FROM trades t
            JOIN strategies s ON t.strategy_id = s.id
            WHERE {trade_where}
            GROUP BY t.strategy_id
        )
        SELECT
            {group_expr} as group_name,
            COUNT(*) as strategies,
            ROUND(AVG(ss.total_pnl), 2) as avg_pnl,
            ROUND(SUM(ss.total_pnl), 2) as sum_pnl,
            ROUND(AVG(CAST(ss.wins AS REAL) / ss.trades * 100), 1) as avg_winrate,
            ROUND(CASE WHEN SUM(ss.gross_loss) > 0
                THEN SUM(ss.gross_profit) / SUM(ss.gross_loss) ELSE 0 END, 2) as profit_factor,
            SUM(ss.trades) as total_trades,
            SUM(CASE WHEN ss.total_pnl > 0 THEN 1 ELSE 0 END) as profitable_count,
            ROUND(CAST(SUM(CASE WHEN ss.total_pnl > 0 THEN 1 ELSE 0 END) AS REAL) / COUNT(*) * 100, 1) as profitable_pct
        FROM strategies s
        JOIN strategy_stats ss ON s.id = ss.strategy_id
        GROUP BY group_name
        ORDER BY avg_pnl DESC
    """
    rows = db.conn.execute(sql, params).fetchall()

    groups = []
    for r in rows:
        groups.append({
            'name': r['group_name'],
            'strategies': r['strategies'],
            'avg_pnl': r['avg_pnl'],
            'sum_pnl': r['sum_pnl'],
            'avg_winrate': r['avg_winrate'],
            'profit_factor': r['profit_factor'],
            'total_trades': r['total_trades'],
            'profitable_count': r['profitable_count'],
            'profitable_pct': r['profitable_pct'],
        })

    return jsonify({
        'status': 'ok',
        'group_by': group_by,
        'count': len(groups),
        'groups': groups,
    })
