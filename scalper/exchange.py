from __future__ import annotations

import aiohttp
from aiohttp.resolver import ThreadedResolver
import ccxt.async_support as ccxt_async
import numpy as np

from scalper.config import Config


class Exchange:
    """Async wrapper over ccxt for Bybit USDT perpetual futures."""

    def __init__(self, config: Config):
        self._exchange = ccxt_async.bybit({
            'apiKey': config.bybit_api_key,
            'secret': config.bybit_api_secret,
            'options': {'defaultType': 'swap'},
            'enableRateLimit': True,
        })
        if config.bybit_demo:
            self._exchange.enable_demo_trading(True)

    async def start(self):
        """Load markets. Uses ThreadedResolver to avoid aiodns issues on Windows."""
        # Replace default session with one using ThreadedResolver
        resolver = ThreadedResolver()
        connector = aiohttp.TCPConnector(resolver=resolver, ssl=False)
        if self._exchange.session:
            await self._exchange.session.close()
        self._exchange.session = aiohttp.ClientSession(connector=connector)
        await self._exchange.load_markets()

    async def close(self):
        """Close exchange connection."""
        await self._exchange.close()

    async def get_top_symbols(self, n: int = 50) -> list[str]:
        """Top N USDT perps by 24h volume.

        Filter: symbol ends with ':USDT' and has quoteVolume.
        Sort by quoteVolume descending.
        """
        tickers = await self._exchange.fetch_tickers()
        perps = [
            t for t in tickers.values()
            if t['symbol'].endswith(':USDT') and t.get('quoteVolume')
        ]
        perps.sort(key=lambda t: t['quoteVolume'], reverse=True)
        return [t['symbol'] for t in perps[:n]]

    async def fetch_ohlcv(
        self, symbol: str, timeframe: str, limit: int = 100,
    ) -> dict[str, np.ndarray]:
        """Fetch candles and return as dict of numpy arrays.

        Keys: timestamp, open, high, low, close, volume
        """
        raw = await self._exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        data = np.array(raw)
        return {
            'timestamp': data[:, 0],
            'open': data[:, 1],
            'high': data[:, 2],
            'low': data[:, 3],
            'close': data[:, 4],
            'volume': data[:, 5],
        }

    async def get_price(self, symbol: str) -> float:
        """Current last price from ticker."""
        ticker = await self._exchange.fetch_ticker(symbol)
        return float(ticker['last'])
