import os
import sys
import time
from functools import lru_cache

from flask import Blueprint, jsonify, request

# Добавляем корень проекта в path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, PROJECT_ROOT)

from strategy20.paper_storage import PaperTradeStorage
from strategy20.strategies import PAPER_STRATEGIES

api = Blueprint("api", __name__)

# Ленивая инициализация storage
_storage = None


def get_storage() -> PaperTradeStorage:
    global _storage
    if _storage is None:
        db_path = os.path.join(PROJECT_ROOT, "trades.db")
        _storage = PaperTradeStorage(db_path)
    return _storage


# Индекс стратегий для быстрого поиска
STRATEGIES_MAP = {s.strategy_id: s for s in PAPER_STRATEGIES}

# Кеш свечей
_candles_cache: dict[str, tuple[float, list]] = {}
CANDLE_CACHE_TTL = 60  # секунд

# Кеш текущей цены
_price_cache: tuple[float, float] = (0.0, 0.0)  # (timestamp, price)
PRICE_CACHE_TTL = 30  # секунд


def _get_current_price() -> float | None:
    """Получить текущую цену BTC с кешированием."""
    global _price_cache
    now = time.time()
    cached_time, cached_price = _price_cache
    if cached_price > 0 and now - cached_time < PRICE_CACHE_TTL:
        return cached_price
    try:
        import ccxt
        exchange = ccxt.bybit({
            "options": {"defaultType": "swap"},
            "enableRateLimit": True,
        })
        ticker = exchange.fetch_ticker("BTC/USDT:USDT")
        price = ticker["last"]
        _price_cache = (now, price)
        return price
    except Exception:
        return cached_price if cached_price > 0 else None


@api.route("/strategies")
def strategies_list():
    storage = get_storage()
    summary = storage.get_all_strategies_summary()
    summary_map = {s["strategy_id"]: s for s in summary}

    # Открытые позиции
    open_trades = storage.get_open_trades()
    open_map = {}
    for t in open_trades:
        open_map[t["strategy_id"]] = t

    # Текущая цена для расчёта unrealized PnL
    current_price = _get_current_price()

    result = []
    for s in PAPER_STRATEGIES:
        stats = summary_map.get(s.strategy_id, {})
        ot = open_map.get(s.strategy_id)

        # Расчёт unrealized PnL для открытой позиции
        open_pnl_live = None
        open_pnl_live_pct = None
        if ot and current_price:
            entry = ot["entry_price"]
            side = ot["side"]
            qty = ot["qty"]
            if side == "buy":
                open_pnl_live = round((current_price - entry) * qty, 2)
            else:
                open_pnl_live = round((entry - current_price) * qty, 2)
            open_pnl_live_pct = round(open_pnl_live / s.virtual_balance * 100, 2)

        result.append({
            "strategy_id": s.strategy_id,
            "group": s.group,
            "timeframe": s.timeframe,
            "direction": s.direction,
            "st_period": s.st_period,
            "st_multiplier": s.st_multiplier,
            "sl_percent": s.sl_percent,
            "virtual_balance": s.virtual_balance,
            "total_trades": stats.get("total_trades", 0),
            "wins": stats.get("wins", 0),
            "losses": stats.get("losses", 0),
            "win_rate": round(stats["wins"] / stats["total_trades"] * 100, 1)
                if stats.get("total_trades", 0) > 0 else 0.0,
            "total_pnl": stats.get("total_pnl", 0.0),
            "total_pnl_pct": stats.get("total_pnl_pct", 0.0),
            "profit_factor": stats.get("profit_factor", 0.0),
            "has_open_position": ot is not None,
            "open_side": ot["side"] if ot else None,
            "open_entry_price": ot["entry_price"] if ot else None,
            "open_sl_price": ot["sl_price"] if ot else None,
            "open_opened_at": ot["opened_at"] if ot else None,
            "open_pnl_live": open_pnl_live,
            "open_pnl_live_pct": open_pnl_live_pct,
            "current_price": current_price,
        })

    return jsonify(result)


@api.route("/strategy/<strategy_id>/stats")
def strategy_stats(strategy_id):
    if strategy_id not in STRATEGIES_MAP:
        return jsonify({"error": "Strategy not found"}), 404
    storage = get_storage()
    stats = storage.get_strategy_stats(strategy_id)
    config = STRATEGIES_MAP[strategy_id]
    stats["config"] = {
        "strategy_id": config.strategy_id,
        "group": config.group,
        "timeframe": config.timeframe,
        "direction": config.direction,
        "st_period": config.st_period,
        "st_multiplier": config.st_multiplier,
        "sl_percent": config.sl_percent,
        "virtual_balance": config.virtual_balance,
    }

    # Текущая цена и unrealized PnL
    current_price = _get_current_price()
    stats["current_price"] = current_price
    if stats.get("open_trade") and current_price:
        ot = stats["open_trade"]
        entry = ot["entry_price"]
        side = ot["side"]
        qty = ot["qty"]
        if side == "buy":
            upnl = round((current_price - entry) * qty, 2)
        else:
            upnl = round((entry - current_price) * qty, 2)
        stats["open_pnl_live"] = upnl
        stats["open_pnl_live_pct"] = round(upnl / config.virtual_balance * 100, 2)
    else:
        stats["open_pnl_live"] = None
        stats["open_pnl_live_pct"] = None

    return jsonify(stats)


@api.route("/strategy/<strategy_id>/trades")
def strategy_trades(strategy_id):
    if strategy_id not in STRATEGIES_MAP:
        return jsonify({"error": "Strategy not found"}), 404
    storage = get_storage()
    limit = request.args.get("limit", 100, type=int)
    offset = request.args.get("offset", 0, type=int)
    trades = storage.get_trade_history(strategy_id=strategy_id, limit=limit, offset=offset)
    return jsonify(trades)


@api.route("/strategy/<strategy_id>/equity")
def strategy_equity(strategy_id):
    if strategy_id not in STRATEGIES_MAP:
        return jsonify({"error": "Strategy not found"}), 404
    storage = get_storage()
    curve = storage.get_equity_curve(strategy_id)
    return jsonify(curve)


@api.route("/strategy/<strategy_id>/candles")
def strategy_candles(strategy_id):
    """Возвращает OHLCV данные для графика. Кеширует на 60с."""
    if strategy_id not in STRATEGIES_MAP:
        return jsonify({"error": "Strategy not found"}), 404

    config = STRATEGIES_MAP[strategy_id]
    tf = config.timeframe
    cache_key = tf

    now = time.time()
    if cache_key in _candles_cache:
        cached_time, cached_data = _candles_cache[cache_key]
        if now - cached_time < CANDLE_CACHE_TTL:
            return jsonify(cached_data)

    # Загружаем свечи через ccxt
    try:
        import ccxt
        from config import Config
        cfg = Config.from_env()
        exchange = ccxt.bybit({
            "options": {"defaultType": "swap"},
            "enableRateLimit": True,
        })
        ohlcv = exchange.fetch_ohlcv(cfg.symbol, timeframe=tf, limit=200)
        candles = []
        for c in ohlcv:
            candles.append({
                "time": int(c[0] / 1000),
                "open": c[1],
                "high": c[2],
                "low": c[3],
                "close": c[4],
                "volume": c[5],
            })
        _candles_cache[cache_key] = (now, candles)
        return jsonify(candles)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
