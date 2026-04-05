"""Multi-strategy scanner — same as Scanner but accepts any signal engine."""

from __future__ import annotations

import logging
import time

from scalper.config import Config
from scalper.exchange import Exchange
from scalper.filters import TrendFilter

log = logging.getLogger(__name__)


class MultiScanner:
    """Scan top-N coins using a pluggable signal engine."""

    def __init__(self, config: Config, signal_engine, exchange: Exchange | None = None,
                 use_trend_filter: bool = True) -> None:
        self.cfg = config
        self._exchange = exchange or Exchange(config)
        self._engine = signal_engine
        self._use_trend_filter = use_trend_filter
        self._trend_filter = TrendFilter(ema_fast=config.ema_fast, ema_slow=config.ema_slow)
        self._top_symbols: list[str] = []
        self._symbols_updated_at: float = 0
        self._symbols_ttl: float = 300

    async def _get_symbols(self) -> list[str]:
        now = time.time()
        if not self._top_symbols or (now - self._symbols_updated_at) > self._symbols_ttl:
            self._top_symbols = await self._exchange.get_top_symbols(self.cfg.top_n_coins)
            self._symbols_updated_at = now
            log.info('Updated top %d symbols', len(self._top_symbols))
        return self._top_symbols

    async def scan(self) -> list[dict]:
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

                # Optional trend filter on senior TF
                if self._use_trend_filter:
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
