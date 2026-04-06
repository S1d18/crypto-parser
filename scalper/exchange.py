from __future__ import annotations

import logging

import aiohttp
from aiohttp.resolver import ThreadedResolver
import ccxt.async_support as ccxt_async
import numpy as np

from scalper.config import Config

log = logging.getLogger(__name__)


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

    # ------------------------------------------------------------------
    # Order execution
    # ------------------------------------------------------------------

    async def set_leverage(self, symbol: str, leverage: int):
        """Set leverage for symbol."""
        try:
            await self._exchange.set_leverage(leverage, symbol)
        except Exception as e:
            # Bybit may return error if leverage is already set
            if 'leverage not modified' not in str(e).lower():
                log.warning('Set leverage failed for %s: %s', symbol, e)

    async def open_position(self, symbol: str, direction: str, qty: float,
                            leverage: int, sl_price: float = None,
                            tp_price: float = None) -> dict:
        """Open a position with market order + SL/TP on exchange.

        SL/TP are set as position-level orders on Bybit so they persist
        even if the bot crashes.
        Returns order info dict with verified fill data.
        """
        await self.set_leverage(symbol, leverage)

        side = 'buy' if direction == 'long' else 'sell'

        qty = self._exchange.amount_to_precision(symbol, qty)
        qty = float(qty)

        params = {}
        if sl_price:
            params['stopLoss'] = {'triggerPrice': sl_price}
        if tp_price:
            params['takeProfit'] = {'triggerPrice': tp_price}

        order = await self._exchange.create_order(
            symbol=symbol,
            type='market',
            side=side,
            amount=qty,
            params=params,
        )

        # Verify fill — fetch order to get actual filled qty and price
        order = await self._verify_fill(order, symbol)

        log.info('Order placed: %s %s %s qty=%.6f fill_qty=%.6f fill_price=%s '
                 'SL=%s TP=%s order_id=%s',
                 side, symbol, direction, qty,
                 order.get('filled', qty),
                 order.get('average', '?'),
                 sl_price, tp_price, order.get('id'))
        return order

    async def close_position(self, symbol: str, direction: str, qty: float) -> dict:
        """Close a position with market order (opposite side).

        Returns order info dict with verified fill data.
        """
        side = 'sell' if direction == 'long' else 'buy'

        qty = self._exchange.amount_to_precision(symbol, qty)
        qty = float(qty)

        order = await self._exchange.create_order(
            symbol=symbol,
            type='market',
            side=side,
            amount=qty,
            params={'reduceOnly': True},
        )

        # Verify fill
        order = await self._verify_fill(order, symbol)

        log.info('Close order: %s %s qty=%.6f fill_qty=%.6f fill_price=%s order_id=%s',
                 side, symbol, qty,
                 order.get('filled', qty),
                 order.get('average', '?'),
                 order.get('id'))
        return order

    # ------------------------------------------------------------------
    # SL/TP management on exchange
    # ------------------------------------------------------------------

    def _bybit_symbol(self, symbol: str) -> str:
        """Convert ccxt symbol 'BTC/USDT:USDT' to Bybit native 'BTCUSDT'."""
        return symbol.replace('/', '').replace(':USDT', '')

    async def set_sl_tp(self, symbol: str, sl_price: float = None,
                        tp_price: float = None):
        """Set or update position-level SL/TP on Bybit.

        Operates on the position directly — no order ID needed.
        Replaces any existing SL/TP.
        """
        params = {
            'category': 'linear',
            'symbol': self._bybit_symbol(symbol),
            'tpslMode': 'Full',
            'positionIdx': 0,
        }
        if sl_price is not None:
            params['stopLoss'] = str(sl_price)
            params['slTriggerBy'] = 'LastPrice'
        if tp_price is not None:
            params['takeProfit'] = str(tp_price)
            params['tpTriggerBy'] = 'LastPrice'

        try:
            await self._exchange.privatePostV5PositionTradingStop(params)
            log.debug('SL/TP set for %s: SL=%s TP=%s', symbol, sl_price, tp_price)
        except Exception as e:
            log.warning('Failed to set SL/TP for %s: %s', symbol, e)

    async def update_sl(self, symbol: str, sl_price: float):
        """Move SL on exchange (for trailing stop updates)."""
        await self.set_sl_tp(symbol, sl_price=sl_price)

    async def get_position_sl_tp(self, symbol: str) -> dict:
        """Read back SL/TP from exchange to verify they are set."""
        pos = await self.get_position(symbol)
        if not pos:
            return {'sl': None, 'tp': None}
        info = pos.get('info', {})
        sl = info.get('stopLoss', '0')
        tp = info.get('takeProfit', '0')
        return {
            'sl': float(sl) if sl and sl != '0' else None,
            'tp': float(tp) if tp and tp != '0' else None,
        }

    # ------------------------------------------------------------------
    # Order verification
    # ------------------------------------------------------------------

    async def _verify_fill(self, order: dict, symbol: str) -> dict:
        """Verify order was filled. Fetch from exchange if needed."""
        filled = order.get('filled')
        avg_price = order.get('average')

        if filled and avg_price:
            return order

        # Fetch order status from exchange
        order_id = order.get('id')
        if not order_id:
            return order

        try:
            fetched = await self._exchange.fetch_order(order_id, symbol)
            if fetched.get('filled'):
                order['filled'] = fetched['filled']
            if fetched.get('average'):
                order['average'] = fetched['average']
            if fetched.get('status'):
                order['status'] = fetched['status']
            if fetched.get('status') != 'closed':
                log.warning('Order %s not fully filled: status=%s filled=%s/%s',
                            order_id, fetched.get('status'),
                            fetched.get('filled'), fetched.get('amount'))
        except Exception as e:
            log.warning('Could not verify order %s: %s', order_id, e)

        return order

    async def get_position(self, symbol: str) -> dict | None:
        """Get current position for symbol. Returns None if no position.

        Position dict includes Bybit's unrealizedPnl, markPrice, etc.
        """
        try:
            positions = await self._exchange.fetch_positions([symbol])
            for pos in positions:
                contracts = pos.get('contracts')
                if pos.get('symbol') == symbol and contracts and float(contracts) > 0:
                    return pos
        except Exception:
            pass
        return None

    async def get_position_pnl(self, symbol: str) -> dict | None:
        """Get unrealized PnL and mark price from Bybit for a position."""
        pos = await self.get_position(symbol)
        if not pos:
            return None
        return {
            'unrealized_pnl': float(pos.get('unrealizedPnl') or 0),
            'mark_price': float(pos.get('markPrice') or 0),
            'entry_price': float(pos.get('entryPrice') or 0),
            'contracts': float(pos.get('contracts') or 0),
            'percentage': float(pos.get('percentage') or 0),
        }

    async def get_position_contracts(self, symbol: str) -> float:
        """Return current live contracts size on exchange, or 0 if flat/unknown."""
        pos = await self.get_position(symbol)
        if not pos:
            return 0.0
        try:
            return float(pos.get('contracts') or 0.0)
        except Exception:
            return 0.0
