import unittest
import numpy as np
from scalper.indicators import calc_ema, calc_rsi, calc_atr, calc_adx, calc_volume_ratio


def _make_ohlcv(n=100):
    """Generate sinusoidal OHLCV test data."""
    np.random.seed(42)
    t = np.linspace(0, 4 * np.pi, n)
    base = 100 + 10 * np.sin(t) + np.random.randn(n) * 0.5
    high = base + np.abs(np.random.randn(n)) * 1.5
    low = base - np.abs(np.random.randn(n)) * 1.5
    close = base + np.random.randn(n) * 0.3
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    volume = 1000 + 500 * np.abs(np.sin(t)) + np.random.randn(n) * 50
    volume = np.maximum(volume, 10)
    return open_, high, low, close, volume


class TestEMA(unittest.TestCase):
    def test_length(self):
        _, _, _, close, _ = _make_ohlcv()
        ema = calc_ema(close, 14)
        self.assertEqual(len(ema), len(close))

    def test_smoothing(self):
        """EMA should be smoother than raw close prices."""
        _, _, _, close, _ = _make_ohlcv()
        ema = calc_ema(close, 14)
        valid = ~np.isnan(ema)
        ema_diffs = np.diff(ema[valid])
        close_diffs = np.diff(close[valid])
        self.assertLess(np.std(ema_diffs), np.std(close_diffs))


class TestRSI(unittest.TestCase):
    def test_range(self):
        _, _, _, close, _ = _make_ohlcv()
        rsi = calc_rsi(close, 14)
        valid = rsi[~np.isnan(rsi)]
        self.assertTrue(np.all(valid >= 0))
        self.assertTrue(np.all(valid <= 100))

    def test_length(self):
        _, _, _, close, _ = _make_ohlcv()
        rsi = calc_rsi(close, 14)
        self.assertEqual(len(rsi), len(close))


class TestATR(unittest.TestCase):
    def test_positive(self):
        _, high, low, close, _ = _make_ohlcv()
        atr = calc_atr(high, low, close, 14)
        valid = atr[~np.isnan(atr)]
        self.assertTrue(np.all(valid > 0))

    def test_length(self):
        _, high, low, close, _ = _make_ohlcv()
        atr = calc_atr(high, low, close, 14)
        self.assertEqual(len(atr), len(close))


class TestADX(unittest.TestCase):
    def test_range(self):
        _, high, low, close, _ = _make_ohlcv()
        adx = calc_adx(high, low, close, 14)
        valid = adx[~np.isnan(adx)]
        self.assertTrue(np.all(valid >= 0))
        self.assertTrue(np.all(valid <= 100))

    def test_length(self):
        _, high, low, close, _ = _make_ohlcv()
        adx = calc_adx(high, low, close, 14)
        self.assertEqual(len(adx), len(close))


class TestVolumeRatio(unittest.TestCase):
    def test_ratio(self):
        _, _, _, _, volume = _make_ohlcv()
        vr = calc_volume_ratio(volume, 20)
        valid = vr[~np.isnan(vr)]
        self.assertTrue(len(valid) > 0)
        self.assertTrue(np.all(valid > 0))
        self.assertEqual(len(vr), len(volume))


if __name__ == "__main__":
    unittest.main()
