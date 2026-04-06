"""Close all positions on ALL sub-accounts."""
import os
from dotenv import load_dotenv
import ccxt

load_dotenv()

ACCOUNTS = [
    ("Global", "BYBIT_API_KEY", "BYBIT_API_SECRET"),
    ("DEFAULT", "BYBIT_API_KEY_DEFAULT", "BYBIT_API_SECRET_DEFAULT"),
    ("TREND_RIDER", "BYBIT_API_KEY_TREND_RIDER", "BYBIT_API_SECRET_TREND_RIDER"),
    ("BREAKOUT", "BYBIT_API_KEY_BREAKOUT", "BYBIT_API_SECRET_BREAKOUT"),
    ("SCALP_REVERSAL", "BYBIT_API_KEY_SCALP_REVERSAL", "BYBIT_API_SECRET_SCALP_REVERSAL"),
    ("VWAP_BOUNCE", "BYBIT_API_KEY_VWAP_BOUNCE", "BYBIT_API_SECRET_VWAP_BOUNCE"),
    ("EMA_RETEST", "BYBIT_API_KEY_EMA_RETEST", "BYBIT_API_SECRET_EMA_RETEST"),
    ("DONCHIAN_BREAKOUT", "BYBIT_API_KEY_DONCHIAN_BREAKOUT", "BYBIT_API_SECRET_DONCHIAN_BREAKOUT"),
    ("VWAP_REVERSION", "BYBIT_API_KEY_VWAP_REVERSION", "BYBIT_API_SECRET_VWAP_REVERSION"),
]

total_closed = 0

for name, key_env, sec_env in ACCOUNTS:
    k = os.getenv(key_env, "")
    s = os.getenv(sec_env, "")
    if not k or not s:
        continue

    ex = ccxt.bybit({
        "apiKey": k, "secret": s,
        "options": {"defaultType": "swap"},
        "enableRateLimit": True,
    })
    ex.enable_demo_trading(True)
    ex.load_markets()

    positions = ex.fetch_positions()
    opens = [p for p in positions if p["contracts"] and p["contracts"] > 0]

    if not opens:
        print(f"  {name:20s} clean")
        continue

    print(f"  {name:20s} closing {len(opens)} positions...")
    for p in opens:
        sym = p["symbol"]
        side = "sell" if p["side"] == "long" else "buy"
        qty = float(ex.amount_to_precision(sym, p["contracts"]))
        try:
            ex.create_order(sym, "market", side, qty, params={"reduceOnly": True})
            print(f"    {sym} {p['side']} qty={qty} - CLOSED")
            total_closed += 1
        except Exception as e:
            print(f"    {sym} - FAIL: {str(e)[:50]}")

print(f"\nTotal closed: {total_closed}")
