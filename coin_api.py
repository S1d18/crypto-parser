"""
API для Coin Dashboard — дашборд по каждой монете.

Endpoints:
- GET /api/coin/<symbol>/summary      — статистика + консенсус (% в лонге/шорте)
- GET /api/coin/<symbol>/best-params   — топ-5 параметров по PnL
- GET /api/coin/<symbol>/recent-trades — последние 10 закрытых сделок
"""
from flask import Blueprint, jsonify
from core.database import get_database

coin_bp = Blueprint('coin', __name__)

VALID_SYMBOLS = ['BTC', 'ETH', 'SOL', 'LTC', 'TON']


def _symbol_filter(symbol):
    """Return SQL LIKE pattern for symbol, e.g. 'BTC' -> 'BTC%'."""
    return f"{symbol.upper()}%"


@coin_bp.route('/<symbol>/summary')
def coin_summary(symbol):
    """Summary: strategy counts, PnL, consensus (% in long/short), per-TF breakdown."""
    symbol = symbol.upper()
    if symbol not in VALID_SYMBOLS:
        return jsonify({'status': 'error', 'message': 'Invalid symbol'}), 400

    db = get_database()
    like = _symbol_filter(symbol)

    # === Total strategies for this coin ===
    total = db.conn.execute(
        "SELECT COUNT(*) FROM strategies WHERE symbol LIKE ?", (like,)
    ).fetchone()[0]

    long_strats = db.conn.execute(
        "SELECT COUNT(*) FROM strategies WHERE symbol LIKE ? AND direction = 'long'", (like,)
    ).fetchone()[0]

    short_strats = db.conn.execute(
        "SELECT COUNT(*) FROM strategies WHERE symbol LIKE ? AND direction = 'short'", (like,)
    ).fetchone()[0]

    both_strats = db.conn.execute(
        "SELECT COUNT(*) FROM strategies WHERE symbol LIKE ? AND direction = 'both'", (like,)
    ).fetchone()[0]

    # === PnL summary ===
    pnl_row = db.conn.execute("""
        SELECT
            COALESCE(SUM(t.pnl), 0) as sum_pnl,
            COALESCE(AVG(t.pnl), 0) as avg_pnl,
            COUNT(*) as total_trades,
            SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END) as wins
        FROM trades t
        JOIN strategies s ON t.strategy_id = s.id
        WHERE s.symbol LIKE ? AND t.status = 'closed'
    """, (like,)).fetchone()

    total_trades = pnl_row['total_trades'] or 0
    wins = pnl_row['wins'] or 0
    win_rate = round(wins / total_trades * 100, 1) if total_trades > 0 else 0

    # === Consensus: open positions right now ===
    consensus_row = db.conn.execute("""
        SELECT
            COUNT(*) as open_total,
            SUM(CASE WHEN t.side = 'long' OR t.side = 'buy' THEN 1 ELSE 0 END) as open_long,
            SUM(CASE WHEN t.side = 'short' OR t.side = 'sell' THEN 1 ELSE 0 END) as open_short
        FROM trades t
        JOIN strategies s ON t.strategy_id = s.id
        WHERE s.symbol LIKE ? AND t.status = 'open'
    """, (like,)).fetchone()

    open_total = consensus_row['open_total'] or 0
    open_long = consensus_row['open_long'] or 0
    open_short = consensus_row['open_short'] or 0
    long_pct = round(open_long / total * 100, 1) if total > 0 else 0
    short_pct = round(open_short / total * 100, 1) if total > 0 else 0
    neutral_pct = round(100 - long_pct - short_pct, 1)

    # === Per-timeframe consensus ===
    tf_rows = db.conn.execute("""
        SELECT
            s.timeframe,
            COUNT(DISTINCT s.id) as total_strats,
            SUM(CASE WHEN t.status = 'open' AND (t.side = 'long' OR t.side = 'buy') THEN 1 ELSE 0 END) as in_long,
            SUM(CASE WHEN t.status = 'open' AND (t.side = 'short' OR t.side = 'sell') THEN 1 ELSE 0 END) as in_short
        FROM strategies s
        LEFT JOIN trades t ON t.strategy_id = s.id AND t.status = 'open'
        WHERE s.symbol LIKE ?
        GROUP BY s.timeframe
    """, (like,)).fetchall()

    tf_order = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '12h', '1d']
    tf_map = {}
    for r in tf_rows:
        tf = r['timeframe']
        t_total = r['total_strats'] or 0
        t_long = r['in_long'] or 0
        t_short = r['in_short'] or 0
        tf_map[tf] = {
            'timeframe': tf,
            'total': t_total,
            'in_long': t_long,
            'in_short': t_short,
            'neutral': t_total - t_long - t_short,
            'long_pct': round(t_long / t_total * 100, 1) if t_total > 0 else 0,
            'short_pct': round(t_short / t_total * 100, 1) if t_total > 0 else 0,
        }
    tf_consensus = [tf_map[tf] for tf in tf_order if tf in tf_map]

    # === Per-timeframe PnL ===
    tf_pnl_rows = db.conn.execute("""
        SELECT
            s.timeframe,
            ROUND(SUM(t.pnl), 2) as pnl,
            COUNT(*) as trades,
            SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END) as wins
        FROM trades t
        JOIN strategies s ON t.strategy_id = s.id
        WHERE s.symbol LIKE ? AND t.status = 'closed'
        GROUP BY s.timeframe
    """, (like,)).fetchall()

    tf_pnl_map = {}
    for r in tf_pnl_rows:
        tf_pnl_map[r['timeframe']] = {
            'pnl': r['pnl'],
            'trades': r['trades'],
            'win_rate': round(r['wins'] / r['trades'] * 100, 1) if r['trades'] > 0 else 0
        }

    # Merge PnL into tf_consensus
    for item in tf_consensus:
        pnl_data = tf_pnl_map.get(item['timeframe'], {})
        item['pnl'] = pnl_data.get('pnl', 0)
        item['trades'] = pnl_data.get('trades', 0)
        item['win_rate'] = pnl_data.get('win_rate', 0)

    return jsonify({
        'status': 'ok',
        'symbol': symbol,
        'total_strategies': total,
        'long_strategies': long_strats,
        'short_strategies': short_strats,
        'both_strategies': both_strats,
        'sum_pnl': round(pnl_row['sum_pnl'], 2),
        'avg_trade_pnl': round(pnl_row['avg_pnl'], 4),
        'total_trades': total_trades,
        'wins': wins,
        'win_rate': win_rate,
        'consensus': {
            'open_total': open_total,
            'open_long': open_long,
            'open_short': open_short,
            'long_pct': long_pct,
            'short_pct': short_pct,
            'neutral_pct': neutral_pct,
        },
        'tf_consensus': tf_consensus,
    })


@coin_bp.route('/<symbol>/best-params')
def coin_best_params(symbol):
    """Top-5 parameter combinations by avg PnL for this coin."""
    symbol = symbol.upper()
    if symbol not in VALID_SYMBOLS:
        return jsonify({'status': 'error', 'message': 'Invalid symbol'}), 400

    db = get_database()
    like = _symbol_filter(symbol)

    sql = """
        WITH strategy_stats AS (
            SELECT
                t.strategy_id,
                SUM(t.pnl) as total_pnl,
                COUNT(*) as trades,
                SUM(CASE WHEN t.pnl > 0 THEN 1 ELSE 0 END) as wins
            FROM trades t
            JOIN strategies s ON t.strategy_id = s.id
            WHERE s.symbol LIKE ? AND t.status = 'closed'
            GROUP BY t.strategy_id
            HAVING COUNT(*) >= 3
        )
        SELECT
            CAST(json_extract(s.params, '$.st_period') AS INT) as period,
            CAST(json_extract(s.params, '$.st_multiplier') AS REAL) as multiplier,
            CAST(json_extract(s.params, '$.sl_percent') AS REAL) as sl_percent,
            COUNT(*) as strategies,
            ROUND(AVG(ss.total_pnl), 4) as avg_pnl,
            ROUND(SUM(ss.total_pnl), 2) as sum_pnl,
            ROUND(AVG(CAST(ss.wins AS REAL) / ss.trades * 100), 1) as avg_winrate,
            ROUND(AVG(ss.trades), 0) as avg_trades
        FROM strategies s
        JOIN strategy_stats ss ON s.id = ss.strategy_id
        WHERE json_extract(s.params, '$.st_period') IS NOT NULL
        GROUP BY period, multiplier, sl_percent
        HAVING COUNT(*) >= 2
        ORDER BY avg_pnl DESC
        LIMIT 10
    """
    rows = db.conn.execute(sql, (like,)).fetchall()

    params_list = []
    for r in rows:
        params_list.append({
            'period': r['period'],
            'multiplier': r['multiplier'],
            'sl_percent': r['sl_percent'],
            'strategies': r['strategies'],
            'avg_pnl': r['avg_pnl'],
            'sum_pnl': r['sum_pnl'],
            'avg_winrate': r['avg_winrate'],
            'avg_trades': int(r['avg_trades'] or 0),
        })

    return jsonify({
        'status': 'ok',
        'symbol': symbol,
        'count': len(params_list),
        'params': params_list,
    })


@coin_bp.route('/<symbol>/recent-trades')
def coin_recent_trades(symbol):
    """Last 20 closed trades for this coin."""
    symbol = symbol.upper()
    if symbol not in VALID_SYMBOLS:
        return jsonify({'status': 'error', 'message': 'Invalid symbol'}), 400

    db = get_database()
    like = _symbol_filter(symbol)

    sql = """
        SELECT
            t.id, t.strategy_id, t.symbol, t.side, t.direction,
            t.entry_price, t.close_price, t.sl_price,
            t.opened_at, t.closed_at, t.close_reason,
            t.pnl, t.pnl_percent, t.fees,
            s.name as strategy_name, s.timeframe, s.direction as strat_direction
        FROM trades t
        JOIN strategies s ON t.strategy_id = s.id
        WHERE s.symbol LIKE ? AND t.status = 'closed'
        ORDER BY t.closed_at DESC
        LIMIT 20
    """
    rows = db.conn.execute(sql, (like,)).fetchall()

    trades = []
    for r in rows:
        trades.append({
            'id': r['id'],
            'strategy_id': r['strategy_id'],
            'strategy_name': r['strategy_name'],
            'timeframe': r['timeframe'],
            'symbol': r['symbol'],
            'side': r['side'],
            'direction': r['strat_direction'],
            'entry_price': r['entry_price'],
            'close_price': r['close_price'],
            'opened_at': r['opened_at'],
            'closed_at': r['closed_at'],
            'close_reason': r['close_reason'],
            'pnl': r['pnl'],
            'pnl_percent': r['pnl_percent'],
        })

    return jsonify({
        'status': 'ok',
        'symbol': symbol,
        'count': len(trades),
        'trades': trades,
    })
