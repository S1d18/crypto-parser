from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from scalper.config import Config
from scalper.risk import RiskManager, TrailingStop


class TestTrailingStop(unittest.TestCase):
    def test_trailing_long(self):
        ts = TrailingStop(direction="long", entry=100.0, sl=97.0)
        # distance = 3.0, initial sl = 97.0

        # Price goes up -> sl should move up
        new_sl = ts.update(105.0)
        self.assertAlmostEqual(new_sl, 102.0)  # 105 - 3

        # Price goes down -> sl stays at 102
        new_sl = ts.update(103.0)
        self.assertAlmostEqual(new_sl, 102.0)

        # Price goes further up
        new_sl = ts.update(110.0)
        self.assertAlmostEqual(new_sl, 107.0)

    def test_trailing_short(self):
        ts = TrailingStop(direction="short", entry=100.0, sl=103.0)
        # distance = 3.0, initial sl = 103.0

        # Price goes down -> sl should move down
        new_sl = ts.update(95.0)
        self.assertAlmostEqual(new_sl, 98.0)  # 95 + 3

        # Price goes up -> sl stays at 98
        new_sl = ts.update(97.0)
        self.assertAlmostEqual(new_sl, 98.0)

        # Price goes further down
        new_sl = ts.update(90.0)
        self.assertAlmostEqual(new_sl, 93.0)

    def test_is_hit_long(self):
        ts = TrailingStop(direction="long", entry=100.0, sl=97.0)
        self.assertFalse(ts.is_hit(100.0))
        self.assertTrue(ts.is_hit(97.0))
        self.assertTrue(ts.is_hit(95.0))

    def test_is_hit_short(self):
        ts = TrailingStop(direction="short", entry=100.0, sl=103.0)
        self.assertFalse(ts.is_hit(100.0))
        self.assertTrue(ts.is_hit(103.0))
        self.assertTrue(ts.is_hit(105.0))


class TestPositionSize(unittest.TestCase):
    def test_position_size(self):
        cfg = Config(balance=200.0, leverage=20, max_risk_per_trade=0.5, max_open_positions=10)
        rm = RiskManager(cfg)
        result = rm.calc_position_size(price=50000.0, confidence=100)

        # margin = 200 * 0.15 * 1.0 (conf>=90) = 30.0
        self.assertAlmostEqual(result['margin'], 30.0, places=2)
        # position_value = 30 * 20 = 600
        self.assertAlmostEqual(result['position_value'], 600.0, places=2)
        # qty = 600 / 50000
        self.assertAlmostEqual(result['qty'], 600.0 / 50000, places=6)


class TestConsecutiveLosses(unittest.TestCase):
    def test_no_pause_initially(self):
        cfg = Config(max_consecutive_losses=10, pause_after_losses_minutes=60)
        rm = RiskManager(cfg)
        self.assertFalse(rm.should_pause())

    def test_pause_after_10_losses(self):
        cfg = Config(max_consecutive_losses=10, pause_after_losses_minutes=60)
        rm = RiskManager(cfg)
        for _ in range(10):
            rm.record_loss()
        self.assertTrue(rm.should_pause())

    def test_reset_on_win(self):
        cfg = Config(max_consecutive_losses=10, pause_after_losses_minutes=60)
        rm = RiskManager(cfg)
        for _ in range(9):
            rm.record_loss()
        self.assertFalse(rm.should_pause())
        rm.record_win()
        self.assertFalse(rm.should_pause())
        # After win, counter is 0 — need 10 more losses to pause
        for _ in range(9):
            rm.record_loss()
        self.assertFalse(rm.should_pause())


class TestDailyLimit(unittest.TestCase):
    def test_daily_loss_stop(self):
        cfg = Config(max_daily_loss=30.0)
        rm = RiskManager(cfg)
        rm.record_daily_pnl(-30.0)
        self.assertTrue(rm.is_daily_limit_hit())

    def test_daily_ok(self):
        cfg = Config(max_daily_loss=30.0)
        rm = RiskManager(cfg)
        rm.record_daily_pnl(-15.0)
        self.assertFalse(rm.is_daily_limit_hit())

    def test_can_trade_combines_checks(self):
        cfg = Config(max_daily_loss=30.0, max_consecutive_losses=10)
        rm = RiskManager(cfg)
        self.assertTrue(rm.can_trade())
        rm.record_daily_pnl(-30.0)
        self.assertFalse(rm.can_trade())

    def test_daily_reset_on_new_day(self):
        cfg = Config(max_daily_loss=30.0, max_consecutive_losses=10)
        rm = RiskManager(cfg)
        rm.record_daily_pnl(-30.0)
        self.assertFalse(rm.can_trade())

        # Simulate a new day by changing last_reset_date
        rm.last_reset_date = (datetime.now() - timedelta(days=1)).date()
        self.assertTrue(rm.can_trade())


if __name__ == '__main__':
    unittest.main()
