"""
Verify PnL accuracy across all strategy databases.

Checks:
1. Partial close bug — 30% PnL lost from accounting
2. Balance drift — DB balance vs calculated balance
3. Bybit real balance comparison
4. Trade-level PnL recalculation

Run on Raspberry Pi: python verify_pnl.py
"""
import sqlite3
import os
import sys

# --------------- Bybit balance check ---------------
def get_bybit_balance():
    """Get real USDT balance from Bybit demo account."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    api_key = os.getenv('BYBIT_API_KEY', '')
    api_secret = os.getenv('BYBIT_API_SECRET', '')
    is_demo = os.getenv('BYBIT_DEMO', 'true').lower() in ('true', '1', 'yes')

    if not api_key:
        return None, "No API key in .env"

    try:
        import ccxt
        ex = ccxt.bybit({
            'apiKey': api_key,
            'secret': api_secret,
            'options': {'defaultType': 'swap'},
            'enableRateLimit': True,
        })
        if is_demo:
            ex.enable_demo_trading(True)
        ex.load_markets()
        bal = ex.fetch_balance()
        usdt = bal.get('USDT', {})
        return {
            'total': float(usdt.get('total', 0)),
            'free': float(usdt.get('free', 0)),
            'used': float(usdt.get('used', 0)),  # margin in open positions
        }, None
    except Exception as e:
        return None, str(e)


# --------------- DB analysis ---------------
DBS = {
    'Sniper Original (5000)': 'data/scalper_default.db',
    'Trend Rider (5001)':     'data/scalper_trend_rider.db',
    'Breakout (5002)':        'data/scalper_breakout.db',
    'Scalp Reversal (5003)':  'data/scalper_scalp_reversal.db',
    'VWAP Bounce (5004)':     'data/scalper_vwap_bounce.db',
}

TAKER_FEE = 0.00055
INITIAL_BALANCE = 200.0


def analyze_db(name, path):
    """Analyze one strategy DB for PnL accuracy."""
    result = {
        'name': name,
        'exists': False,
        'open_trades': 0,
        'closed_trades': 0,
        'db_balance': None,
        'calculated_balance': None,
        'total_recorded_pnl': 0,
        'partial_close_trades': [],
        'partial_close_lost_pnl': 0,
        'pnl_mismatches': [],
        'problems': [],
    }

    if not os.path.exists(path):
        return result

    result['exists'] = True
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row

    # --- Saved balance ---
    row = conn.execute("SELECT value FROM state WHERE key='balance'").fetchone()
    if row:
        result['db_balance'] = float(row['value'])

    # --- Open trades ---
    opens = conn.execute("SELECT * FROM trades WHERE status='open'").fetchall()
    result['open_trades'] = len(opens)

    # --- Closed trades ---
    closed = conn.execute(
        "SELECT * FROM trades WHERE status='closed' ORDER BY id"
    ).fetchall()
    result['closed_trades'] = len(closed)

    # --- Check trade_events for partial closes ---
    # Build set of trade IDs that had partial close events
    partial_ids = set()
    try:
        events = conn.execute(
            "SELECT trade_id, event_type, details FROM trade_events "
            "WHERE event_type = 'partial_close'"
        ).fetchall()
        for ev in events:
            partial_ids.add(ev['trade_id'])
    except Exception:
        pass  # table might not exist in old DBs

    # --- Analyze each closed trade ---
    total_recorded_pnl = 0
    total_partial_lost = 0

    for t in closed:
        pnl = t['pnl'] or 0
        total_recorded_pnl += pnl
        trade_id = t['id']

        # Check if this trade had a partial close
        if trade_id in partial_ids:
            # Try to extract partial PnL from event details
            ev_rows = conn.execute(
                "SELECT details FROM trade_events "
                "WHERE trade_id = ? AND event_type = 'partial_close'",
                (trade_id,)
            ).fetchall()

            partial_pnl_from_event = 0
            for ev in ev_rows:
                detail = ev['details'] or ''
                # Format: "Закрыто 30% ($X.XX), остаток 70% едет"
                if '$' in detail:
                    try:
                        val = detail.split('$')[1].split(')')[0]
                        partial_pnl_from_event = float(val)
                    except (IndexError, ValueError):
                        pass

            if partial_pnl_from_event > 0:
                result['partial_close_trades'].append({
                    'id': trade_id,
                    'symbol': t['symbol'],
                    'direction': t['direction'],
                    'recorded_pnl': round(pnl, 4),
                    'partial_pnl_lost': round(partial_pnl_from_event, 4),
                    'should_be_pnl': round(pnl + partial_pnl_from_event, 4),
                    'close_reason': t['close_reason'],
                })
                total_partial_lost += partial_pnl_from_event

        # --- Recalculate PnL from entry/exit to verify ---
        if t['exit_price'] and t['entry_price'] and t['qty']:
            entry = t['entry_price']
            exit_p = t['exit_price']
            qty = t['qty']
            direction = t['direction']

            if direction == 'long':
                gross = (exit_p - entry) * qty
            else:
                gross = (entry - exit_p) * qty

            fees = (entry * qty + exit_p * qty) * TAKER_FEE
            recalc_pnl = gross - fees

            # But qty in DB is already reduced to 70% if partial close happened
            # So recalc will match the recorded (wrong) PnL
            # The real check is whether partial_pnl was added

            diff = abs(recalc_pnl - pnl)
            if diff > 0.05:  # >5 cents discrepancy
                result['pnl_mismatches'].append({
                    'id': trade_id,
                    'symbol': t['symbol'],
                    'recorded_pnl': round(pnl, 4),
                    'recalculated_pnl': round(recalc_pnl, 4),
                    'diff': round(diff, 4),
                })

    result['total_recorded_pnl'] = round(total_recorded_pnl, 4)
    result['partial_close_lost_pnl'] = round(total_partial_lost, 4)
    result['calculated_balance'] = round(
        INITIAL_BALANCE + total_recorded_pnl, 2
    )

    # --- Problems ---
    if result['db_balance'] is not None:
        calc_bal = result['calculated_balance']
        db_bal = result['db_balance']
        drift = round(db_bal - calc_bal, 2)
        if abs(drift) > 0.1:
            result['problems'].append(
                f"Balance drift: DB=${db_bal:.2f} vs calculated=${calc_bal:.2f} "
                f"(diff=${drift:+.2f})"
            )

    if total_partial_lost > 0:
        result['problems'].append(
            f"Partial close bug: ${total_partial_lost:.2f} profit lost from "
            f"{len(result['partial_close_trades'])} trades"
        )

    conn.close()
    return result


# --------------- Main ---------------
def main():
    print("=" * 70)
    print("  PnL VERIFICATION REPORT")
    print("=" * 70)

    # Bybit balance
    print("\n>>> Checking Bybit balance...")
    bybit_bal, bybit_err = get_bybit_balance()
    if bybit_bal:
        print(f"  Bybit USDT total:  ${bybit_bal['total']:.2f}")
        print(f"  Bybit USDT free:   ${bybit_bal['free']:.2f}")
        print(f"  Bybit USDT used:   ${bybit_bal['used']:.2f} (margin)")
    else:
        print(f"  Could not fetch: {bybit_err}")

    # Per-strategy analysis
    all_db_balance = 0
    all_recorded_pnl = 0
    all_partial_lost = 0
    all_partial_trades = 0
    strategy_count = 0

    for name, path in DBS.items():
        r = analyze_db(name, path)
        if not r['exists']:
            continue

        strategy_count += 1
        print(f"\n{'-' * 70}")
        print(f"  {name}")
        print(f"{'-' * 70}")

        print(f"  Open: {r['open_trades']}  |  Closed: {r['closed_trades']}")

        if r['db_balance'] is not None:
            print(f"  DB balance:         ${r['db_balance']:.2f}")
            all_db_balance += r['db_balance']
        print(f"  Recorded total PnL: ${r['total_recorded_pnl']:+.2f}")
        print(f"  Calculated balance: ${r['calculated_balance']:.2f} "
              f"(${INITIAL_BALANCE} + PnL)")

        all_recorded_pnl += r['total_recorded_pnl']

        # Partial close issues
        if r['partial_close_trades']:
            all_partial_lost += r['partial_close_lost_pnl']
            all_partial_trades += len(r['partial_close_trades'])
            print(f"\n  PARTIAL CLOSE BUG — {len(r['partial_close_trades'])} trades affected:")
            for pt in r['partial_close_trades']:
                print(f"    #{pt['id']:3d} {pt['symbol']:25s} {pt['direction']:5s} "
                      f"recorded=${pt['recorded_pnl']:+.2f}  "
                      f"lost_partial=${pt['partial_pnl_lost']:+.2f}  "
                      f"should_be=${pt['should_be_pnl']:+.2f}  "
                      f"({pt['close_reason']})")

        # PnL recalculation mismatches
        if r['pnl_mismatches']:
            print(f"\n  PnL RECALC MISMATCHES — {len(r['pnl_mismatches'])} trades:")
            for m in r['pnl_mismatches']:
                print(f"    #{m['id']:3d} {m['symbol']:25s} "
                      f"recorded=${m['recorded_pnl']:+.4f}  "
                      f"recalculated=${m['recalculated_pnl']:+.4f}  "
                      f"diff=${m['diff']:.4f}")

        # Problems
        if r['problems']:
            print(f"\n  PROBLEMS:")
            for p in r['problems']:
                print(f"    ! {p}")

    # --------------- Global summary ---------------
    print(f"\n{'=' * 70}")
    print(f"  GLOBAL SUMMARY")
    print(f"{'=' * 70}")

    print(f"\n  Strategies analyzed: {strategy_count}")
    print(f"  Total recorded PnL across all: ${all_recorded_pnl:+.2f}")
    print(f"  Sum of DB balances:            ${all_db_balance:.2f}")
    print(f"  Expected total (${INITIAL_BALANCE}x{strategy_count} + PnL): "
          f"${INITIAL_BALANCE * strategy_count + all_recorded_pnl:.2f}")

    if all_partial_trades > 0:
        print(f"\n  PARTIAL CLOSE BUG TOTAL:")
        print(f"    Trades affected:  {all_partial_trades}")
        print(f"    PnL lost:         ${all_partial_lost:+.2f}")
        corrected_pnl = all_recorded_pnl + all_partial_lost
        print(f"    Corrected PnL:    ${corrected_pnl:+.2f}")

    if bybit_bal:
        print(f"\n  BYBIT vs BOT:")
        print(f"    Bybit total:      ${bybit_bal['total']:.2f}")
        print(f"    Bot DB balances:  ${all_db_balance:.2f}")
        # Each strategy uses same Bybit account, so compare Bybit vs
        # sum_of_initial + real exchange PnL
        # Note: all strategies share one exchange account
        diff = bybit_bal['total'] - all_db_balance
        if strategy_count > 1:
            print(f"    NOTE: {strategy_count} strategies share 1 Bybit account!")
            print(f"    Bybit holds real $ for all strategies combined.")
            print(f"    Difference (Bybit - sum of DB balances): ${diff:+.2f}")
        else:
            print(f"    Difference: ${diff:+.2f}")

    print(f"\n{'=' * 70}")
    print(f"  DONE")
    print(f"{'=' * 70}")


if __name__ == '__main__':
    main()
