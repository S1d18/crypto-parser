"""Coin scanner — scans top coins and ranks by signal strength."""

from __future__ import annotations

import logging
import time

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
        # Cache top symbols for 5 minutes
        self._top_symbols: list[str] = []
        self._symbols_updated_at: float = 0
        self._symbols_ttl: float = 300  # 5 min

    async def _get_symbols(self) -> list[str]:
        """Get top symbols with caching."""
        now = time.time()
        if not self._top_symbols or (now - self._symbols_updated_at) > self._symbols_ttl:
            self._top_symbols = await self._exchange.get_top_symbols(self.cfg.top_n_coins)
            self._symbols_updated_at = now
            log.info('Updated top %d symbols', len(self._top_symbols))
        return self._top_symbols

    async def scan(self) -> list[dict]:
        """Scan all coins, return sorted opportunities.

        1. Fetch OHLCV for scalp_timeframe
        2. Evaluate with SignalEngine
        3. If signal found: fetch senior TF, check TrendFilter
        4. Sort by strength descending
        """
        symbols = await self._get_symbols()
        opportunities: list[dict] = []

        for symbol in symbols:
            try:
                ohlcv = await self._exchange.fetch_ohlcv(
                    symbol, self.cfg.scalp_timeframe, limit=100,
                )

                signal = self._engine.evaluate(ohlcv)
                if signal is None:
                    continue

                if signal.confidence < 75:
                    continue

                # Only fetch senior TF if we have a signal (saves API calls)
                senior_ohlcv = await self._exchange.fetch_ohlcv(
                    symbol, self.cfg.trend_timeframe, limit=50,
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

        opportunities.sort(key=lambda x: x['signal'].confidence, reverse=True)
        return opportunities
