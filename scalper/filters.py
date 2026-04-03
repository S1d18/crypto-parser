"""Trend filters — prevent trading against the senior timeframe trend."""

import numpy as np

from scalper.indicators import calc_ema


class TrendFilter:
    """EMA crossover filter on senior timeframe.

    Long allowed only when EMA_fast > EMA_slow (uptrend).
    Short allowed only when EMA_fast < EMA_slow (downtrend).
    """

    def __init__(self, ema_fast: int = 9, ema_slow: int = 21) -> None:
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow

    def is_allowed(self, direction: str, ohlcv_senior: dict[str, np.ndarray]) -> bool:
        """Check if *direction* is allowed based on senior TF trend.

        Returns False if insufficient data, NaN values, or unknown direction.
        """
        if direction not in ("long", "short"):
            return False

        close = ohlcv_senior.get("close")
        if close is None or len(close) < self.ema_slow:
            return False

        fast = calc_ema(close, self.ema_fast)
        slow = calc_ema(close, self.ema_slow)

        last_fast = fast[-1]
        last_slow = slow[-1]

        if np.isnan(last_fast) or np.isnan(last_slow):
            return False

        if direction == "long":
            return bool(last_fast > last_slow)
        else:  # short
            return bool(last_fast < last_slow)
