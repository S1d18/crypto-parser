"""Tests for scalper.bot module."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scalper.config import Config
from scalper.signals import Signal


@pytest.fixture
def config():
    return Config(
        balance=200.0,
        leverage=20,
        max_risk_per_trade=0.5,
        taker_fee=0.00055,
        scan_interval=30,
    )


def _make_signal(direction='long', strength=3, entry=100.0, sl=98.0, tp=104.0):
    return Signal(
        direction=direction,
        strength=strength,
        entry_price=entry,
        sl_price=sl,
        tp_price=tp,
        reasons=['ema_cross', 'momentum', 'volume_spike'],
    )


class TestBotOpensTrade:
    """Signal found -> trade opened in storage."""

    def test_bot_opens_trade(self, config):
        from scalper.bot import ScalperBot

        bot = ScalperBot(config)

        # Mock exchange
        bot._exchange = AsyncMock()
        bot._exchange.start = AsyncMock()
        bot._exchange.close = AsyncMock()
        bot._exchange.get_price = AsyncMock(return_value=100.0)

        # Mock scanner returns one opportunity
        sig = _make_signal()
        bot._scanner = AsyncMock()
        bot._scanner.scan = AsyncMock(return_value=[
            {'symbol': 'BTC/USDT:USDT', 'signal': sig, 'price': 100.0},
        ])

        # Mock risk manager
        bot._risk = MagicMock()
        bot._risk.can_trade.return_value = True
        bot._risk.calc_position_size.return_value = {
            'qty': 20.0, 'margin': 100.0, 'position_value': 2000.0,
        }
        bot._risk.create_trailing_stop.return_value = MagicMock()

        # Mock storage
        bot._storage = MagicMock()
        bot._storage.get_open_trades.return_value = []
        bot._storage.open_trade.return_value = 1  # trade_id

        # Run one tick
        asyncio.get_event_loop().run_until_complete(bot.tick())

        # Verify trade was opened
        bot._storage.open_trade.assert_called_once()
        call_kwargs = bot._storage.open_trade.call_args
        # Check positional or keyword args contain the symbol
        args, kwargs = call_kwargs
        assert kwargs.get('symbol', args[0] if args else None) == 'BTC/USDT:USDT'

    def test_bot_opens_trade_with_correct_direction(self, config):
        from scalper.bot import ScalperBot

        bot = ScalperBot(config)
        bot._exchange = AsyncMock()
        bot._exchange.get_price = AsyncMock(return_value=50.0)

        sig = _make_signal(direction='short', entry=50.0, sl=52.0, tp=46.0)
        bot._scanner = AsyncMock()
        bot._scanner.scan = AsyncMock(return_value=[
            {'symbol': 'ETH/USDT:USDT', 'signal': sig, 'price': 50.0},
        ])

        bot._risk = MagicMock()
        bot._risk.can_trade.return_value = True
        bot._risk.calc_position_size.return_value = {
            'qty': 40.0, 'margin': 100.0, 'position_value': 2000.0,
        }
        bot._risk.create_trailing_stop.return_value = MagicMock()

        bot._storage = MagicMock()
        bot._storage.get_open_trades.return_value = []
        bot._storage.open_trade.return_value = 1

        asyncio.get_event_loop().run_until_complete(bot.tick())

        call_args = bot._storage.open_trade.call_args
        assert call_args.kwargs.get('direction') == 'short'


class TestBotSkipsWhenPaused:
    """can_trade=False -> scanner not called."""

    def test_bot_skips_when_paused(self, config):
        from scalper.bot import ScalperBot

        bot = ScalperBot(config)
        bot._exchange = AsyncMock()
        bot._exchange.get_price = AsyncMock(return_value=100.0)

        bot._scanner = AsyncMock()
        bot._scanner.scan = AsyncMock(return_value=[])

        bot._risk = MagicMock()
        bot._risk.can_trade.return_value = False

        bot._storage = MagicMock()
        bot._storage.get_open_trades.return_value = []

        asyncio.get_event_loop().run_until_complete(bot.tick())

        # Scanner should NOT be called when risk says can't trade
        bot._scanner.scan.assert_not_called()

    def test_bot_skips_when_has_open_position(self, config):
        from scalper.bot import ScalperBot

        bot = ScalperBot(config)
        bot._exchange = AsyncMock()
        bot._exchange.get_price = AsyncMock(return_value=100.0)

        bot._scanner = AsyncMock()

        bot._risk = MagicMock()
        bot._risk.can_trade.return_value = True

        # Already have an open position
        bot._storage = MagicMock()
        bot._storage.get_open_trades.return_value = []
        bot._open_positions = {
            1: {'trade': {'id': 1, 'symbol': 'BTC/USDT:USDT', 'direction': 'long',
                          'entry_price': 100.0, 'sl_price': 98.0, 'tp_price': 104.0,
                          'qty': 20.0, 'leverage': 20, 'margin': 100.0},
                'trailing': MagicMock(update=MagicMock(return_value=98.0),
                                      is_hit=MagicMock(return_value=False))},
        }

        asyncio.get_event_loop().run_until_complete(bot.tick())

        # Scanner should NOT be called when already have open position
        bot._scanner.scan.assert_not_called()


class TestBotClosesOnSL:
    """Open position, price drops below SL -> closed."""

    def test_bot_closes_long_on_sl(self, config):
        from scalper.bot import ScalperBot

        bot = ScalperBot(config)
        bot._exchange = AsyncMock()
        # Price dropped below SL
        bot._exchange.get_price = AsyncMock(return_value=95.0)

        bot._scanner = AsyncMock()
        bot._risk = MagicMock()
        bot._risk.can_trade.return_value = True

        bot._storage = MagicMock()
        bot._storage.get_open_trades.return_value = []

        # Set up an open position with trailing stop
        trailing = MagicMock()
        trailing.update.return_value = 98.0
        trailing.is_hit.return_value = True  # SL hit

        trade = {
            'id': 1,
            'symbol': 'BTC/USDT:USDT',
            'direction': 'long',
            'qty': 20.0,
            'entry_price': 100.0,
            'sl_price': 98.0,
            'tp_price': 104.0,
            'leverage': 20,
            'margin': 100.0,
        }
        bot._open_positions = {1: {'trade': trade, 'trailing': trailing}}

        asyncio.get_event_loop().run_until_complete(bot.tick())

        # Verify trade was closed
        bot._storage.close_trade.assert_called_once()
        call_kwargs = bot._storage.close_trade.call_args.kwargs
        assert call_kwargs['trade_id'] == 1
        assert call_kwargs['close_reason'] == 'sl'
        # PnL for long: (95 - 100) * 20 = -100, minus fees
        assert call_kwargs['pnl'] < 0

    def test_bot_closes_short_on_sl(self, config):
        from scalper.bot import ScalperBot

        bot = ScalperBot(config)
        bot._exchange = AsyncMock()
        # Price went above SL for short
        bot._exchange.get_price = AsyncMock(return_value=55.0)

        bot._scanner = AsyncMock()
        bot._risk = MagicMock()
        bot._risk.can_trade.return_value = True

        bot._storage = MagicMock()
        bot._storage.get_open_trades.return_value = []

        trailing = MagicMock()
        trailing.update.return_value = 52.0
        trailing.is_hit.return_value = True

        trade = {
            'id': 2,
            'symbol': 'ETH/USDT:USDT',
            'direction': 'short',
            'qty': 40.0,
            'entry_price': 50.0,
            'sl_price': 52.0,
            'tp_price': 46.0,
            'leverage': 20,
            'margin': 100.0,
        }
        bot._open_positions = {2: {'trade': trade, 'trailing': trailing}}

        asyncio.get_event_loop().run_until_complete(bot.tick())

        bot._storage.close_trade.assert_called_once()
        call_kwargs = bot._storage.close_trade.call_args.kwargs
        assert call_kwargs['trade_id'] == 2
        assert call_kwargs['close_reason'] == 'sl'
        # Short PnL: (50 - 55) * 40 = -200, minus fees
        assert call_kwargs['pnl'] < 0

    def test_bot_closes_on_tp(self, config):
        from scalper.bot import ScalperBot

        bot = ScalperBot(config)
        bot._exchange = AsyncMock()
        # Price hit TP for long
        bot._exchange.get_price = AsyncMock(return_value=105.0)

        bot._scanner = AsyncMock()
        bot._risk = MagicMock()
        bot._risk.can_trade.return_value = True

        bot._storage = MagicMock()
        bot._storage.get_open_trades.return_value = []

        trailing = MagicMock()
        trailing.update.return_value = 99.0
        trailing.is_hit.return_value = False  # SL not hit

        trade = {
            'id': 3,
            'symbol': 'BTC/USDT:USDT',
            'direction': 'long',
            'qty': 20.0,
            'entry_price': 100.0,
            'sl_price': 98.0,
            'tp_price': 104.0,
            'leverage': 20,
            'margin': 100.0,
        }
        bot._open_positions = {3: {'trade': trade, 'trailing': trailing}}

        asyncio.get_event_loop().run_until_complete(bot.tick())

        bot._storage.close_trade.assert_called_once()
        call_kwargs = bot._storage.close_trade.call_args.kwargs
        assert call_kwargs['trade_id'] == 3
        assert call_kwargs['close_reason'] == 'tp'
        assert call_kwargs['pnl'] > 0


class TestBotCallbacks:
    """Test notification callbacks."""

    def test_on_update_callback(self, config):
        from scalper.bot import ScalperBot

        bot = ScalperBot(config)
        events = []

        bot.on_update(lambda event, data: events.append((event, data)))
        bot._notify('test_event', {'key': 'value'})

        assert len(events) == 1
        assert events[0] == ('test_event', {'key': 'value'})


class TestBotGetStatus:
    """Test get_status method."""

    def test_get_status(self, config):
        from scalper.bot import ScalperBot

        bot = ScalperBot(config)
        bot._risk = MagicMock()
        bot._risk.can_trade.return_value = True

        bot._storage = MagicMock()
        bot._storage.get_daily_stats.return_value = {
            'total_trades': 5, 'total_pnl': 10.0,
            'wins': 3, 'losses': 2, 'win_rate': 60.0,
        }
        bot._storage.get_all_stats.return_value = {
            'total_trades': 100, 'total_pnl': 50.0,
            'wins': 60, 'losses': 40, 'win_rate': 60.0,
        }

        bot._running = True

        status = bot.get_status()

        assert status['running'] is True
        assert status['balance'] == 200.0
        assert status['open_positions'] == 0
        assert status['can_trade'] is True
        assert 'daily_stats' in status
        assert 'all_stats' in status


class TestBotRecoverPositions:
    """Test recovery of open positions from DB on start."""

    def test_start_recovers_open_positions(self, config):
        from scalper.bot import ScalperBot

        bot = ScalperBot(config)
        bot._exchange = AsyncMock()
        bot._exchange.start = AsyncMock()

        bot._risk = MagicMock()
        bot._risk.create_trailing_stop.return_value = MagicMock()

        bot._storage = MagicMock()
        bot._storage.get_open_trades.return_value = [
            {
                'id': 1,
                'symbol': 'BTC/USDT:USDT',
                'direction': 'long',
                'qty': 20.0,
                'entry_price': 100.0,
                'sl_price': 98.0,
                'tp_price': 104.0,
                'leverage': 20,
                'margin': 100.0,
            },
        ]

        asyncio.get_event_loop().run_until_complete(bot.start())

        assert 1 in bot._open_positions
        assert bot._running is True
