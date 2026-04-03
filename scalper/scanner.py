"""Coin scanner — scans top coins and ranks by signal strength."""

from __future__ import annotations

import logging

from scalper.config import Config
from scalper.exchange import Exchange
from scalper.filters import TrendFilter
from scalper.signals import SignalEngine

log = logging.getLogger(__name__)


class Scanner:
    """Scan top-N coins and return ranked trading opportunities."""

    def __init__(self, config: Config, exchange: Exchange | None = None) -> None:
        self.cfg = config
        self._exchange = exchange or Exchange(config)
        self._engine = SignalEngine(config)
        self._trend_filter = TrendFilter(ema_fast=config.ema_fast, ema_slow=config.ema_slow)

    async def scan(self) -> list[dict]:
        """Scan all coins, return sorted opportunities.

        For each symbol in top_n_coins:
        1. Fetch OHLCV for scalp_timeframe (e.g. 3m)
        2. Evaluate with SignalEngine
        3. If signal found: fetch senior TF OHLCV, check TrendFilter
        4. If filter passes: add to opportunities

        Sort by signal.strength descending.
        Return list of {'symbol': str, 'signal': Signal, 'price': float}

        Catch exceptions per-symbol and log warning, continue scanning.
        """
        symbols = await self._exchange.get_top_symbols(self.cfg.top_n_coins)
        opportunities: list[dict] = []

        for symbol in symbols:
            try:
                ohlcv = await self._exchange.fetch_ohlcv(
                    symbol, self.cfg.scalp_timeframe, limit=100,
                )

                signal = self._engine.evaluate(ohlcv)
                if signal is None:
                    continue

                senior_ohlcv = await self._exchange.fetch_ohlcv(
                    symbol, self.cfg.trend_timeframe, limit=100,
                )

                if not self._trend_filter.is_allowed(signal.direction, senior_ohlcv):
                    continue

                opportunities.append({
                    'symbol': symbol,
                    'signal': signal,
                    'price': signal.entry_price,
                })

            except Exception:
                log.warning('Error scanning %s', symbol, exc_info=True)
                continue

        opportunities.sort(key=lambda x: x['signal'].strength, reverse=True)
        return opportunities
