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


@pytest.mark.asyncio
async def test_full_cycle(tmp_path, config):
    """Full cycle: scan -> open trade -> trailing updates -> TP hit -> close.

    Tick 1: scanner returns signal, bot opens a long trade.
    Tick 2: price rises to 51000, trailing stop updates, position stays open.
    Tick 3: price hits TP (51500), bot closes trade with profit.
    Verify: no open positions, 1 winning trade, balance increased.
    """
    db_path = str(tmp_path / 'test.db')

    bot = ScalperBot(config)
    bot._storage = Storage(db_path)
    bot._exchange = MagicMock()
    bot._exchange.start = AsyncMock()
    bot._exchange.close = AsyncMock()
    bot._exchange.get_price = AsyncMock(return_value=50000.0)

    signal = Signal(
        direction='long',
        strength=3,
        entry_price=50000.0,
        sl_price=49250.0,
        tp_price=51500.0,
        reasons=['ema_cross', 'rsi_oversold', 'volume_spike'],
    )

    bot._scanner = MagicMock()
    bot._scanner.scan = AsyncMock(return_value=[
        {'symbol': 'BTC/USDT:USDT', 'signal': signal, 'price': 50000.0},
    ])

    await bot.start()

    # ---- Tick 1: open trade ------------------------------------------------
    await bot.tick()
    assert len(bot._open_positions) == 1, 'Expected 1 open position after tick 1'

    trade_id = list(bot._open_positions.keys())[0]
    pos = bot._open_positions[trade_id]
    trailing_sl_before = pos['trailing'].current_sl

    # ---- Tick 2: price rises, trailing updates, position stays open --------
    bot._exchange.get_price = AsyncMock(return_value=51000.0)
    # Scanner should not be called (already have open position), but mock it anyway
    bot._scanner.scan = AsyncMock(return_value=[])
    await bot.tick()
    assert len(bot._open_positions) == 1, 'Position should still be open after tick 2'

    # Trailing stop should have moved up
    trailing_sl_after = bot._open_positions[trade_id]['trailing'].current_sl
    assert trailing_sl_after > trailing_sl_before, \
        f'Trailing SL should move up: {trailing_sl_before} -> {trailing_sl_after}'

    # ---- Tick 3: price hits TP -> bot closes trade -------------------------
    bot._exchange.get_price = AsyncMock(return_value=51500.0)
    await bot.tick()
    assert len(bot._open_positions) == 0, 'Position should be closed after TP hit'

    # ---- Verify DB stats ---------------------------------------------------
    stats = bot._storage.get_daily_stats()
    assert stats['total_trades'] == 1
    assert stats['wins'] == 1
    assert stats['losses'] == 0
    assert stats['total_pnl'] > 0

    # Balance should have increased
    assert config.balance > 200.0, f'Balance should increase, got {config.balance}'

    # Equity history should have a snapshot
    equity = bot._storage.get_equity_history()
    assert len(equity) >= 1
    assert equity[-1]['balance'] > 200.0

    # Trade history should show the closed trade
    history = bot._storage.get_trade_history()
    assert len(history) == 1
    assert history[0]['close_reason'] == 'tp'
    assert history[0]['pnl'] > 0
    assert history[0]['direction'] == 'long'
    assert history[0]['symbol'] == 'BTC/USDT:USDT'

    bot._storage.close()


@pytest.mark.asyncio
async def test_full_cycle_short_sl(tmp_path, config):
    """Short trade cycle ending in SL hit.

    Tick 1: scanner returns short signal, bot opens trade at 50000.
    Tick 2: price rises to 50500 (bad for short), SL hit at 50750 -> close with loss.
    Verify: no open positions, 1 losing trade, balance decreased.
    """
    db_path = str(tmp_path / 'test_short.db')

    bot = ScalperBot(config)
    bot._storage = Storage(db_path)
    bot._exchange = MagicMock()
    bot._exchange.start = AsyncMock()
    bot._exchange.close = AsyncMock()
    bot._exchange.get_price = AsyncMock(return_value=50000.0)

    signal = Signal(
        direction='short',
        strength=3,
        entry_price=50000.0,
        sl_price=50750.0,
        tp_price=48500.0,
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

    # Tick 2: price rises above SL for short -> closed
    bot._exchange.get_price = AsyncMock(return_value=50800.0)
    bot._scanner.scan = AsyncMock(return_value=[])
    await bot.tick()
    assert len(bot._open_positions) == 0, 'Short should be closed after SL hit'

    stats = bot._storage.get_daily_stats()
    assert stats['total_trades'] == 1
    assert stats['losses'] == 1
    assert stats['total_pnl'] < 0
    assert config.balance < 200.0

    bot._storage.close()
