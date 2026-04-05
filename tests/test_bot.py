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


def _mock_exchange():
    """Create a mock exchange with all needed async methods."""
    ex = AsyncMock()
    ex.get_price = AsyncMock(return_value=100.0)
    ex.open_position = AsyncMock(return_value={
        'id': 'order123', 'average': None, 'price': None, 'filled': None,
    })
    ex.close_position = AsyncMock(return_value={
        'id': 'order456', 'average': None, 'price': None, 'filled': None,
    })
    ex.fetch_ohlcv = AsyncMock(return_value=None)
    return ex


class TestBotOpensTrade:
    """Signal found -> trade opened in storage."""

    def test_bot_opens_trade(self, config):
        from scalper.bot import ScalperBot

        bot = ScalperBot(config)
        bot._exchange = _mock_exchange()

        sig = _make_signal()
        bot._scanner = AsyncMock()
        bot._scanner.scan = AsyncMock(return_value=[
            {'symbol': 'BTC/USDT:USDT', 'signal': sig, 'price': 100.0},
        ])

        bot._risk = MagicMock()
        bot._risk.can_trade.return_value = True
        bot._risk.calc_position_size.return_value = {
            'qty': 20.0, 'margin': 100.0, 'position_value': 2000.0,
        }
        bot._risk.create_trailing_stop.return_value = MagicMock()

        bot._storage = MagicMock()
        bot._storage.get_open_trades.return_value = []
        bot._storage.open_trade.return_value = 1

        asyncio.get_event_loop().run_until_complete(bot.tick())

        bot._storage.open_trade.assert_called_once()
        call_kwargs = bot._storage.open_trade.call_args
        args, kwargs = call_kwargs
        assert kwargs.get('symbol', args[0] if args else None) == 'BTC/USDT:USDT'

    def test_bot_opens_trade_with_correct_direction(self, config):
        from scalper.bot import ScalperBot

        bot = ScalperBot(config)
        bot._exchange = _mock_exchange()

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
        bot._exchange = _mock_exchange()

        bot._scanner = AsyncMock()
        bot._scanner.scan = AsyncMock(return_value=[])

        bot._risk = MagicMock()
        bot._risk.can_trade.return_value = False

        bot._storage = MagicMock()
        bot._storage.get_open_trades.return_value = []

        asyncio.get_event_loop().run_until_complete(bot.tick())

        bot._scanner.scan.assert_not_called()

    def test_bot_skips_when_has_open_position(self, config):
        from scalper.bot import ScalperBot

        config.max_open_positions = 3  # limit to 3 for this test
        bot = ScalperBot(config)
        bot._exchange = _mock_exchange()

        bot._scanner = AsyncMock()

        bot._risk = MagicMock()
        bot._risk.can_trade.return_value = True

        bot._storage = MagicMock()
        bot._storage.get_open_trades.return_value = []
        trade_mock = lambda sym: {'trade': {'id': 1, 'symbol': sym, 'direction': 'long',
                          'entry_price': 100.0, 'sl_price': 98.0, 'tp_price': 104.0,
                          'qty': 20.0, 'leverage': 20, 'margin': 100.0},
                'trailing': MagicMock(update=MagicMock(return_value=98.0),
                                      is_hit=MagicMock(return_value=False))}
        bot._open_positions = {
            1: trade_mock('BTC/USDT:USDT'),
            2: trade_mock('ETH/USDT:USDT'),
            3: trade_mock('SOL/USDT:USDT'),
        }

        asyncio.get_event_loop().run_until_complete(bot.tick())

        bot._scanner.scan.assert_not_called()


class TestBotClosesOnSL:
    """Open position, price drops below SL -> closed."""

    def test_bot_closes_long_on_sl(self, config):
        from scalper.bot import ScalperBot

        bot = ScalperBot(config)
        bot._exchange = _mock_exchange()
        bot._exchange.get_price = AsyncMock(return_value=95.0)

        bot._scanner = AsyncMock()
        bot._risk = MagicMock()
        bot._risk.can_trade.return_value = True

        bot._storage = MagicMock()
        bot._storage.get_open_trades.return_value = []

        trailing = MagicMock()
        trailing.update = MagicMock(return_value=98.0)
        trailing.is_hit = MagicMock(return_value=True)
        trailing.current_sl = 98.0

        bot._open_positions = {
            1: {'trade': {'id': 1, 'symbol': 'BTC/USDT:USDT', 'direction': 'long',
                          'entry_price': 100.0, 'sl_price': 98.0, 'tp_price': 104.0,
                          'qty': 20.0, 'leverage': 20, 'margin': 100.0},
                'trailing': trailing},
        }

        asyncio.get_event_loop().run_until_complete(bot.tick())

        bot._storage.close_trade.assert_called_once()
        assert len(bot._open_positions) == 0

        call_kwargs = bot._storage.close_trade.call_args.kwargs
        assert call_kwargs['pnl'] < 0

    def test_bot_closes_short_on_sl(self, config):
        from scalper.bot import ScalperBot

        bot = ScalperBot(config)
        bot._exchange = _mock_exchange()
        bot._exchange.get_price = AsyncMock(return_value=105.0)

        bot._scanner = AsyncMock()
        bot._risk = MagicMock()
        bot._risk.can_trade.return_value = True

        bot._storage = MagicMock()
        bot._storage.get_open_trades.return_value = []

        trailing = MagicMock()
        trailing.update = MagicMock(return_value=102.0)
        trailing.is_hit = MagicMock(return_value=True)
        trailing.current_sl = 102.0

        bot._open_positions = {
            1: {'trade': {'id': 1, 'symbol': 'BTC/USDT:USDT', 'direction': 'short',
                          'entry_price': 100.0, 'sl_price': 102.0, 'tp_price': 96.0,
                          'qty': 20.0, 'leverage': 20, 'margin': 100.0},
                'trailing': trailing},
        }

        asyncio.get_event_loop().run_until_complete(bot.tick())

        bot._storage.close_trade.assert_called_once()
        call_kwargs = bot._storage.close_trade.call_args.kwargs
        assert call_kwargs['pnl'] < 0

    def test_bot_closes_on_tp(self, config):
        from scalper.bot import ScalperBot

        bot = ScalperBot(config)
        bot._exchange = _mock_exchange()
        bot._exchange.get_price = AsyncMock(return_value=105.0)

        bot._scanner = AsyncMock()
        bot._risk = MagicMock()
        bot._risk.can_trade.return_value = True

        bot._storage = MagicMock()
        bot._storage.get_open_trades.return_value = []

        trailing = MagicMock()
        trailing.update = MagicMock(return_value=99.0)
        trailing.is_hit = MagicMock(return_value=False)
        trailing.current_sl = 99.0

        bot._open_positions = {
            1: {'trade': {'id': 1, 'symbol': 'BTC/USDT:USDT', 'direction': 'long',
                          'entry_price': 100.0, 'sl_price': 98.0, 'tp_price': 104.0,
                          'qty': 20.0, 'leverage': 20, 'margin': 100.0},
                'trailing': trailing},
        }

        asyncio.get_event_loop().run_until_complete(bot.tick())

        bot._storage.close_trade.assert_called_once()
        call_kwargs = bot._storage.close_trade.call_args.kwargs
        assert call_kwargs['pnl'] > 0


class TestBotCallbacks:
    """Test notification callbacks."""

    def test_callback_called_on_open(self, config):
        from scalper.bot import ScalperBot

        bot = ScalperBot(config)
        bot._exchange = _mock_exchange()

        events = []
        bot.on_update(lambda evt, data: events.append((evt, data)))

        sig = _make_signal()
        bot._scanner = AsyncMock()
        bot._scanner.scan = AsyncMock(return_value=[
            {'symbol': 'BTC/USDT:USDT', 'signal': sig, 'price': 100.0},
        ])

        bot._risk = MagicMock()
        bot._risk.can_trade.return_value = True
        bot._risk.calc_position_size.return_value = {
            'qty': 20.0, 'margin': 100.0, 'position_value': 2000.0,
        }
        bot._risk.create_trailing_stop.return_value = MagicMock()

        bot._storage = MagicMock()
        bot._storage.get_open_trades.return_value = []
        bot._storage.open_trade.return_value = 1

        asyncio.get_event_loop().run_until_complete(bot.tick())

        assert any(e[0] == 'trade_opened' for e in events)


class TestGetStatus:
    """Test get_status returns correct structure."""

    def test_status_structure(self, config):
        from scalper.bot import ScalperBot

        bot = ScalperBot(config)
        bot._running = True
        bot._storage = MagicMock()
        bot._storage.get_daily_stats.return_value = {
            'total_trades': 0, 'total_pnl': 0, 'wins': 0, 'losses': 0, 'win_rate': 0,
        }
        bot._storage.get_all_stats.return_value = {
            'total_trades': 0, 'total_pnl': 0, 'wins': 0, 'losses': 0, 'win_rate': 0,
        }

        status = bot.get_status()

        assert status['running'] is True
        assert status['balance'] == 200.0
        assert 'positions' in status
        assert 'daily_stats' in status
        assert 'unrealized_pnl' in status


class TestRecoverPositions:
    """Test recovery of open positions from DB on start."""

    def test_recovers_positions(self, config):
        from scalper.bot import ScalperBot

        bot = ScalperBot(config)
        bot._exchange = _mock_exchange()

        bot._storage = MagicMock()
        bot._storage.get_open_trades.return_value = [
            {'id': 5, 'symbol': 'BTC/USDT:USDT', 'direction': 'long',
             'entry_price': 100.0, 'sl_price': 98.0, 'tp_price': 104.0,
             'qty': 20.0, 'leverage': 20, 'margin': 100.0},
        ]
        bot._storage.get_state.return_value = None

        bot._risk = MagicMock()
        bot._risk.create_trailing_stop.return_value = MagicMock()

        asyncio.get_event_loop().run_until_complete(bot.start())

        assert 5 in bot._open_positions
