# Скальпинг-бот "Снайпер" — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Paper trading скальпер, сканирующий топ-50 крипто-монет на Bybit и входящий в быстрые сделки с x20 плечом, цель ~$100/день с баланса $200.

**Architecture:** Asyncio бот сканирует топ-50 USDT перпов каждые 30 секунд, ранжирует по силе сигнала (EMA+RSI+Volume+ADX), входит когда 2-3 индикатора совпадают. Адаптивные SL/TP по ATR с trailing stop. Flask-SocketIO дашборд на русском для мониторинга.

**Tech Stack:** Python 3.11+, ccxt (async), numpy, Flask, Flask-SocketIO, SQLite, eventlet

---

## Подготовка: Очистка проекта

Перед началом — удалить всё старое содержимое (кроме `.env`, `.gitignore`, `docs/`, `CLAUDE.md`, `.venv/`). Новый проект в той же директории.

```bash
# Из D:\python\Crypto_parser — удалить старые файлы
# Оставить: .env, .env.example, .gitignore, CLAUDE.md, docs/, .venv/, .git/
```

---

## Task 1: Конфиг и настройки

**Files:**
- Create: `scalper/config.py`
- Create: `scalper/__init__.py`
- Create: `.env.example` (обновить)
- Test: `tests/test_config.py`
- Create: `tests/__init__.py`

**Step 1: Write the failing test**

```python
# tests/__init__.py
# (empty)

# tests/test_config.py
import pytest
import os

def test_config_defaults():
    """Config создаётся с дефолтными значениями."""
    from scalper.config import Config
    cfg = Config()
    assert cfg.balance == 200.0
    assert cfg.leverage == 20
    assert cfg.max_risk_per_trade == 0.5  # 50% баланса
    assert cfg.max_daily_loss == 30.0
    assert cfg.max_consecutive_losses == 10
    assert cfg.pause_after_losses_minutes == 60
    assert cfg.scan_interval == 30
    assert cfg.scalp_timeframe == '3m'
    assert cfg.trend_timeframe == '15m'
    assert cfg.top_n_coins == 50
    assert cfg.taker_fee == 0.00055
    assert cfg.atr_sl_multiplier == 1.5
    assert cfg.tp_ratio == 2.0
    assert cfg.adx_min == 20
    assert cfg.web_port == 5001

def test_config_from_env(monkeypatch):
    """Config читает значения из переменных окружения."""
    from scalper.config import Config
    monkeypatch.setenv('BYBIT_API_KEY', 'test_key')
    monkeypatch.setenv('BYBIT_API_SECRET', 'test_secret')
    monkeypatch.setenv('BALANCE', '500')
    monkeypatch.setenv('LEVERAGE', '10')
    cfg = Config.from_env()
    assert cfg.bybit_api_key == 'test_key'
    assert cfg.bybit_api_secret == 'test_secret'
    assert cfg.balance == 500.0
    assert cfg.leverage == 10
```

**Step 2: Run test to verify it fails**

```bash
cd D:\python\Crypto_parser
python -m pytest tests/test_config.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'scalper'`

**Step 3: Write minimal implementation**

```python
# scalper/__init__.py
# (empty)

# scalper/config.py
from dataclasses import dataclass, field
import os
from dotenv import load_dotenv


@dataclass
class Config:
    # Bybit API
    bybit_api_key: str = ''
    bybit_api_secret: str = ''
    bybit_demo: bool = True

    # Баланс и позиции
    balance: float = 200.0
    leverage: int = 20
    max_risk_per_trade: float = 0.5       # 50% баланса на сделку

    # Риск-менеджмент
    max_daily_loss: float = 30.0          # -$30 → стоп на день
    max_consecutive_losses: int = 10      # 10 убытков подряд → пауза
    pause_after_losses_minutes: int = 60  # пауза 1 час

    # Сканирование
    scan_interval: int = 30               # секунд между сканами
    scalp_timeframe: str = '3m'           # основной ТФ
    trend_timeframe: str = '15m'          # старший ТФ для фильтра
    top_n_coins: int = 50                 # топ N монет по объёму

    # Комиссия Bybit
    taker_fee: float = 0.00055            # 0.055%

    # Индикаторы и сигналы
    atr_sl_multiplier: float = 1.5        # SL = ATR × 1.5
    tp_ratio: float = 2.0                 # TP = SL × 2.0
    adx_min: int = 20                     # мин ADX для входа
    ema_fast: int = 9                     # быстрая EMA
    ema_slow: int = 21                    # медленная EMA
    rsi_period: int = 14
    rsi_oversold: int = 35
    rsi_overbought: int = 65
    atr_period: int = 14
    adx_period: int = 14
    volume_ma_period: int = 20            # MA объёма для фильтра

    # Веб
    web_port: int = 5001

    @classmethod
    def from_env(cls) -> 'Config':
        load_dotenv()
        kwargs = {}
        env_map = {
            'BYBIT_API_KEY': ('bybit_api_key', str),
            'BYBIT_API_SECRET': ('bybit_api_secret', str),
            'BYBIT_DEMO': ('bybit_demo', lambda v: v.lower() in ('true', '1', 'yes')),
            'BALANCE': ('balance', float),
            'LEVERAGE': ('leverage', int),
            'MAX_DAILY_LOSS': ('max_daily_loss', float),
            'MAX_CONSECUTIVE_LOSSES': ('max_consecutive_losses', int),
            'SCAN_INTERVAL': ('scan_interval', int),
            'SCALP_TIMEFRAME': ('scalp_timeframe', str),
            'TOP_N_COINS': ('top_n_coins', int),
            'WEB_PORT': ('web_port', int),
        }
        for env_key, (attr, converter) in env_map.items():
            val = os.getenv(env_key)
            if val is not None:
                kwargs[attr] = converter(val)
        return cls(**kwargs)
```

**Step 4: Run tests**

```bash
python -m pytest tests/test_config.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add scalper/__init__.py scalper/config.py tests/__init__.py tests/test_config.py
git commit -m "feat: add Config dataclass with env loading"
```

---

## Task 2: Индикаторы (EMA, RSI, ATR, ADX)

**Files:**
- Create: `scalper/indicators.py`
- Test: `tests/test_indicators.py`

**Step 1: Write the failing tests**

```python
# tests/test_indicators.py
import pytest
import numpy as np
from scalper.indicators import calc_ema, calc_rsi, calc_atr, calc_adx, calc_volume_ratio


def _make_ohlcv(n=100):
    """Генерирует тестовые OHLCV данные (синусоида + шум)."""
    np.random.seed(42)
    t = np.linspace(0, 4 * np.pi, n)
    close = 100 + 10 * np.sin(t) + np.random.randn(n) * 0.5
    high = close + np.abs(np.random.randn(n)) * 0.5
    low = close - np.abs(np.random.randn(n)) * 0.5
    opn = (close + np.random.randn(n) * 0.2)
    volume = 1000 + np.random.randn(n) * 100
    return opn, high, low, close, np.abs(volume)


class TestEMA:
    def test_length(self):
        _, _, _, close, _ = _make_ohlcv(50)
        ema = calc_ema(close, 9)
        assert len(ema) == len(close)

    def test_smoothing(self):
        _, _, _, close, _ = _make_ohlcv(50)
        ema = calc_ema(close, 9)
        # EMA должна быть более гладкой чем close
        ema_diff = np.abs(np.diff(ema[9:]))
        close_diff = np.abs(np.diff(close[9:]))
        assert np.std(ema_diff) < np.std(close_diff)


class TestRSI:
    def test_range(self):
        _, _, _, close, _ = _make_ohlcv(100)
        rsi = calc_rsi(close, 14)
        valid = rsi[~np.isnan(rsi)]
        assert np.all(valid >= 0) and np.all(valid <= 100)

    def test_length(self):
        _, _, _, close, _ = _make_ohlcv(100)
        rsi = calc_rsi(close, 14)
        assert len(rsi) == len(close)


class TestATR:
    def test_positive(self):
        _, high, low, close, _ = _make_ohlcv(100)
        atr = calc_atr(high, low, close, 14)
        valid = atr[~np.isnan(atr)]
        assert np.all(valid > 0)

    def test_length(self):
        _, high, low, close, _ = _make_ohlcv(100)
        atr = calc_atr(high, low, close, 14)
        assert len(atr) == len(close)


class TestADX:
    def test_range(self):
        _, high, low, close, _ = _make_ohlcv(100)
        adx = calc_adx(high, low, close, 14)
        valid = adx[~np.isnan(adx)]
        assert np.all(valid >= 0) and np.all(valid <= 100)

    def test_length(self):
        _, high, low, close, _ = _make_ohlcv(100)
        adx = calc_adx(high, low, close, 14)
        assert len(adx) == len(close)


class TestVolumeRatio:
    def test_ratio(self):
        _, _, _, _, volume = _make_ohlcv(50)
        ratio = calc_volume_ratio(volume, 20)
        # ratio > 1 означает объём выше среднего
        assert len(ratio) == len(volume)
        valid = ratio[~np.isnan(ratio)]
        assert np.all(valid > 0)
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_indicators.py -v
```
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write implementation**

```python
# scalper/indicators.py
"""Расчёт технических индикаторов на numpy. Без pandas — легче для Pi."""
import numpy as np


def calc_ema(data: np.ndarray, period: int) -> np.ndarray:
    """Exponential Moving Average."""
    ema = np.full_like(data, np.nan, dtype=float)
    if len(data) < period:
        return ema
    ema[period - 1] = np.mean(data[:period])
    k = 2.0 / (period + 1)
    for i in range(period, len(data)):
        ema[i] = data[i] * k + ema[i - 1] * (1 - k)
    return ema


def calc_rsi(close: np.ndarray, period: int = 14) -> np.ndarray:
    """Relative Strength Index (Wilder's smoothing)."""
    rsi = np.full_like(close, np.nan, dtype=float)
    if len(close) < period + 1:
        return rsi
    delta = np.diff(close)
    gains = np.where(delta > 0, delta, 0.0)
    losses = np.where(delta < 0, -delta, 0.0)

    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    for i in range(period, len(delta)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            rsi[i + 1] = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi[i + 1] = 100.0 - 100.0 / (1.0 + rs)

    # Первое значение RSI
    if avg_loss == 0:
        rsi[period] = 100.0
    else:
        first_avg_gain = np.mean(gains[:period])
        first_avg_loss = np.mean(losses[:period])
        if first_avg_loss == 0:
            rsi[period] = 100.0
        else:
            rsi[period] = 100.0 - 100.0 / (1.0 + first_avg_gain / first_avg_loss)
    return rsi


def calc_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray,
             period: int = 14) -> np.ndarray:
    """Average True Range (Wilder's smoothing)."""
    atr = np.full_like(close, np.nan, dtype=float)
    if len(close) < 2:
        return atr
    tr = np.zeros(len(close))
    tr[0] = high[0] - low[0]
    for i in range(1, len(close)):
        tr[i] = max(high[i] - low[i],
                     abs(high[i] - close[i - 1]),
                     abs(low[i] - close[i - 1]))
    if len(tr) < period:
        return atr
    atr[period - 1] = np.mean(tr[:period])
    for i in range(period, len(tr)):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    return atr


def calc_adx(high: np.ndarray, low: np.ndarray, close: np.ndarray,
             period: int = 14) -> np.ndarray:
    """Average Directional Index."""
    adx = np.full_like(close, np.nan, dtype=float)
    n = len(close)
    if n < period * 2:
        return adx

    plus_dm = np.zeros(n)
    minus_dm = np.zeros(n)
    tr = np.zeros(n)

    for i in range(1, n):
        up = high[i] - high[i - 1]
        down = low[i - 1] - low[i]
        plus_dm[i] = up if (up > down and up > 0) else 0.0
        minus_dm[i] = down if (down > up and down > 0) else 0.0
        tr[i] = max(high[i] - low[i],
                     abs(high[i] - close[i - 1]),
                     abs(low[i] - close[i - 1]))

    # Wilder's smoothing for TR, +DM, -DM
    atr_s = np.zeros(n)
    plus_dm_s = np.zeros(n)
    minus_dm_s = np.zeros(n)

    atr_s[period] = np.sum(tr[1:period + 1])
    plus_dm_s[period] = np.sum(plus_dm[1:period + 1])
    minus_dm_s[period] = np.sum(minus_dm[1:period + 1])

    for i in range(period + 1, n):
        atr_s[i] = atr_s[i - 1] - atr_s[i - 1] / period + tr[i]
        plus_dm_s[i] = plus_dm_s[i - 1] - plus_dm_s[i - 1] / period + plus_dm[i]
        minus_dm_s[i] = minus_dm_s[i - 1] - minus_dm_s[i - 1] / period + minus_dm[i]

    # +DI, -DI
    plus_di = np.zeros(n)
    minus_di = np.zeros(n)
    dx = np.zeros(n)

    for i in range(period, n):
        if atr_s[i] != 0:
            plus_di[i] = 100.0 * plus_dm_s[i] / atr_s[i]
            minus_di[i] = 100.0 * minus_dm_s[i] / atr_s[i]
        di_sum = plus_di[i] + minus_di[i]
        if di_sum != 0:
            dx[i] = 100.0 * abs(plus_di[i] - minus_di[i]) / di_sum

    # ADX = Wilder's smooth of DX
    start = period * 2
    if start < n:
        adx[start] = np.mean(dx[period + 1:start + 1])
        for i in range(start + 1, n):
            adx[i] = (adx[i - 1] * (period - 1) + dx[i]) / period

    return adx


def calc_volume_ratio(volume: np.ndarray, period: int = 20) -> np.ndarray:
    """Отношение текущего объёма к скользящей средней."""
    ratio = np.full_like(volume, np.nan, dtype=float)
    if len(volume) < period:
        return ratio
    vol_ma = calc_ema(volume, period)
    mask = vol_ma > 0
    ratio[mask] = volume[mask] / vol_ma[mask]
    return ratio
```

**Step 4: Run tests**

```bash
python -m pytest tests/test_indicators.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add scalper/indicators.py tests/test_indicators.py
git commit -m "feat: add indicator calculations (EMA, RSI, ATR, ADX, volume ratio)"
```

---

## Task 3: Биржа — обёртка над ccxt

**Files:**
- Create: `scalper/exchange.py`
- Test: `tests/test_exchange.py`

**Step 1: Write the failing test**

```python
# tests/test_exchange.py
import pytest
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def config():
    from scalper.config import Config
    return Config(bybit_api_key='test', bybit_api_secret='test', bybit_demo=True)


@pytest.mark.asyncio
async def test_get_top_symbols(config):
    """Получение топ-N символов по объёму."""
    from scalper.exchange import Exchange

    mock_tickers = {
        'BTC/USDT:USDT': {'symbol': 'BTC/USDT:USDT', 'quoteVolume': 5_000_000_000},
        'ETH/USDT:USDT': {'symbol': 'ETH/USDT:USDT', 'quoteVolume': 2_000_000_000},
        'DOGE/USDT:USDT': {'symbol': 'DOGE/USDT:USDT', 'quoteVolume': 500_000_000},
        'SHIB/USDT:USDT': {'symbol': 'SHIB/USDT:USDT', 'quoteVolume': 100_000_000},
        'BTC/USDT': {'symbol': 'BTC/USDT', 'quoteVolume': 999_999_999},  # spot — исключить
    }

    ex = Exchange(config)
    with patch.object(ex, '_exchange') as mock_ex:
        mock_ex.fetch_tickers = AsyncMock(return_value=mock_tickers)
        top = await ex.get_top_symbols(3)

    assert top == ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'DOGE/USDT:USDT']


@pytest.mark.asyncio
async def test_fetch_ohlcv(config):
    """Получение свечей, конвертация в numpy."""
    from scalper.exchange import Exchange

    raw = [
        [1700000000000, 100.0, 105.0, 95.0, 102.0, 1000.0],
        [1700000060000, 102.0, 107.0, 100.0, 105.0, 1200.0],
    ]

    ex = Exchange(config)
    with patch.object(ex, '_exchange') as mock_ex:
        mock_ex.fetch_ohlcv = AsyncMock(return_value=raw)
        ohlcv = await ex.fetch_ohlcv('BTC/USDT:USDT', '1m', limit=2)

    assert ohlcv['open'].shape == (2,)
    assert ohlcv['close'][0] == 102.0
    assert ohlcv['high'][1] == 107.0
    assert ohlcv['volume'][1] == 1200.0
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_exchange.py -v
```
Expected: FAIL

**Step 3: Write implementation**

```python
# scalper/exchange.py
"""Обёртка над ccxt для работы с Bybit."""
import ccxt.async_support as ccxt_async
import numpy as np
from scalper.config import Config


class Exchange:
    def __init__(self, config: Config):
        self._config = config
        self._exchange = ccxt_async.bybit({
            'apiKey': config.bybit_api_key,
            'secret': config.bybit_api_secret,
            'options': {'defaultType': 'swap'},
            'enableRateLimit': True,
        })
        if config.bybit_demo:
            self._exchange.set_sandbox_mode(True)

    async def start(self):
        await self._exchange.load_markets()

    async def close(self):
        await self._exchange.close()

    async def get_top_symbols(self, n: int = 50) -> list[str]:
        """Топ N USDT-перпов по 24h объёму."""
        tickers = await self._exchange.fetch_tickers()
        perps = [
            t for s, t in tickers.items()
            if s.endswith(':USDT') and t.get('quoteVolume')
        ]
        perps.sort(key=lambda t: t['quoteVolume'], reverse=True)
        return [t['symbol'] for t in perps[:n]]

    async def fetch_ohlcv(self, symbol: str, timeframe: str,
                          limit: int = 100) -> dict[str, np.ndarray]:
        """Получить свечи и вернуть как dict numpy массивов."""
        raw = await self._exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        arr = np.array(raw, dtype=float)
        return {
            'timestamp': arr[:, 0],
            'open': arr[:, 1],
            'high': arr[:, 2],
            'low': arr[:, 3],
            'close': arr[:, 4],
            'volume': arr[:, 5],
        }

    async def get_price(self, symbol: str) -> float:
        """Текущая цена (last)."""
        ticker = await self._exchange.fetch_ticker(symbol)
        return ticker['last']
```

**Step 4: Run tests**

```bash
pip install pytest-asyncio
python -m pytest tests/test_exchange.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add scalper/exchange.py tests/test_exchange.py
git commit -m "feat: add Exchange wrapper over ccxt with top symbols and OHLCV"
```

---

## Task 4: Генератор сигналов

**Files:**
- Create: `scalper/signals.py`
- Test: `tests/test_signals.py`

**Step 1: Write the failing tests**

```python
# tests/test_signals.py
import pytest
import numpy as np
from scalper.signals import SignalEngine, Signal


def _make_trending_up(n=100):
    """Создаёт данные с явным восходящим трендом."""
    np.random.seed(42)
    base = np.linspace(100, 130, n)
    noise = np.random.randn(n) * 0.3
    close = base + noise
    high = close + np.abs(np.random.randn(n)) * 0.5
    low = close - np.abs(np.random.randn(n)) * 0.5
    opn = close - np.random.randn(n) * 0.2
    volume = np.linspace(1000, 2000, n) + np.abs(np.random.randn(n)) * 50
    return {
        'open': opn, 'high': high, 'low': low,
        'close': close, 'volume': volume,
        'timestamp': np.arange(n, dtype=float),
    }


def _make_flat(n=100):
    """Создаёт боковик (ADX будет низкий)."""
    np.random.seed(42)
    close = 100 + np.random.randn(n) * 0.2
    high = close + 0.1
    low = close - 0.1
    opn = close.copy()
    volume = np.full(n, 500.0)
    return {
        'open': opn, 'high': high, 'low': low,
        'close': close, 'volume': volume,
        'timestamp': np.arange(n, dtype=float),
    }


class TestSignalEngine:
    def test_signal_dataclass(self):
        s = Signal(direction='long', strength=3, entry_price=100.0,
                   sl_price=99.0, tp_price=102.0, reasons=['ema_cross', 'rsi', 'volume'])
        assert s.direction == 'long'
        assert s.strength == 3
        assert len(s.reasons) == 3

    def test_no_signal_on_flat(self):
        from scalper.config import Config
        engine = SignalEngine(Config())
        ohlcv = _make_flat(100)
        signal = engine.evaluate(ohlcv)
        assert signal is None  # боковик → нет сигнала

    def test_signal_has_adaptive_sl_tp(self):
        from scalper.config import Config
        engine = SignalEngine(Config())
        ohlcv = _make_trending_up(100)
        signal = engine.evaluate(ohlcv)
        if signal is not None:
            # SL и TP должны быть установлены
            assert signal.sl_price > 0
            assert signal.tp_price > 0
            # TP дальше от входа чем SL
            if signal.direction == 'long':
                assert signal.tp_price > signal.entry_price > signal.sl_price
            else:
                assert signal.tp_price < signal.entry_price < signal.sl_price
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_signals.py -v
```
Expected: FAIL

**Step 3: Write implementation**

```python
# scalper/signals.py
"""Мульти-индикаторный генератор сигналов."""
from dataclasses import dataclass, field
import numpy as np
from scalper.config import Config
from scalper.indicators import calc_ema, calc_rsi, calc_atr, calc_adx, calc_volume_ratio


@dataclass
class Signal:
    direction: str          # 'long' или 'short'
    strength: int           # кол-во совпавших индикаторов (1-4)
    entry_price: float
    sl_price: float         # адаптивный SL по ATR
    tp_price: float         # TP = SL × ratio
    reasons: list[str] = field(default_factory=list)


class SignalEngine:
    """Оценивает OHLCV данные и возвращает Signal или None."""

    def __init__(self, config: Config):
        self.cfg = config

    def evaluate(self, ohlcv: dict[str, np.ndarray]) -> Signal | None:
        close = ohlcv['close']
        high = ohlcv['high']
        low = ohlcv['low']
        volume = ohlcv['volume']

        if len(close) < 50:
            return None

        # Расчёт индикаторов
        ema_fast = calc_ema(close, self.cfg.ema_fast)
        ema_slow = calc_ema(close, self.cfg.ema_slow)
        rsi = calc_rsi(close, self.cfg.rsi_period)
        atr = calc_atr(high, low, close, self.cfg.atr_period)
        adx = calc_adx(high, low, close, self.cfg.adx_period)
        vol_ratio = calc_volume_ratio(volume, self.cfg.volume_ma_period)

        # Текущие значения (последняя свеча)
        i = len(close) - 1
        if any(np.isnan(x) for x in [ema_fast[i], ema_slow[i], rsi[i], atr[i], adx[i]]):
            return None

        # Фильтр: ADX < min → боковик, не торгуем
        if adx[i] < self.cfg.adx_min:
            return None

        # Подсчёт сигналов LONG
        long_reasons = []
        short_reasons = []

        # 1. EMA cross
        if ema_fast[i] > ema_slow[i] and ema_fast[i - 1] <= ema_slow[i - 1]:
            long_reasons.append('ema_cross')
        elif ema_fast[i] < ema_slow[i] and ema_fast[i - 1] >= ema_slow[i - 1]:
            short_reasons.append('ema_cross')
        # EMA расположение (не кросс, но тренд)
        elif ema_fast[i] > ema_slow[i]:
            long_reasons.append('ema_trend')
        elif ema_fast[i] < ema_slow[i]:
            short_reasons.append('ema_trend')

        # 2. RSI
        if rsi[i] < self.cfg.rsi_oversold:
            long_reasons.append('rsi_oversold')
        elif rsi[i] > self.cfg.rsi_overbought:
            short_reasons.append('rsi_overbought')

        # 3. Объём выше среднего
        if not np.isnan(vol_ratio[i]) and vol_ratio[i] > 1.2:
            long_reasons.append('volume_spike')
            short_reasons.append('volume_spike')

        # 4. Моментум: close > close[-3]
        if close[i] > close[i - 3]:
            long_reasons.append('momentum')
        elif close[i] < close[i - 3]:
            short_reasons.append('momentum')

        # Нужно минимум 2 совпадения для входа
        entry_price = close[i]
        current_atr = atr[i]
        sl_distance = current_atr * self.cfg.atr_sl_multiplier

        if len(long_reasons) >= 2:
            sl_price = entry_price - sl_distance
            tp_price = entry_price + sl_distance * self.cfg.tp_ratio
            return Signal(
                direction='long',
                strength=len(long_reasons),
                entry_price=entry_price,
                sl_price=sl_price,
                tp_price=tp_price,
                reasons=long_reasons,
            )

        if len(short_reasons) >= 2:
            sl_price = entry_price + sl_distance
            tp_price = entry_price - sl_distance * self.cfg.tp_ratio
            return Signal(
                direction='short',
                strength=len(short_reasons),
                entry_price=entry_price,
                sl_price=sl_price,
                tp_price=tp_price,
                reasons=short_reasons,
            )

        return None
```

**Step 4: Run tests**

```bash
python -m pytest tests/test_signals.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add scalper/signals.py tests/test_signals.py
git commit -m "feat: add multi-indicator signal engine with adaptive SL/TP"
```

---

## Task 5: Фильтры входа (старший ТФ)

**Files:**
- Create: `scalper/filters.py`
- Test: `tests/test_filters.py`

**Step 1: Write the failing tests**

```python
# tests/test_filters.py
import pytest
import numpy as np
from scalper.filters import TrendFilter


def test_uptrend_allows_long():
    """Восходящий тренд на старшем ТФ → лонг разрешён."""
    n = 50
    close = np.linspace(100, 120, n)
    high = close + 1
    low = close - 1
    ohlcv = {'close': close, 'high': high, 'low': low,
             'open': close, 'volume': np.full(n, 1000.0),
             'timestamp': np.arange(n, dtype=float)}
    f = TrendFilter()
    assert f.is_allowed('long', ohlcv) is True
    assert f.is_allowed('short', ohlcv) is False


def test_downtrend_allows_short():
    """Нисходящий тренд → шорт разрешён."""
    n = 50
    close = np.linspace(120, 100, n)
    high = close + 1
    low = close - 1
    ohlcv = {'close': close, 'high': high, 'low': low,
             'open': close, 'volume': np.full(n, 1000.0),
             'timestamp': np.arange(n, dtype=float)}
    f = TrendFilter()
    assert f.is_allowed('short', ohlcv) is True
    assert f.is_allowed('long', ohlcv) is False
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_filters.py -v
```
Expected: FAIL

**Step 3: Write implementation**

```python
# scalper/filters.py
"""Фильтры входа — не позволяют торговать против тренда."""
import numpy as np
from scalper.indicators import calc_ema, calc_adx


class TrendFilter:
    """Фильтр по тренду старшего таймфрейма.
    
    Лонг разрешён только если EMA fast > EMA slow (восходящий тренд).
    Шорт разрешён только если EMA fast < EMA slow (нисходящий тренд).
    """

    def __init__(self, ema_fast: int = 9, ema_slow: int = 21):
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow

    def is_allowed(self, direction: str, ohlcv_senior: dict[str, np.ndarray]) -> bool:
        close = ohlcv_senior['close']
        if len(close) < self.ema_slow + 5:
            return False

        fast = calc_ema(close, self.ema_fast)
        slow = calc_ema(close, self.ema_slow)
        i = len(close) - 1

        if np.isnan(fast[i]) or np.isnan(slow[i]):
            return False

        if direction == 'long':
            return fast[i] > slow[i]
        elif direction == 'short':
            return fast[i] < slow[i]
        return False
```

**Step 4: Run tests**

```bash
python -m pytest tests/test_filters.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add scalper/filters.py tests/test_filters.py
git commit -m "feat: add trend filter for senior timeframe"
```

---

## Task 6: Риск-менеджмент

**Files:**
- Create: `scalper/risk.py`
- Test: `tests/test_risk.py`

**Step 1: Write the failing tests**

```python
# tests/test_risk.py
import pytest
from scalper.risk import RiskManager
from scalper.config import Config


@pytest.fixture
def rm():
    cfg = Config(balance=200, leverage=20, max_risk_per_trade=0.5,
                 max_consecutive_losses=10, pause_after_losses_minutes=60,
                 max_daily_loss=30)
    return RiskManager(cfg)


class TestPositionSize:
    def test_position_value(self, rm):
        size = rm.calc_position_size(50000.0)
        # 200 * 0.5 = $100 риска × 20 leverage = $2000 позиция
        # qty = 2000 / 50000 = 0.04 BTC
        assert abs(size['qty'] - 0.04) < 0.001
        assert abs(size['position_value'] - 2000.0) < 1.0
        assert abs(size['margin'] - 100.0) < 1.0


class TestConsecutiveLosses:
    def test_no_pause_initially(self, rm):
        assert rm.should_pause() is False

    def test_pause_after_10_losses(self, rm):
        for _ in range(10):
            rm.record_loss()
        assert rm.should_pause() is True

    def test_reset_on_win(self, rm):
        for _ in range(9):
            rm.record_loss()
        rm.record_win()
        assert rm.should_pause() is False


class TestDailyLimit:
    def test_daily_loss_stop(self, rm):
        rm.record_daily_pnl(-30.0)
        assert rm.is_daily_limit_hit() is True

    def test_daily_ok(self, rm):
        rm.record_daily_pnl(-15.0)
        assert rm.is_daily_limit_hit() is False


class TestTrailingStop:
    def test_trailing_long(self, rm):
        # Вход в лонг, цена растёт → стоп подтягивается
        trail = rm.create_trailing_stop('long', entry=100.0, sl=98.0)
        new_sl = trail.update(105.0)  # цена выросла
        assert new_sl > 98.0  # стоп поднялся
        new_sl2 = trail.update(103.0)  # цена упала, но стоп не опускается
        assert new_sl2 == new_sl

    def test_trailing_short(self, rm):
        trail = rm.create_trailing_stop('short', entry=100.0, sl=102.0)
        new_sl = trail.update(95.0)  # цена упала
        assert new_sl < 102.0  # стоп опустился
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_risk.py -v
```
Expected: FAIL

**Step 3: Write implementation**

```python
# scalper/risk.py
"""Риск-менеджмент: позиционирование, лимиты, trailing stop."""
from dataclasses import dataclass
from datetime import datetime, timedelta
from scalper.config import Config


class TrailingStop:
    """Подтягивающийся стоп-лосс."""

    def __init__(self, direction: str, entry: float, sl: float):
        self.direction = direction
        self.current_sl = sl
        self.entry = entry
        self._distance = abs(entry - sl)  # фиксируем дистанцию

    def update(self, current_price: float) -> float:
        """Обновить trailing stop по текущей цене. Возвращает новый SL."""
        if self.direction == 'long':
            new_sl = current_price - self._distance
            if new_sl > self.current_sl:
                self.current_sl = new_sl
        else:  # short
            new_sl = current_price + self._distance
            if new_sl < self.current_sl:
                self.current_sl = new_sl
        return self.current_sl

    def is_hit(self, current_price: float) -> bool:
        if self.direction == 'long':
            return current_price <= self.current_sl
        return current_price >= self.current_sl


class RiskManager:
    def __init__(self, config: Config):
        self.cfg = config
        self._consecutive_losses = 0
        self._daily_pnl = 0.0
        self._pause_until: datetime | None = None
        self._last_reset_date: str = ''

    def calc_position_size(self, price: float) -> dict:
        """Рассчитать размер позиции."""
        margin = self.cfg.balance * self.cfg.max_risk_per_trade
        position_value = margin * self.cfg.leverage
        qty = position_value / price
        return {
            'qty': qty,
            'margin': margin,
            'position_value': position_value,
        }

    def record_loss(self):
        self._consecutive_losses += 1

    def record_win(self):
        self._consecutive_losses = 0

    def record_daily_pnl(self, pnl: float):
        self._daily_pnl += pnl

    def reset_daily(self):
        self._daily_pnl = 0.0
        self._consecutive_losses = 0
        self._pause_until = None

    def should_pause(self) -> bool:
        if self._pause_until and datetime.now() < self._pause_until:
            return True
        if self._consecutive_losses >= self.cfg.max_consecutive_losses:
            self._pause_until = datetime.now() + timedelta(
                minutes=self.cfg.pause_after_losses_minutes)
            self._consecutive_losses = 0  # сбросим после установки паузы
            return True
        return False

    def is_daily_limit_hit(self) -> bool:
        return self._daily_pnl <= -self.cfg.max_daily_loss

    def can_trade(self) -> bool:
        """Главная проверка: можно ли сейчас торговать."""
        # Авто-сброс дневных лимитов
        today = datetime.now().strftime('%Y-%m-%d')
        if today != self._last_reset_date:
            self.reset_daily()
            self._last_reset_date = today
        return not self.should_pause() and not self.is_daily_limit_hit()

    def create_trailing_stop(self, direction: str, entry: float,
                             sl: float) -> TrailingStop:
        return TrailingStop(direction, entry, sl)
```

**Step 4: Run tests**

```bash
python -m pytest tests/test_risk.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add scalper/risk.py tests/test_risk.py
git commit -m "feat: add risk manager with trailing stop and daily limits"
```

---

## Task 7: SQLite хранилище

**Files:**
- Create: `scalper/storage.py`
- Test: `tests/test_storage.py`

**Step 1: Write the failing tests**

```python
# tests/test_storage.py
import pytest
import os
from scalper.storage import Storage


@pytest.fixture
def db(tmp_path):
    db_path = str(tmp_path / 'test.db')
    s = Storage(db_path)
    yield s
    s.close()


class TestTrades:
    def test_open_and_close_trade(self, db):
        tid = db.open_trade(
            symbol='BTC/USDT:USDT', direction='long', qty=0.04,
            entry_price=50000.0, sl_price=49500.0, tp_price=51000.0,
            leverage=20, margin=100.0,
            reasons='ema_cross,rsi_oversold'
        )
        assert tid > 0

        trade = db.get_open_trades()
        assert len(trade) == 1
        assert trade[0]['symbol'] == 'BTC/USDT:USDT'

        db.close_trade(tid, exit_price=51000.0, pnl=40.0,
                       pnl_pct=20.0, close_reason='tp_hit')
        assert len(db.get_open_trades()) == 0

    def test_daily_stats(self, db):
        tid = db.open_trade(
            symbol='ETH/USDT:USDT', direction='short', qty=1.0,
            entry_price=3000.0, sl_price=3030.0, tp_price=2940.0,
            leverage=20, margin=100.0, reasons='ema_cross,momentum'
        )
        db.close_trade(tid, exit_price=2950.0, pnl=50.0,
                       pnl_pct=25.0, close_reason='tp_hit')
        stats = db.get_daily_stats()
        assert stats['total_trades'] == 1
        assert stats['total_pnl'] == 50.0

    def test_equity_snapshot(self, db):
        db.save_equity_snapshot(200.0)
        db.save_equity_snapshot(210.0)
        history = db.get_equity_history()
        assert len(history) == 2
        assert history[-1]['balance'] == 210.0
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_storage.py -v
```
Expected: FAIL

**Step 3: Write implementation**

```python
# scalper/storage.py
"""SQLite хранилище сделок и статистики."""
import sqlite3
from datetime import datetime, date


class Storage:
    def __init__(self, db_path: str = 'data/scalper.db'):
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        self._conn.executescript('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                direction TEXT NOT NULL,
                qty REAL NOT NULL,
                leverage INTEGER NOT NULL,
                margin REAL NOT NULL,
                entry_price REAL NOT NULL,
                sl_price REAL NOT NULL,
                tp_price REAL NOT NULL,
                exit_price REAL,
                pnl REAL,
                pnl_pct REAL,
                reasons TEXT,
                close_reason TEXT,
                opened_at TEXT NOT NULL,
                closed_at TEXT,
                status TEXT NOT NULL DEFAULT 'open'
            );

            CREATE TABLE IF NOT EXISTS equity_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                balance REAL NOT NULL,
                timestamp TEXT NOT NULL
            );
        ''')
        self._conn.commit()

    def open_trade(self, symbol: str, direction: str, qty: float,
                   entry_price: float, sl_price: float, tp_price: float,
                   leverage: int, margin: float, reasons: str = '') -> int:
        cur = self._conn.execute(
            '''INSERT INTO trades
               (symbol, direction, qty, leverage, margin, entry_price,
                sl_price, tp_price, reasons, opened_at, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')''',
            (symbol, direction, qty, leverage, margin, entry_price,
             sl_price, tp_price, reasons, datetime.now().isoformat())
        )
        self._conn.commit()
        return cur.lastrowid

    def close_trade(self, trade_id: int, exit_price: float, pnl: float,
                    pnl_pct: float, close_reason: str):
        self._conn.execute(
            '''UPDATE trades SET exit_price=?, pnl=?, pnl_pct=?,
               close_reason=?, closed_at=?, status='closed'
               WHERE id=?''',
            (exit_price, pnl, pnl_pct, close_reason,
             datetime.now().isoformat(), trade_id)
        )
        self._conn.commit()

    def get_open_trades(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM trades WHERE status='open'"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_daily_stats(self, day: str = None) -> dict:
        if day is None:
            day = date.today().isoformat()
        rows = self._conn.execute(
            "SELECT * FROM trades WHERE status='closed' AND closed_at LIKE ?",
            (f'{day}%',)
        ).fetchall()
        trades = [dict(r) for r in rows]
        total_pnl = sum(t['pnl'] or 0 for t in trades)
        wins = sum(1 for t in trades if (t['pnl'] or 0) > 0)
        return {
            'total_trades': len(trades),
            'total_pnl': total_pnl,
            'wins': wins,
            'losses': len(trades) - wins,
            'win_rate': (wins / len(trades) * 100) if trades else 0,
        }

    def get_all_stats(self) -> dict:
        rows = self._conn.execute(
            "SELECT * FROM trades WHERE status='closed'"
        ).fetchall()
        trades = [dict(r) for r in rows]
        total_pnl = sum(t['pnl'] or 0 for t in trades)
        wins = sum(1 for t in trades if (t['pnl'] or 0) > 0)
        return {
            'total_trades': len(trades),
            'total_pnl': total_pnl,
            'wins': wins,
            'losses': len(trades) - wins,
            'win_rate': (wins / len(trades) * 100) if trades else 0,
        }

    def get_trade_history(self, limit: int = 50) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM trades WHERE status='closed' ORDER BY closed_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def save_equity_snapshot(self, balance: float):
        self._conn.execute(
            "INSERT INTO equity_history (balance, timestamp) VALUES (?, ?)",
            (balance, datetime.now().isoformat())
        )
        self._conn.commit()

    def get_equity_history(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM equity_history ORDER BY timestamp"
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        self._conn.close()
```

**Step 4: Run tests**

```bash
python -m pytest tests/test_storage.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add scalper/storage.py tests/test_storage.py
git commit -m "feat: add SQLite storage for trades and equity history"
```

---

## Task 8: Сканер монет

**Files:**
- Create: `scalper/scanner.py`
- Test: `tests/test_scanner.py`

**Step 1: Write the failing test**

```python
# tests/test_scanner.py
import pytest
import numpy as np
from unittest.mock import AsyncMock, MagicMock
from scalper.scanner import Scanner
from scalper.signals import Signal


def _dummy_ohlcv(n=100, trend='up'):
    base = np.linspace(100, 130, n) if trend == 'up' else np.linspace(130, 100, n)
    noise = np.random.randn(n) * 0.3
    close = base + noise
    return {
        'open': close - 0.1, 'high': close + 0.5, 'low': close - 0.5,
        'close': close, 'volume': np.full(n, 1500.0),
        'timestamp': np.arange(n, dtype=float),
    }


@pytest.mark.asyncio
async def test_scanner_ranks_by_strength():
    """Сканер возвращает монеты отсортированные по силе сигнала."""
    from scalper.config import Config
    cfg = Config()

    scanner = Scanner(cfg)

    # Мокаем exchange и signal engine
    scanner._exchange = MagicMock()
    scanner._exchange.get_top_symbols = AsyncMock(
        return_value=['BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT'])
    scanner._exchange.fetch_ohlcv = AsyncMock(return_value=_dummy_ohlcv())

    # Подменяем signal engine чтобы вернуть разную силу
    results = iter([
        Signal('long', 3, 100.0, 98.0, 104.0, ['ema', 'rsi', 'vol']),
        None,  # ETH — нет сигнала
        Signal('short', 2, 100.0, 102.0, 96.0, ['ema', 'momentum']),
    ])
    scanner._signal_engine.evaluate = lambda ohlcv: next(results)
    scanner._trend_filter.is_allowed = lambda d, ohlcv: True

    opportunities = await scanner.scan()
    assert len(opportunities) == 2
    assert opportunities[0]['symbol'] == 'BTC/USDT:USDT'  # strength 3 first
    assert opportunities[0]['signal'].strength == 3
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_scanner.py -v
```
Expected: FAIL

**Step 3: Write implementation**

```python
# scalper/scanner.py
"""Сканер топ-50 монет — ищет лучшие сетапы для входа."""
import logging
from scalper.config import Config
from scalper.exchange import Exchange
from scalper.signals import SignalEngine
from scalper.filters import TrendFilter

log = logging.getLogger(__name__)


class Scanner:
    def __init__(self, config: Config, exchange: Exchange = None):
        self.cfg = config
        self._exchange = exchange or Exchange(config)
        self._signal_engine = SignalEngine(config)
        self._trend_filter = TrendFilter(config.ema_fast, config.ema_slow)

    async def scan(self) -> list[dict]:
        """Сканировать все монеты, вернуть отсортированные возможности."""
        symbols = await self._exchange.get_top_symbols(self.cfg.top_n_coins)
        opportunities = []

        for symbol in symbols:
            try:
                ohlcv = await self._exchange.fetch_ohlcv(
                    symbol, self.cfg.scalp_timeframe, limit=100)

                signal = self._signal_engine.evaluate(ohlcv)
                if signal is None:
                    continue

                # Проверка тренда старшего ТФ
                ohlcv_senior = await self._exchange.fetch_ohlcv(
                    symbol, self.cfg.trend_timeframe, limit=50)

                if not self._trend_filter.is_allowed(signal.direction, ohlcv_senior):
                    continue

                opportunities.append({
                    'symbol': symbol,
                    'signal': signal,
                    'price': ohlcv['close'][-1],
                })
            except Exception as e:
                log.warning(f"Ошибка сканирования {symbol}: {e}")
                continue

        # Сортировка по силе сигнала (больше = лучше)
        opportunities.sort(key=lambda x: x['signal'].strength, reverse=True)
        return opportunities
```

**Step 4: Run tests**

```bash
python -m pytest tests/test_scanner.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add scalper/scanner.py tests/test_scanner.py
git commit -m "feat: add coin scanner with ranking by signal strength"
```

---

## Task 9: Главный бот (торговый цикл)

**Files:**
- Create: `scalper/bot.py`
- Test: `tests/test_bot.py`

**Step 1: Write the failing tests**

```python
# tests/test_bot.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from scalper.bot import ScalperBot
from scalper.config import Config
from scalper.signals import Signal


@pytest.fixture
def bot():
    cfg = Config(balance=200, leverage=20)
    b = ScalperBot(cfg)
    b._scanner = MagicMock()
    b._exchange = MagicMock()
    b._storage = MagicMock()
    b._risk = MagicMock()
    return b


@pytest.mark.asyncio
async def test_bot_opens_trade(bot):
    """Бот открывает сделку при сигнале."""
    signal = Signal('long', 3, 50000.0, 49500.0, 51000.0,
                    ['ema_cross', 'rsi', 'volume'])
    bot._scanner.scan = AsyncMock(return_value=[
        {'symbol': 'BTC/USDT:USDT', 'signal': signal, 'price': 50000.0}
    ])
    bot._risk.can_trade.return_value = True
    bot._risk.calc_position_size.return_value = {
        'qty': 0.04, 'margin': 100.0, 'position_value': 2000.0}
    bot._risk.create_trailing_stop.return_value = MagicMock()
    bot._storage.get_open_trades.return_value = []
    bot._storage.open_trade.return_value = 1

    await bot.tick()

    bot._storage.open_trade.assert_called_once()
    call_kwargs = bot._storage.open_trade.call_args
    assert call_kwargs[1]['symbol'] == 'BTC/USDT:USDT'
    assert call_kwargs[1]['direction'] == 'long'


@pytest.mark.asyncio
async def test_bot_skips_when_paused(bot):
    """Бот не торгует когда пауза."""
    bot._risk.can_trade.return_value = False
    bot._storage.get_open_trades.return_value = []

    await bot.tick()

    bot._scanner.scan.assert_not_called()


@pytest.mark.asyncio
async def test_bot_closes_on_sl(bot):
    """Бот закрывает позицию при срабатывании SL."""
    bot._risk.can_trade.return_value = True
    open_trade = {
        'id': 1, 'symbol': 'BTC/USDT:USDT', 'direction': 'long',
        'qty': 0.04, 'entry_price': 50000.0, 'sl_price': 49500.0,
        'tp_price': 51000.0, 'leverage': 20, 'margin': 100.0,
    }
    bot._storage.get_open_trades.return_value = [open_trade]
    bot._exchange.get_price = AsyncMock(return_value=49400.0)
    # trailing stop hit
    trailing = MagicMock()
    trailing.update.return_value = 49500.0
    trailing.is_hit.return_value = True
    bot._open_positions = {1: {'trade': open_trade, 'trailing': trailing}}

    await bot.tick()

    bot._storage.close_trade.assert_called_once()
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_bot.py -v
```
Expected: FAIL

**Step 3: Write implementation**

```python
# scalper/bot.py
"""Главный скальпинг-бот — asyncio цикл."""
import asyncio
import logging
from datetime import datetime
from scalper.config import Config
from scalper.exchange import Exchange
from scalper.scanner import Scanner
from scalper.risk import RiskManager
from scalper.storage import Storage

log = logging.getLogger(__name__)


class ScalperBot:
    def __init__(self, config: Config):
        self.cfg = config
        self._exchange = Exchange(config)
        self._scanner = Scanner(config, self._exchange)
        self._risk = RiskManager(config)
        self._storage = Storage()
        self._open_positions: dict[int, dict] = {}  # trade_id → {trade, trailing}
        self._running = False
        self._callbacks: list = []  # для WebSocket уведомлений

    def on_update(self, callback):
        """Подписка на обновления (для веб-дашборда)."""
        self._callbacks.append(callback)

    def _notify(self, event: str, data: dict):
        for cb in self._callbacks:
            try:
                cb(event, data)
            except Exception:
                pass

    async def start(self):
        """Запустить бота."""
        await self._exchange.start()
        self._running = True
        # Восстановить открытые позиции из БД
        for trade in self._storage.get_open_trades():
            trailing = self._risk.create_trailing_stop(
                trade['direction'], trade['entry_price'], trade['sl_price'])
            self._open_positions[trade['id']] = {
                'trade': trade, 'trailing': trailing}
        log.info(f"Бот запущен. Баланс: ${self.cfg.balance}. "
                 f"Открытых позиций: {len(self._open_positions)}")

    async def stop(self):
        self._running = False
        await self._exchange.close()
        self._storage.close()
        log.info("Бот остановлен")

    async def tick(self):
        """Один цикл: проверить позиции → сканировать → войти."""
        # 1. Проверить открытые позиции (SL/TP/trailing)
        await self._check_open_positions()

        # 2. Можно ли торговать?
        if not self._risk.can_trade():
            log.info("Торговля приостановлена (лимиты)")
            return

        # 3. Уже есть открытая позиция? (1 позиция за раз для простоты)
        if self._open_positions:
            return

        # 4. Сканировать рынок
        opportunities = await self._scanner.scan()
        if not opportunities:
            return

        # 5. Взять лучшую возможность
        best = opportunities[0]
        await self._open_trade(best)

    async def _check_open_positions(self):
        """Проверить SL/TP/trailing для всех открытых позиций."""
        closed_ids = []
        for tid, pos in list(self._open_positions.items()):
            trade = pos['trade']
            trailing = pos['trailing']
            try:
                price = await self._exchange.get_price(trade['symbol'])
            except Exception as e:
                log.warning(f"Не могу получить цену {trade['symbol']}: {e}")
                continue

            # Обновить trailing stop
            trailing.update(price)

            # Проверить TP
            tp_hit = (trade['direction'] == 'long' and price >= trade['tp_price']) or \
                     (trade['direction'] == 'short' and price <= trade['tp_price'])

            # Проверить SL (trailing)
            sl_hit = trailing.is_hit(price)

            if tp_hit:
                await self._close_trade(tid, price, 'tp_hit')
                closed_ids.append(tid)
            elif sl_hit:
                await self._close_trade(tid, price, 'sl_hit')
                closed_ids.append(tid)

        for tid in closed_ids:
            del self._open_positions[tid]

    async def _open_trade(self, opportunity: dict):
        """Открыть новую сделку."""
        signal = opportunity['signal']
        symbol = opportunity['symbol']
        size = self._risk.calc_position_size(signal.entry_price)

        tid = self._storage.open_trade(
            symbol=symbol,
            direction=signal.direction,
            qty=size['qty'],
            entry_price=signal.entry_price,
            sl_price=signal.sl_price,
            tp_price=signal.tp_price,
            leverage=self.cfg.leverage,
            margin=size['margin'],
            reasons=','.join(signal.reasons),
        )

        trailing = self._risk.create_trailing_stop(
            signal.direction, signal.entry_price, signal.sl_price)

        trade_data = {
            'id': tid, 'symbol': symbol, 'direction': signal.direction,
            'qty': size['qty'], 'entry_price': signal.entry_price,
            'sl_price': signal.sl_price, 'tp_price': signal.tp_price,
            'leverage': self.cfg.leverage, 'margin': size['margin'],
        }
        self._open_positions[tid] = {'trade': trade_data, 'trailing': trailing}

        log.info(f"ОТКРЫТА: {signal.direction.upper()} {symbol} "
                 f"@ {signal.entry_price:.2f} | SL: {signal.sl_price:.2f} "
                 f"| TP: {signal.tp_price:.2f} | Причины: {signal.reasons}")

        self._notify('trade_open', trade_data)

    async def _close_trade(self, trade_id: int, exit_price: float, reason: str):
        """Закрыть сделку, обновить баланс."""
        pos = self._open_positions[trade_id]
        trade = pos['trade']

        # PnL расчёт
        if trade['direction'] == 'long':
            pnl_gross = (exit_price - trade['entry_price']) * trade['qty']
        else:
            pnl_gross = (trade['entry_price'] - exit_price) * trade['qty']

        # Комиссии
        entry_fee = trade['entry_price'] * trade['qty'] * self.cfg.taker_fee
        exit_fee = exit_price * trade['qty'] * self.cfg.taker_fee
        pnl = pnl_gross - entry_fee - exit_fee
        pnl_pct = (pnl / trade['margin']) * 100

        self._storage.close_trade(trade_id, exit_price, pnl, pnl_pct, reason)

        # Обновить баланс
        self.cfg.balance += pnl
        self._risk.record_daily_pnl(pnl)
        self._storage.save_equity_snapshot(self.cfg.balance)

        if pnl > 0:
            self._risk.record_win()
        else:
            self._risk.record_loss()

        log.info(f"ЗАКРЫТА: {trade['symbol']} | PnL: ${pnl:.2f} ({pnl_pct:.1f}%) "
                 f"| Причина: {reason} | Баланс: ${self.cfg.balance:.2f}")

        self._notify('trade_close', {
            'trade_id': trade_id, 'pnl': pnl, 'reason': reason,
            'balance': self.cfg.balance,
        })

    async def run(self):
        """Главный цикл бота."""
        await self.start()
        try:
            while self._running:
                try:
                    await self.tick()
                except Exception as e:
                    log.error(f"Ошибка в цикле: {e}", exc_info=True)
                await asyncio.sleep(self.cfg.scan_interval)
        finally:
            await self.stop()

    def get_status(self) -> dict:
        """Текущий статус для дашборда."""
        return {
            'running': self._running,
            'balance': self.cfg.balance,
            'open_positions': len(self._open_positions),
            'positions': [
                {**pos['trade'], 'current_sl': pos['trailing'].current_sl}
                for pos in self._open_positions.values()
            ],
            'daily_stats': self._storage.get_daily_stats(),
            'all_stats': self._storage.get_all_stats(),
            'can_trade': self._risk.can_trade(),
        }
```

**Step 4: Run tests**

```bash
python -m pytest tests/test_bot.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add scalper/bot.py tests/test_bot.py
git commit -m "feat: add main scalper bot with trading loop"
```

---

## Task 10: Веб-дашборд (Flask + SocketIO)

**Files:**
- Create: `scalper/web/app.py`
- Create: `scalper/web/__init__.py`
- Create: `scalper/web/templates/index.html`
- Create: `scalper/web/static/style.css`
- Create: `scalper/web/static/app.js`

**Step 1: Write the Flask app**

```python
# scalper/web/__init__.py
# (empty)

# scalper/web/app.py
"""Flask веб-дашборд скальпер-бота."""
from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO
from flask_cors import CORS

socketio = SocketIO()


def create_app(bot=None, storage=None):
    app = Flask(__name__)
    CORS(app)
    socketio.init_app(app, cors_allowed_origins="*")

    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/api/status')
    def api_status():
        if bot:
            return jsonify(bot.get_status())
        return jsonify({'running': False, 'balance': 0})

    @app.route('/api/trades')
    def api_trades():
        if storage:
            return jsonify(storage.get_trade_history(100))
        return jsonify([])

    @app.route('/api/stats/daily')
    def api_daily_stats():
        if storage:
            return jsonify(storage.get_daily_stats())
        return jsonify({})

    @app.route('/api/stats/all')
    def api_all_stats():
        if storage:
            return jsonify(storage.get_all_stats())
        return jsonify({})

    @app.route('/api/equity')
    def api_equity():
        if storage:
            return jsonify(storage.get_equity_history())
        return jsonify([])

    # Подключение бота к SocketIO для реальтайм обновлений
    if bot:
        def on_bot_event(event, data):
            socketio.emit(event, data)
        bot.on_update(on_bot_event)

    return app
```

**Step 2: Write HTML шаблон (русский, glassmorphism)**

```html
<!-- scalper/web/templates/index.html -->
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Снайпер — Скальпинг Бот</title>
    <link rel="stylesheet" href="/static/style.css">
    <script src="https://cdn.socket.io/4.7.5/socket.io.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
</head>
<body>
    <div class="container">
        <header>
            <h1>🎯 Снайпер</h1>
            <div id="status" class="status-badge">Загрузка...</div>
        </header>

        <!-- Основные метрики -->
        <div class="metrics-grid">
            <div class="card glass">
                <div class="card-label">Баланс</div>
                <div class="card-value" id="balance">$0.00</div>
            </div>
            <div class="card glass">
                <div class="card-label">PnL сегодня</div>
                <div class="card-value" id="daily-pnl">$0.00</div>
            </div>
            <div class="card glass">
                <div class="card-label">Сделок сегодня</div>
                <div class="card-value" id="daily-trades">0</div>
            </div>
            <div class="card glass">
                <div class="card-label">Винрейт</div>
                <div class="card-value" id="winrate">0%</div>
            </div>
            <div class="card glass">
                <div class="card-label">PnL всего</div>
                <div class="card-value" id="total-pnl">$0.00</div>
            </div>
            <div class="card glass">
                <div class="card-label">Всего сделок</div>
                <div class="card-value" id="total-trades">0</div>
            </div>
        </div>

        <!-- Открытая позиция -->
        <div class="section glass">
            <h2>Текущая позиция</h2>
            <div id="position-container">
                <p class="muted">Нет открытых позиций</p>
            </div>
        </div>

        <!-- Equity кривая -->
        <div class="section glass">
            <h2>Equity кривая</h2>
            <canvas id="equity-chart" height="200"></canvas>
        </div>

        <!-- История сделок -->
        <div class="section glass">
            <h2>История сделок</h2>
            <table id="trades-table">
                <thead>
                    <tr>
                        <th>Время</th>
                        <th>Монета</th>
                        <th>Напр.</th>
                        <th>Вход</th>
                        <th>Выход</th>
                        <th>PnL</th>
                        <th>Причина</th>
                    </tr>
                </thead>
                <tbody id="trades-body"></tbody>
            </table>
        </div>
    </div>

    <script src="/static/app.js"></script>
</body>
</html>
```

**Step 3: Write CSS**

```css
/* scalper/web/static/style.css */
:root {
    --bg: #0a0a1a;
    --glass: rgba(255,255,255,0.05);
    --glass-border: rgba(255,255,255,0.1);
    --text: #e0e0f0;
    --text-muted: #888;
    --green: #00e676;
    --red: #ff5252;
    --blue: #448aff;
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
    background: var(--bg);
    color: var(--text);
    font-family: 'Segoe UI', system-ui, sans-serif;
    min-height: 100vh;
}

.container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 20px;
}

header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 24px;
}

header h1 { font-size: 1.8em; }

.status-badge {
    padding: 6px 16px;
    border-radius: 20px;
    font-size: 0.9em;
    font-weight: 600;
}

.status-running { background: rgba(0,230,118,0.2); color: var(--green); }
.status-paused { background: rgba(255,82,82,0.2); color: var(--red); }
.status-stopped { background: rgba(136,136,136,0.2); color: var(--text-muted); }

.glass {
    background: var(--glass);
    border: 1px solid var(--glass-border);
    border-radius: 16px;
    backdrop-filter: blur(10px);
}

.metrics-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 12px;
    margin-bottom: 24px;
}

.card {
    padding: 16px;
    text-align: center;
}

.card-label {
    font-size: 0.8em;
    color: var(--text-muted);
    margin-bottom: 4px;
}

.card-value {
    font-size: 1.5em;
    font-weight: 700;
}

.section {
    padding: 20px;
    margin-bottom: 20px;
}

.section h2 {
    font-size: 1.1em;
    margin-bottom: 16px;
    color: var(--text-muted);
}

table {
    width: 100%;
    border-collapse: collapse;
}

th, td {
    padding: 10px 12px;
    text-align: left;
    border-bottom: 1px solid var(--glass-border);
}

th {
    color: var(--text-muted);
    font-size: 0.85em;
    font-weight: 600;
}

.pnl-positive { color: var(--green); }
.pnl-negative { color: var(--red); }
.muted { color: var(--text-muted); }

.position-card {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
    gap: 12px;
}

.position-card .label { font-size: 0.8em; color: var(--text-muted); }
.position-card .value { font-size: 1.1em; font-weight: 600; }

.direction-long { color: var(--green); }
.direction-short { color: var(--red); }
```

**Step 4: Write JavaScript**

```javascript
// scalper/web/static/app.js
const socket = io();
let equityChart = null;

// Обновление данных каждые 5 секунд
async function updateDashboard() {
    try {
        const [statusRes, tradesRes, equityRes] = await Promise.all([
            fetch('/api/status'),
            fetch('/api/trades'),
            fetch('/api/equity'),
        ]);
        const status = await statusRes.json();
        const trades = await tradesRes.json();
        const equity = await equityRes.json();

        updateStatus(status);
        updateMetrics(status);
        updatePosition(status);
        updateTrades(trades);
        updateEquityChart(equity);
    } catch (e) {
        console.error('Ошибка обновления:', e);
    }
}

function updateStatus(s) {
    const el = document.getElementById('status');
    if (!s.running) {
        el.textContent = 'Остановлен';
        el.className = 'status-badge status-stopped';
    } else if (!s.can_trade) {
        el.textContent = 'Пауза';
        el.className = 'status-badge status-paused';
    } else {
        el.textContent = 'Работает';
        el.className = 'status-badge status-running';
    }
}

function updateMetrics(s) {
    document.getElementById('balance').textContent = `$${s.balance.toFixed(2)}`;
    const d = s.daily_stats || {};
    const a = s.all_stats || {};
    const dailyPnl = d.total_pnl || 0;
    const dailyEl = document.getElementById('daily-pnl');
    dailyEl.textContent = `$${dailyPnl.toFixed(2)}`;
    dailyEl.className = `card-value ${dailyPnl >= 0 ? 'pnl-positive' : 'pnl-negative'}`;
    document.getElementById('daily-trades').textContent = d.total_trades || 0;
    document.getElementById('winrate').textContent = `${(d.win_rate || 0).toFixed(0)}%`;
    const totalPnl = a.total_pnl || 0;
    const totalEl = document.getElementById('total-pnl');
    totalEl.textContent = `$${totalPnl.toFixed(2)}`;
    totalEl.className = `card-value ${totalPnl >= 0 ? 'pnl-positive' : 'pnl-negative'}`;
    document.getElementById('total-trades').textContent = a.total_trades || 0;
}

function updatePosition(s) {
    const container = document.getElementById('position-container');
    if (!s.positions || s.positions.length === 0) {
        container.innerHTML = '<p class="muted">Нет открытых позиций</p>';
        return;
    }
    const p = s.positions[0];
    container.innerHTML = `
        <div class="position-card">
            <div><div class="label">Монета</div><div class="value">${p.symbol.split('/')[0]}</div></div>
            <div><div class="label">Направление</div><div class="value direction-${p.direction}">${p.direction.toUpperCase()}</div></div>
            <div><div class="label">Вход</div><div class="value">$${p.entry_price.toFixed(2)}</div></div>
            <div><div class="label">SL (trailing)</div><div class="value">${p.current_sl.toFixed(2)}</div></div>
            <div><div class="label">TP</div><div class="value">${p.tp_price.toFixed(2)}</div></div>
            <div><div class="label">Плечо</div><div class="value">x${p.leverage}</div></div>
        </div>
    `;
}

function updateTrades(trades) {
    const tbody = document.getElementById('trades-body');
    tbody.innerHTML = trades.map(t => {
        const pnlClass = (t.pnl || 0) >= 0 ? 'pnl-positive' : 'pnl-negative';
        const time = t.closed_at ? new Date(t.closed_at).toLocaleString('ru-RU') : '-';
        const reasons = {
            'tp_hit': 'Take Profit',
            'sl_hit': 'Stop Loss',
            'signal': 'Сигнал',
        };
        return `<tr>
            <td>${time}</td>
            <td>${t.symbol.split('/')[0]}</td>
            <td class="direction-${t.direction}">${t.direction.toUpperCase()}</td>
            <td>$${(t.entry_price || 0).toFixed(2)}</td>
            <td>$${(t.exit_price || 0).toFixed(2)}</td>
            <td class="${pnlClass}">$${(t.pnl || 0).toFixed(2)} (${(t.pnl_pct || 0).toFixed(1)}%)</td>
            <td>${reasons[t.close_reason] || t.close_reason}</td>
        </tr>`;
    }).join('');
}

function updateEquityChart(equity) {
    const ctx = document.getElementById('equity-chart');
    const labels = equity.map(e => new Date(e.timestamp).toLocaleString('ru-RU', {
        hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit'
    }));
    const data = equity.map(e => e.balance);

    if (equityChart) {
        equityChart.data.labels = labels;
        equityChart.data.datasets[0].data = data;
        equityChart.update('none');
        return;
    }

    equityChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [{
                label: 'Баланс ($)',
                data,
                borderColor: '#448aff',
                backgroundColor: 'rgba(68,138,255,0.1)',
                fill: true,
                tension: 0.3,
                pointRadius: 0,
            }],
        },
        options: {
            responsive: true,
            plugins: { legend: { display: false } },
            scales: {
                x: { ticks: { color: '#888', maxTicksLimit: 10 }, grid: { color: 'rgba(255,255,255,0.05)' } },
                y: { ticks: { color: '#888' }, grid: { color: 'rgba(255,255,255,0.05)' } },
            },
        },
    });
}

// Реальтайм через SocketIO
socket.on('trade_open', () => updateDashboard());
socket.on('trade_close', () => updateDashboard());

// Первоначальная загрузка + интервал
updateDashboard();
setInterval(updateDashboard, 5000);
```

**Step 5: Commit**

```bash
git add scalper/web/
git commit -m "feat: add Russian web dashboard with glassmorphism UI"
```

---

## Task 11: Точка входа и запуск

**Files:**
- Create: `run.py`
- Create: `requirements.txt` (новый)
- Update: `.env.example`

**Step 1: Write entry point**

```python
# run.py
"""Точка входа: запуск бота + веб-дашборда."""
import asyncio
import logging
import os
from threading import Thread
from scalper.config import Config
from scalper.bot import ScalperBot
from scalper.web.app import create_app, socketio

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('scalper.log', encoding='utf-8'),
    ]
)
log = logging.getLogger(__name__)


def run_bot(bot: ScalperBot):
    """Запуск asyncio бота в отдельном потоке."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(bot.run())
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()


def main():
    config = Config.from_env()

    # Создать директорию для БД
    os.makedirs('data', exist_ok=True)

    bot = ScalperBot(config)
    app = create_app(bot, bot._storage)

    log.info(f"=== Снайпер Скальпер ===")
    log.info(f"Баланс: ${config.balance} | Плечо: x{config.leverage}")
    log.info(f"Топ монет: {config.top_n_coins} | ТФ: {config.scalp_timeframe}")
    log.info(f"Дашборд: http://localhost:{config.web_port}")

    # Бот в отдельном потоке
    bot_thread = Thread(target=run_bot, args=(bot,), daemon=True)
    bot_thread.start()

    # Веб-сервер в основном потоке
    socketio.run(app, host='0.0.0.0', port=config.web_port,
                 debug=False, allow_unsafe_werkzeug=True)


if __name__ == '__main__':
    main()
```

**Step 2: Write requirements.txt**

```
ccxt>=4.0
numpy
flask>=3.0
flask-socketio>=5.3
flask-cors>=4.0
python-socketio>=5.11
eventlet>=0.33
python-dotenv
pytest
pytest-asyncio
```

**Step 3: Update .env.example**

```ini
# Bybit API (демо)
BYBIT_API_KEY=your_demo_key
BYBIT_API_SECRET=your_demo_secret
BYBIT_DEMO=true

# Баланс и торговля
BALANCE=200
LEVERAGE=20
MAX_DAILY_LOSS=30
SCAN_INTERVAL=30
SCALP_TIMEFRAME=3m
TOP_N_COINS=50

# Веб-дашборд
WEB_PORT=5001
```

**Step 4: Test full startup**

```bash
cd D:\python\Crypto_parser
pip install -r requirements.txt
python run.py
```
Expected: Бот запускается, дашборд доступен на http://localhost:5001

**Step 5: Commit**

```bash
git add run.py requirements.txt .env.example
git commit -m "feat: add entry point and requirements"
```

---

## Task 12: Интеграционный тест

**Files:**
- Create: `tests/test_integration.py`

**Step 1: Write integration test**

```python
# tests/test_integration.py
"""Интеграционный тест: весь пайплайн от сканирования до закрытия сделки."""
import pytest
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch
from scalper.config import Config
from scalper.bot import ScalperBot
from scalper.signals import Signal


@pytest.fixture
def config():
    return Config(
        balance=200, leverage=20, bybit_api_key='test',
        bybit_api_secret='test', bybit_demo=True,
        max_consecutive_losses=10, max_daily_loss=30,
    )


@pytest.mark.asyncio
async def test_full_cycle(config, tmp_path):
    """Полный цикл: открытие → рост цены → trailing → закрытие по TP."""
    from scalper.storage import Storage

    db_path = str(tmp_path / 'test.db')
    bot = ScalperBot(config)
    bot._storage = Storage(db_path)

    # Мокаем exchange
    bot._exchange = MagicMock()
    bot._exchange.start = AsyncMock()
    bot._exchange.close = AsyncMock()

    # Tick 1: сканер находит сигнал → открытие
    signal = Signal('long', 3, 50000.0, 49250.0, 51500.0,
                    ['ema_cross', 'rsi_oversold', 'volume_spike'])
    bot._scanner = MagicMock()
    bot._scanner.scan = AsyncMock(return_value=[
        {'symbol': 'BTC/USDT:USDT', 'signal': signal, 'price': 50000.0}
    ])

    await bot.start()
    await bot.tick()

    assert len(bot._open_positions) == 1
    assert len(bot._storage.get_open_trades()) == 1

    # Tick 2: цена растёт → trailing подтягивается
    bot._exchange.get_price = AsyncMock(return_value=51000.0)
    await bot.tick()
    assert len(bot._open_positions) == 1  # ещё открыта

    # Tick 3: цена достигает TP → закрытие
    bot._exchange.get_price = AsyncMock(return_value=51500.0)
    await bot.tick()
    assert len(bot._open_positions) == 0

    # Проверяем результат
    stats = bot._storage.get_daily_stats()
    assert stats['total_trades'] == 1
    assert stats['wins'] == 1
    assert stats['total_pnl'] > 0
    assert config.balance > 200  # баланс вырос

    bot._storage.close()
```

**Step 2: Run test**

```bash
python -m pytest tests/test_integration.py -v
```
Expected: PASS

**Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "feat: add integration test for full trade cycle"
```

---

## Task 13: Обновить CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Update CLAUDE.md with new project info**

Replace entire content of `CLAUDE.md` with updated documentation reflecting the new Scalper Sniper architecture, removing all references to old multi-strategy platform.

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for Scalper Sniper project"
```

---

## Порядок выполнения

| # | Task | Зависит от |
|---|------|-----------|
| 0 | Очистка проекта | — |
| 1 | Config | — |
| 2 | Indicators | — |
| 3 | Exchange | 1 |
| 4 | Signals | 1, 2 |
| 5 | Filters | 2 |
| 6 | Risk Manager | 1 |
| 7 | Storage | — |
| 8 | Scanner | 3, 4, 5 |
| 9 | Bot | 6, 7, 8 |
| 10 | Web Dashboard | 9 |
| 11 | Entry Point | 9, 10 |
| 12 | Integration Test | all |
| 13 | CLAUDE.md | all |

Tasks 1, 2, 7 можно выполнять **параллельно** (нет зависимостей).
