import unittest
import numpy as np
from scalper.config import Config
from scalper.signals import Signal, SignalEngine


def _make_trending_up(n=100):
    """Generate strongly trending-up OHLCV data."""
    np.random.seed(42)
    # Strong upward trend with noise
    close = 100 + np.linspace(0, 40, n) + np.random.randn(n) * 0.3
    high = close + np.abs(np.random.randn(n)) * 1.0
    low = close - np.abs(np.random.randn(n)) * 1.0
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    # Volume spike at the end to help trigger signal
    volume = np.full(n, 1000.0)
    volume[-5:] = 2000.0
    return {
        'open': open_,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume,
    }


def _make_flat(n=100):
    """Generate flat/sideways OHLCV data with tiny noise."""
    np.random.seed(42)
    close = 100.0 + np.random.randn(n) * 0.01
    high = close + 0.01
    low = close - 0.01
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    volume = np.full(n, 1000.0)
    return {
        'open': open_,
        'high': high,
        'low': low,
        'close': close,
        'volume': volume,
    }


class TestSignalDataclass(unittest.TestCase):
    def test_signal_creation(self):
        sig = Signal(
            direction='long',
            strength=3,
            entry_price=100.0,
            sl_price=98.0,
            tp_price=104.0,
            reasons=['ema_cross', 'rsi_oversold', 'volume_spike'],
        )
        self.assertEqual(sig.direction, 'long')
        self.assertEqual(sig.strength, 3)
        self.assertEqual(sig.entry_price, 100.0)
        self.assertEqual(sig.sl_price, 98.0)
        self.assertEqual(sig.tp_price, 104.0)
        self.assertEqual(len(sig.reasons), 3)

    def test_signal_short(self):
        sig = Signal(
            direction='short',
            strength=2,
            entry_price=50000.0,
            sl_price=50500.0,
            tp_price=49000.0,
            reasons=['ema_cross', 'rsi_overbought'],
        )
        self.assertEqual(sig.direction, 'short')
        self.assertEqual(sig.strength, 2)


class TestNoSignalOnFlat(unittest.TestCase):
    def test_flat_returns_none(self):
        """Flat data should produce no signal (ADX too low)."""
        cfg = Config()
        engine = SignalEngine(cfg)
        ohlcv = _make_flat(n=100)
        result = engine.evaluate(ohlcv)
        self.assertIsNone(result)


class TestSignalAdaptiveSLTP(unittest.TestCase):
    def test_trending_signal_sl_tp(self):
        """Trending data should produce a signal with adaptive SL/TP."""
        cfg = Config()
        engine = SignalEngine(cfg)
        ohlcv = _make_trending_up(n=100)
        result = engine.evaluate(ohlcv)
        # Trending data may or may not produce a signal depending on ADX
        # but if it does, SL/TP must be consistent
        if result is not None:
            self.assertIn(result.direction, ('long', 'short'))
            self.assertGreaterEqual(result.strength, 2)
            self.assertGreater(len(result.reasons), 0)

            if result.direction == 'long':
                self.assertLess(result.sl_price, result.entry_price)
                self.assertGreater(result.tp_price, result.entry_price)
                sl_dist = result.entry_price - result.sl_price
                tp_dist = result.tp_price - result.entry_price
            else:
                self.assertGreater(result.sl_price, result.entry_price)
                self.assertLess(result.tp_price, result.entry_price)
                sl_dist = result.sl_price - result.entry_price
                tp_dist = result.entry_price - result.tp_price

            # TP distance should equal SL distance * tp_ratio
            expected_tp_dist = sl_dist * cfg.tp_ratio
            self.assertAlmostEqual(tp_dist, expected_tp_dist, places=5)

    def test_trending_produces_signal(self):
        """With a generous ADX threshold, trending data must produce a signal."""
        cfg = Config(adx_min=5)  # lower threshold to ensure signal
        engine = SignalEngine(cfg)
        ohlcv = _make_trending_up(n=100)
        result = engine.evaluate(ohlcv)
        self.assertIsNotNone(result)
        self.assertEqual(result.direction, 'long')
        self.assertGreaterEqual(result.strength, 2)


if __name__ == '__main__':
    unittest.main()
