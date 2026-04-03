import pytest
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch
from scalper.config import Config
from scalper.exchange import Exchange


@pytest.fixture
def config():
    return Config(
        bybit_api_key='test-key',
        bybit_api_secret='test-secret',
        bybit_demo=True,
    )


@pytest.fixture
def exchange(config):
    with patch('scalper.exchange.ccxt_async') as mock_ccxt:
        mock_bybit = MagicMock()
        mock_bybit.set_sandbox_mode = MagicMock()
        mock_bybit.load_markets = AsyncMock()
        mock_bybit.close = AsyncMock()
        mock_ccxt.bybit.return_value = mock_bybit
        ex = Exchange(config)
    return ex


class TestGetTopSymbols:
    """Test get_top_symbols filters and sorts USDT perps by volume."""

    @pytest.mark.asyncio
    async def test_get_top_symbols(self, exchange):
        exchange._exchange.fetch_tickers = AsyncMock(return_value={
            'BTC/USDT:USDT': {
                'symbol': 'BTC/USDT:USDT',
                'quoteVolume': 5_000_000_000,
            },
            'ETH/USDT:USDT': {
                'symbol': 'ETH/USDT:USDT',
                'quoteVolume': 3_000_000_000,
            },
            'SOL/USDT:USDT': {
                'symbol': 'SOL/USDT:USDT',
                'quoteVolume': 1_000_000_000,
            },
            # Spot pair — should be excluded
            'BTC/USDT': {
                'symbol': 'BTC/USDT',
                'quoteVolume': 9_000_000_000,
            },
            # No quoteVolume — should be excluded
            'DOGE/USDT:USDT': {
                'symbol': 'DOGE/USDT:USDT',
                'quoteVolume': None,
            },
            # Zero volume — should be excluded
            'XRP/USDT:USDT': {
                'symbol': 'XRP/USDT:USDT',
                'quoteVolume': 0,
            },
        })

        result = await exchange.get_top_symbols(n=2)

        assert len(result) == 2
        assert result[0] == 'BTC/USDT:USDT'
        assert result[1] == 'ETH/USDT:USDT'

    @pytest.mark.asyncio
    async def test_get_top_symbols_returns_all_when_fewer_than_n(self, exchange):
        exchange._exchange.fetch_tickers = AsyncMock(return_value={
            'BTC/USDT:USDT': {
                'symbol': 'BTC/USDT:USDT',
                'quoteVolume': 1_000_000,
            },
        })

        result = await exchange.get_top_symbols(n=50)
        assert len(result) == 1
        assert result[0] == 'BTC/USDT:USDT'


class TestFetchOhlcv:
    """Test fetch_ohlcv converts raw data to numpy arrays."""

    @pytest.mark.asyncio
    async def test_fetch_ohlcv(self, exchange):
        raw_candles = [
            [1700000000000, 36000.0, 36500.0, 35800.0, 36200.0, 100.5],
            [1700000180000, 36200.0, 36800.0, 36100.0, 36700.0, 200.3],
            [1700000360000, 36700.0, 37000.0, 36600.0, 36900.0, 150.1],
        ]
        exchange._exchange.fetch_ohlcv = AsyncMock(return_value=raw_candles)

        result = await exchange.fetch_ohlcv('BTC/USDT:USDT', '3m', limit=3)

        assert isinstance(result, dict)
        for key in ('timestamp', 'open', 'high', 'low', 'close', 'volume'):
            assert key in result
            assert isinstance(result[key], np.ndarray)
            assert len(result[key]) == 3

        np.testing.assert_array_equal(
            result['timestamp'],
            np.array([1700000000000, 1700000180000, 1700000360000]),
        )
        np.testing.assert_array_almost_equal(
            result['open'], np.array([36000.0, 36200.0, 36700.0]),
        )
        np.testing.assert_array_almost_equal(
            result['close'], np.array([36200.0, 36700.0, 36900.0]),
        )
        np.testing.assert_array_almost_equal(
            result['high'], np.array([36500.0, 36800.0, 37000.0]),
        )
        np.testing.assert_array_almost_equal(
            result['low'], np.array([35800.0, 36100.0, 36600.0]),
        )
        np.testing.assert_array_almost_equal(
            result['volume'], np.array([100.5, 200.3, 150.1]),
        )

        exchange._exchange.fetch_ohlcv.assert_called_once_with(
            'BTC/USDT:USDT', '3m', limit=3,
        )


class TestGetPrice:
    """Test get_price returns last price from ticker."""

    @pytest.mark.asyncio
    async def test_get_price(self, exchange):
        exchange._exchange.fetch_ticker = AsyncMock(return_value={
            'last': 36500.0,
        })

        price = await exchange.get_price('BTC/USDT:USDT')

        assert price == 36500.0
        exchange._exchange.fetch_ticker.assert_called_once_with('BTC/USDT:USDT')


class TestExchangeInit:
    """Test Exchange constructor sets up ccxt correctly."""

    def test_demo_mode_enabled(self):
        cfg = Config(bybit_api_key='k', bybit_api_secret='s', bybit_demo=True)
        with patch('scalper.exchange.ccxt_async') as mock_ccxt:
            mock_bybit = MagicMock()
            mock_ccxt.bybit.return_value = mock_bybit
            Exchange(cfg)
            mock_bybit.enable_demo_trading.assert_called_once_with(True)

    def test_demo_mode_disabled(self):
        cfg = Config(bybit_api_key='k', bybit_api_secret='s', bybit_demo=False)
        with patch('scalper.exchange.ccxt_async') as mock_ccxt:
            mock_bybit = MagicMock()
            mock_ccxt.bybit.return_value = mock_bybit
            Exchange(cfg)
            mock_bybit.enable_demo_trading.assert_not_called()


class TestStartAndClose:
    """Test start and close methods."""

    @pytest.mark.asyncio
    async def test_start_loads_markets(self, exchange):
        exchange._exchange.load_markets = AsyncMock()
        exchange._exchange.session = None  # no existing session
        await exchange.start()
        exchange._exchange.load_markets.assert_called_once()

    @pytest.mark.asyncio
    async def test_close(self, exchange):
        exchange._exchange.close = AsyncMock()
        await exchange.close()
        exchange._exchange.close.assert_called_once()
