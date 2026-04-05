"""Tests for scalper.scanner module."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from scalper.config import Config
from scalper.scanner import Scanner
from scalper.signals import Signal


@pytest.fixture
def config():
    return Config(
        scalp_timeframe='3m',
        trend_timeframe='15m',
        top_n_coins=3,
    )


def _make_ohlcv(length: int = 100) -> dict[str, np.ndarray]:
    """Create dummy OHLCV data."""
    return {
        'timestamp': np.arange(length, dtype=float),
        'open': np.random.rand(length) * 100,
        'high': np.random.rand(length) * 100,
        'low': np.random.rand(length) * 100,
        'close': np.random.rand(length) * 100,
        'volume': np.random.rand(length) * 1000,
    }


def test_scanner_ranks_by_strength(config):
    """Mock 3 symbols with different signal strengths; verify descending sort."""
    exchange = AsyncMock()
    exchange.get_top_symbols = AsyncMock(return_value=[
        'BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT',
    ])
    exchange.fetch_ohlcv = AsyncMock(return_value=_make_ohlcv())

    sig_btc = Signal(direction='long', strength=2, entry_price=100.0,
                     sl_price=98.0, tp_price=104.0, confidence=60,
                     reasons=['ema_cross', 'momentum'])
    sig_eth = Signal(direction='short', strength=4, entry_price=50.0,
                     sl_price=52.0, tp_price=46.0, confidence=90,
                     reasons=['ema_cross', 'rsi_overbought', 'volume_spike', 'momentum'])
    sig_sol = Signal(direction='long', strength=3, entry_price=10.0,
                     sl_price=9.5, tp_price=11.5, confidence=75,
                     reasons=['ema_cross', 'rsi_oversold', 'momentum'])

    signal_map = {
        'BTC/USDT:USDT': sig_btc,
        'ETH/USDT:USDT': sig_eth,
        'SOL/USDT:USDT': sig_sol,
    }

    scanner = Scanner(config, exchange=exchange)

    # Mock signal engine to return pre-defined signals per symbol
    def fake_evaluate(ohlcv):
        # We track which symbol is being evaluated via a side channel
        return fake_evaluate._current_signal

    scanner._engine = MagicMock()
    scanner._engine.evaluate = MagicMock(side_effect=lambda ohlcv: None)

    # Mock trend filter to always allow
    scanner._trend_filter = MagicMock()
    scanner._trend_filter.is_allowed = MagicMock(return_value=True)

    # We need a more elaborate approach: patch fetch_ohlcv to track symbol,
    # and patch evaluate to return per-symbol signal.
    call_index = [0]
    symbols_order = ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT']

    def evaluate_side_effect(ohlcv):
        idx = call_index[0]
        call_index[0] += 1
        sym = symbols_order[idx]
        return signal_map[sym]

    scanner._engine.evaluate = MagicMock(side_effect=evaluate_side_effect)

    results = asyncio.get_event_loop().run_until_complete(scanner.scan())

    assert len(results) == 3
    # Should be sorted by confidence descending: ETH(90), SOL(75), BTC(60)
    assert results[0]['symbol'] == 'ETH/USDT:USDT'
    assert results[0]['signal'].confidence == 90
    assert results[1]['symbol'] == 'SOL/USDT:USDT'
    assert results[1]['signal'].confidence == 75
    assert results[2]['symbol'] == 'BTC/USDT:USDT'
    assert results[2]['signal'].confidence == 60


def test_scanner_skips_no_signal(config):
    """Symbols with no signal should be excluded from results."""
    exchange = AsyncMock()
    exchange.get_top_symbols = AsyncMock(return_value=[
        'BTC/USDT:USDT', 'ETH/USDT:USDT',
    ])
    exchange.fetch_ohlcv = AsyncMock(return_value=_make_ohlcv())

    sig_btc = Signal(direction='long', strength=2, entry_price=100.0,
                     sl_price=98.0, tp_price=104.0, reasons=['ema_cross', 'momentum'])

    scanner = Scanner(config, exchange=exchange)

    call_index = [0]

    def evaluate_side_effect(ohlcv):
        idx = call_index[0]
        call_index[0] += 1
        if idx == 0:
            return sig_btc
        return None  # ETH has no signal

    scanner._engine = MagicMock()
    scanner._engine.evaluate = MagicMock(side_effect=evaluate_side_effect)
    scanner._trend_filter = MagicMock()
    scanner._trend_filter.is_allowed = MagicMock(return_value=True)

    results = asyncio.get_event_loop().run_until_complete(scanner.scan())

    assert len(results) == 1
    assert results[0]['symbol'] == 'BTC/USDT:USDT'


def test_scanner_skips_trend_filtered(config):
    """Symbols blocked by trend filter should be excluded."""
    exchange = AsyncMock()
    exchange.get_top_symbols = AsyncMock(return_value=['BTC/USDT:USDT'])
    exchange.fetch_ohlcv = AsyncMock(return_value=_make_ohlcv())

    sig = Signal(direction='long', strength=3, entry_price=100.0,
                 sl_price=98.0, tp_price=104.0, reasons=['ema_cross', 'momentum', 'volume_spike'])

    scanner = Scanner(config, exchange=exchange)
    scanner._engine = MagicMock()
    scanner._engine.evaluate = MagicMock(return_value=sig)
    scanner._trend_filter = MagicMock()
    scanner._trend_filter.is_allowed = MagicMock(return_value=False)

    results = asyncio.get_event_loop().run_until_complete(scanner.scan())

    assert len(results) == 0


def test_scanner_handles_exception_per_symbol(config):
    """Exception on one symbol should not break scanning of others."""
    exchange = AsyncMock()
    exchange.get_top_symbols = AsyncMock(return_value=[
        'BTC/USDT:USDT', 'BAD/USDT:USDT', 'ETH/USDT:USDT',
    ])

    ohlcv = _make_ohlcv()

    async def fetch_side_effect(symbol, timeframe, limit=100):
        if symbol == 'BAD/USDT:USDT':
            raise RuntimeError('Exchange error')
        return ohlcv

    exchange.fetch_ohlcv = AsyncMock(side_effect=fetch_side_effect)

    sig = Signal(direction='long', strength=2, entry_price=100.0,
                 sl_price=98.0, tp_price=104.0, reasons=['ema_cross', 'momentum'])

    scanner = Scanner(config, exchange=exchange)
    scanner._engine = MagicMock()
    scanner._engine.evaluate = MagicMock(return_value=sig)
    scanner._trend_filter = MagicMock()
    scanner._trend_filter.is_allowed = MagicMock(return_value=True)

    results = asyncio.get_event_loop().run_until_complete(scanner.scan())

    # BAD symbol should be skipped, BTC and ETH should be present
    assert len(results) == 2
    symbols = [r['symbol'] for r in results]
    assert 'BAD/USDT:USDT' not in symbols
