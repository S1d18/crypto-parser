"""Tests for scalper.filters — TrendFilter."""

import numpy as np
import pytest

from scalper.filters import TrendFilter


def _make_ohlcv(close: np.ndarray) -> dict[str, np.ndarray]:
    """Build minimal ohlcv_senior dict from close prices."""
    return {
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": np.ones_like(close),
    }


class TestTrendFilter:
    def setup_method(self):
        self.tf = TrendFilter(ema_fast=9, ema_slow=21)

    def test_uptrend_allows_long(self):
        # Linear uptrend: fast EMA will be above slow EMA
        close = np.linspace(100.0, 200.0, 100)
        ohlcv = _make_ohlcv(close)

        assert self.tf.is_allowed("long", ohlcv) is True
        assert self.tf.is_allowed("short", ohlcv) is False

    def test_downtrend_allows_short(self):
        # Linear downtrend: fast EMA will be below slow EMA
        close = np.linspace(200.0, 100.0, 100)
        ohlcv = _make_ohlcv(close)

        assert self.tf.is_allowed("short", ohlcv) is True
        assert self.tf.is_allowed("long", ohlcv) is False

    def test_insufficient_data(self):
        # Not enough data for slow EMA (period=21 needs at least 21 points)
        close = np.linspace(100.0, 110.0, 10)
        ohlcv = _make_ohlcv(close)

        assert self.tf.is_allowed("long", ohlcv) is False
        assert self.tf.is_allowed("short", ohlcv) is False

    def test_invalid_direction(self):
        close = np.linspace(100.0, 200.0, 100)
        ohlcv = _make_ohlcv(close)

        assert self.tf.is_allowed("sideways", ohlcv) is False
