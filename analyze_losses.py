"""Analyze losing trades across all strategies."""
import sqlite3
import os

dbs = {
    'Trend Rider': 'data/scalper_trend_rider.db',
    'Breakout': 'data/scalper_breakout.db',
    'Scalp Reversal': 'data/scalper_scalp_reversal.db',
    'VWAP Bounce': 'data/scalper_vwap_bounce.db',
}

for name, path in dbs.items():
    if not os.path.exists(path):
        continue
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row

    print(f'\n{"="*60}')
    print(f'  {name}')
    print(f'{"="*60}')

    # Close reasons breakdown
    print('\n  CLOSE REASONS:')
    rows = conn.execute("""
        SELECT close_reason, COUNT(*) cnt,
               ROUND(SUM(pnl),2) total_pnl,
               ROUND(AVG(pnl),2) avg_pnl,
               SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) wins
        FROM trades WHERE status='closed'
        GROUP BY close_reason ORDER BY total_pnl
    """).fetchall()
    for r in rows:
        print(f'    {r["close_reason"]:20s} cnt={r["cnt"]:3d}  '
              f'total_pnl={r["total_pnl"]:+8.2f}  avg={r["avg_pnl"]:+.2f}  '
              f'wins={r["wins"]}/{r["cnt"]}')

    # Trades that had profit but ended in loss
    print('\n  HAD PROFIT -> ENDED LOSS:')
    rows = conn.execute("""
        SELECT id, symbol, direction, ROUND(pnl,2) pnl,
               ROUND(peak_pnl,2) peak, close_reason,
               COALESCE(time_held_sec,0) held
        FROM trades
        WHERE status='closed' AND peak_pnl > 0.5 AND pnl < 0
        ORDER BY pnl
    """).fetchall()
    if rows:
        for r in rows:
            held_min = r['held'] // 60
            print(f'    #{r["id"]:3d} {r["symbol"]:25s} {r["direction"]:5s} '
                  f'pnl={r["pnl"]:+.2f}  peak={r["peak"]:.2f}  '
                  f'reason={r["close_reason"]}  held={held_min}m')
    else:
        print('    (none)')

    # Avg hold time: wins vs losses
    row = conn.execute("""
        SELECT
            ROUND(AVG(CASE WHEN pnl>0 THEN time_held_sec END)/60.0,1) win_min,
            ROUND(AVG(CASE WHEN pnl<=0 THEN time_held_sec END)/60.0,1) loss_min,
            ROUND(AVG(CASE WHEN pnl>0 THEN confidence END),0) win_conf,
            ROUND(AVG(CASE WHEN pnl<=0 THEN confidence END),0) loss_conf
        FROM trades WHERE status='closed'
    """).fetchone()
    print(f'\n  AVG HOLD: wins={row["win_min"]}m  losses={row["loss_min"]}m')
    print(f'  AVG CONFIDENCE: wins={row["win_conf"]}  losses={row["loss_conf"]}')

    # Worst symbols
    print('\n  WORST SYMBOLS:')
    rows = conn.execute("""
        SELECT symbol, COUNT(*) cnt, ROUND(SUM(pnl),2) total_pnl,
               SUM(CASE WHEN pnl>0 THEN 1 ELSE 0 END) wins
        FROM trades WHERE status='closed'
        GROUP BY symbol ORDER BY total_pnl LIMIT 5
    """).fetchall()
    for r in rows:
        print(f'    {r["symbol"]:25s} trades={r["cnt"]:2d}  '
              f'pnl={r["total_pnl"]:+.2f}  wins={r["wins"]}/{r["cnt"]}')

    # All trades list (compact)
    print('\n  ALL CLOSED TRADES:')
    rows = conn.execute("""
        SELECT id, symbol, direction, ROUND(pnl,2) pnl,
               ROUND(peak_pnl,2) peak, ROUND(missed_pnl,2) missed,
               close_reason, confidence,
               COALESCE(time_held_sec,0) held, opened_at, closed_at
        FROM trades WHERE status='closed' ORDER BY id
    """).fetchall()
    for r in rows:
        held_min = r['held'] // 60
        opened = (r['opened_at'] or '')[-8:-3]  # HH:MM
        print(f'    #{r["id"]:3d} {opened} {r["symbol"]:25s} {r["direction"]:5s} '
              f'pnl={r["pnl"]:+7.2f}  peak={r["peak"]:6.2f}  missed={r["missed"]:5.2f}  '
              f'conf={r["confidence"]:2d}  held={held_min:3d}m  {r["close_reason"]}')

    # Open positions
    opens = conn.execute("SELECT * FROM trades WHERE status='open'").fetchall()
    if opens:
        print(f'\n  OPEN POSITIONS ({len(opens)}):')
        for r in opens:
            peak = r['peak_pnl'] or 0
            print(f'    #{r["id"]:3d} {r["symbol"]:25s} {r["direction"]:5s} '
                  f'entry={r["entry_price"]:.4f}  sl={r["sl_price"]:.4f}  '
                  f'tp={r["tp_price"]:.4f}  peak={peak:.2f}  conf={r["confidence"]}')

    conn.close()

print(f'\n{"="*60}')
print('  ANALYSIS COMPLETE')
print(f'{"="*60}')
