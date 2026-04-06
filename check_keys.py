"""Check all Bybit API keys from .env"""
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
    ("DEMO8", "BYBIT_API_KEY_DEMO8", "BYBIT_API_SECRET_DEMO8"),
    ("DEMO9", "BYBIT_API_KEY_DEMO9", "BYBIT_API_SECRET_DEMO9"),
    ("DEMO10", "BYBIT_API_KEY_DEMO10", "BYBIT_API_SECRET_DEMO10"),
    ("DEMO11", "BYBIT_API_KEY_DEMO11", "BYBIT_API_SECRET_DEMO11"),
    ("DEMO12", "BYBIT_API_KEY_DEMO12", "BYBIT_API_SECRET_DEMO12"),
]

ok = 0
fail = 0

for name, key_env, secret_env in ACCOUNTS:
    api_key = os.getenv(key_env, "")
    api_secret = os.getenv(secret_env, "")
    if not api_key or not api_secret:
        print(f"  {name:20s} MISSING key or secret")
        fail += 1
        continue
    try:
        ex = ccxt.bybit({
            "apiKey": api_key,
            "secret": api_secret,
            "options": {"defaultType": "swap"},
            "enableRateLimit": True,
        })
        ex.enable_demo_trading(True)
        bal = ex.fetch_balance()
        usdt = float(bal.get("USDT", {}).get("total", 0))
        print(f"  {name:20s} OK    ${usdt:.2f}")
        ok += 1
    except Exception as e:
        err = str(e).split("\n")[0][:60]
        print(f"  {name:20s} FAIL  {err}")
        fail += 1

print(f"\nResult: {ok} OK, {fail} FAIL")
