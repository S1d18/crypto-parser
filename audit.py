"""Audit all strategy databases."""
import sqlite3
import os

DBS = {
    'Sniper Original (5000)': 'data/scalper_default.db',
    'Trend Rider (5001)': 'data/scalper_trend_rider.db',
    'Breakout (5002)': 'data/scalper_breakout.db',
    'Scalp Reversal (5003)': 'data/scalper_scalp_reversal.db',
    'VWAP Bounce (5004)': 'data/scalper_vwap_bounce.db',
}

for name, path in DBS.items():
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")

    if not os.path.exists(path):
        print("  DB not found")
        continue

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row

    # Open
    opens = conn.execute("SELECT * FROM trades WHERE status='open'").fetchall()
    print(f"\n  Open positions: {len(opens)}")
    for r in opens:
        peak = r['peak_pnl'] or 0
        print(f"    #{r['id']} {r['symbol']:25s} {r['direction']:5s} "
              f"entry=${r['entry_price']:.4f}  peak=${peak:.2f}")

    # Closed
    closed = conn.execute("SELECT * FROM trades WHERE status='closed' ORDER BY id").fetchall()
    print(f"\n  Closed trades: {len(closed)}")
    total_pnl = 0
    total_missed = 0
    wins = 0
    problems = []

    for r in closed:
        pnl = r['pnl'] or 0
        peak = r['peak_pnl'] or 0
        missed = r['missed_pnl'] or 0
        held = r['time_held_sec'] or 0
        conf = r['confidence'] or 0
        total_pnl += pnl
        total_missed += missed
        if pnl > 0:
            wins += 1

        flag = ""
        # Check for issues
        if missed > 5:
            flag = " *** MISSED >$5"
            problems.append(f"#{r['id']} {r['symbol']} missed ${missed:.2f}")
        if peak > 5 and pnl <= 0:
            flag = " *** PEAK>$5 BUT LOSS"
            problems.append(f"#{r['id']} {r['symbol']} peak=${peak:.2f} but pnl=${pnl:.2f}")
        if r['close_reason'] == 'lost_on_restart':
            flag = " *** LOST ON RESTART"

        print(f"    #{r['id']:3d} {r['symbol']:25s} {r['direction']:5s} "
              f"pnl=${pnl:+7.2f}  peak=${peak:6.2f}  missed=${missed:5.2f}  "
              f"held={held//60:3d}m  conf={conf:2d}  reason={r['close_reason']}{flag}")

    if closed:
        wr = wins / len(closed) * 100
        print(f"\n  SUMMARY: PnL=${total_pnl:+.2f} | WinRate={wr:.0f}% ({wins}/{len(closed)}) "
              f"| Missed=${total_missed:.2f}")

    if problems:
        print(f"\n  PROBLEMS:")
        for p in problems:
            print(f"    - {p}")

    conn.close()

print(f"\n{'='*60}")
print("  AUDIT COMPLETE")
print(f"{'='*60}")
