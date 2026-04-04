"""Integration test — full cycle from scanning to closing a trade."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from scalper.config import Config
from scalper.bot import ScalperBot
from scalper.storage import Storage
from scalper.signals import Signal


@pytest.fixture
def config():
    return Config(
        balance=200.0,
        leverage=20,
        max_risk_per_trade=0.5,
        taker_fee=0.00055,
        bybit_api_key='test',
        bybit_api_secret='test',
        bybit_demo=True,
        max_consecutive_losses=10,
        max_daily_loss=30.0,
    )


def _mock_exchange():
    ex = MagicMock()
    ex.start = AsyncMock()
    ex.close = AsyncMock()
    ex.get_price = AsyncMock(return_value=50000.0)
    ex.open_position = AsyncMock(return_value={
        'id': 'ord1', 'average': None, 'price': None, 'filled': None,
    })
    ex.close_position = AsyncMock(return_value={
        'id': 'ord2', 'average': None, 'price': None, 'filled': None,
    })
    ex.fetch_ohlcv = AsyncMock(return_value=None)
    return ex


@pytest.mark.asyncio
async def test_full_cycle(tmp_path, config):
    """Full cycle: scan -> open -> trailing -> TP -> close with profit."""
    db_path = str(tmp_path / 'test.db')

    bot = ScalperBot(config)
    bot._storage = Storage(db_path)
    bot._exchange = _mock_exchange()

    signal = Signal(
        direction='long', strength=3, entry_price=50000.0,
        sl_price=49250.0, tp_price=51500.0,
        reasons=['ema_cross', 'rsi_oversold', 'volume_spike'],
    )

    bot._scanner = MagicMock()
    bot._scanner.scan = AsyncMock(return_value=[
        {'symbol': 'BTC/USDT:USDT', 'signal': signal, 'price': 50000.0},
    ])

    await bot.start()

    # Tick 1: open trade
    await bot.tick()
    assert len(bot._open_positions) == 1

    trade_id = list(bot._open_positions.keys())[0]
    trailing_sl_before = bot._open_positions[trade_id]['trailing'].current_sl

    # Tick 2: price rises
    bot._exchange.get_price = AsyncMock(return_value=51000.0)
    bot._scanner.scan = AsyncMock(return_value=[])
    await bot.tick()
    assert len(bot._open_positions) == 1

    trailing_sl_after = bot._open_positions[trade_id]['trailing'].current_sl
    assert trailing_sl_after > trailing_sl_before

    # Tick 3: TP hit
    bot._exchange.get_price = AsyncMock(return_value=51500.0)
    await bot.tick()
    assert len(bot._open_positions) == 0

    stats = bot._storage.get_daily_stats()
    assert stats['total_trades'] == 1
    assert stats['wins'] == 1
    assert stats['total_pnl'] > 0
    assert config.balance > 200.0

    # Verify close order(s) were placed (may include partial close)
    assert bot._exchange.close_position.call_count >= 1

    bot._storage.close()


@pytest.mark.asyncio
async def test_full_cycle_short_sl(tmp_path, config):
    """Short trade ending in SL hit."""
    db_path = str(tmp_path / 'test_short.db')

    bot = ScalperBot(config)
    bot._storage = Storage(db_path)
    bot._exchange = _mock_exchange()

    signal = Signal(
        direction='short', strength=3, entry_price=50000.0,
        sl_price=50750.0, tp_price=48500.0,
        reasons=['ema_cross', 'rsi_overbought', 'volume_spike'],
    )

    bot._scanner = MagicMock()
    bot._scanner.scan = AsyncMock(return_value=[
        {'symbol': 'BTC/USDT:USDT', 'signal': signal, 'price': 50000.0},
    ])

    await bot.start()

    # Tick 1: open short
    await bot.tick()
    assert len(bot._open_positions) == 1

    # Tick 2: price rises above SL
    bot._exchange.get_price = AsyncMock(return_value=50800.0)
    bot._scanner.scan = AsyncMock(return_value=[])
    await bot.tick()
    assert len(bot._open_positions) == 0

    stats = bot._storage.get_daily_stats()
    assert stats['total_trades'] == 1
    assert stats['losses'] == 1
    assert stats['total_pnl'] < 0
    assert config.balance < 200.0

    bot._storage.close()
