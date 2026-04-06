"""Check SL/TP on all sub-account positions."""
import os
from dotenv import load_dotenv
import ccxt

load_dotenv()

ACCOUNTS = [
    ("DEFAULT", "BYBIT_API_KEY_DEFAULT", "BYBIT_API_SECRET_DEFAULT"),
    ("TREND_RIDER", "BYBIT_API_KEY_TREND_RIDER", "BYBIT_API_SECRET_TREND_RIDER"),
    ("BREAKOUT", "BYBIT_API_KEY_BREAKOUT", "BYBIT_API_SECRET_BREAKOUT"),
    ("SCALP_REVERSAL", "BYBIT_API_KEY_SCALP_REVERSAL", "BYBIT_API_SECRET_SCALP_REVERSAL"),
    ("VWAP_BOUNCE", "BYBIT_API_KEY_VWAP_BOUNCE", "BYBIT_API_SECRET_VWAP_BOUNCE"),
    ("EMA_RETEST", "BYBIT_API_KEY_EMA_RETEST", "BYBIT_API_SECRET_EMA_RETEST"),
    ("DONCHIAN_BREAKOUT", "BYBIT_API_KEY_DONCHIAN_BREAKOUT", "BYBIT_API_SECRET_DONCHIAN_BREAKOUT"),
    ("VWAP_REVERSION", "BYBIT_API_KEY_VWAP_REVERSION", "BYBIT_API_SECRET_VWAP_REVERSION"),
]

for name, ke, se in ACCOUNTS:
    k = os.getenv(ke, "")
    s = os.getenv(se, "")
    if not k:
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
        print(f"  {name:20s} no positions")
        continue
    for p in opens:
        info = p.get("info", {})
        sl = info.get("stopLoss", "0")
        tp = info.get("takeProfit", "0")
        sym = p["symbol"]
        side = p["side"]
        pnl = p.get("unrealizedPnl", 0)
        sl_ok = "OK" if sl and sl != "0" else "MISSING!"
        tp_ok = "OK" if tp and tp != "0" else "MISSING!"
        print(f"  {name:20s} {sym:25s} {side:5s} "
              f"SL={sl:>12s} [{sl_ok}]  TP={tp:>12s} [{tp_ok}]  "
              f"uPnL={float(pnl):+.2f}")
