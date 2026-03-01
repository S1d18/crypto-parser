"""
Глобальный сервис для получения цен криптовалют с множества бирж.

Функции:
- Ротация через 10 различных бирж (одна в секунду)
- Кэширование последних цен в памяти
- Автоматический фоллбэк при недоступности биржи
- Thread-safe доступ к ценам
"""
import asyncio
import logging
import time
from threading import Thread, Lock
from typing import Dict, Optional, List
from datetime import datetime
import ccxt

logger = logging.getLogger(__name__)


class PriceService:
    """Сервис для получения цен с множества бирж."""

    # Список бирж для ротации (в порядке приоритета)
    EXCHANGES = [
        'bybit',
        'binance',
        'okx',
        'kucoin',
        'gateio',
        'huobi',  # HTX
        'bitget',
        'mexc',
        'kraken',
        'coinbase'
    ]

    # Символы для отслеживания (Bybit format)
    SYMBOLS = [
        'BTC/USDT',
        'ETH/USDT',
        'SOL/USDT',
        'LTC/USDT',
        'TON/USDT'
    ]

    def __init__(self):
        self.prices: Dict[str, Dict] = {}  # {symbol: {price, exchange, timestamp}}
        self.lock = Lock()
        self.current_exchange_idx = 0
        self.running = False
        self.thread: Optional[Thread] = None
        self.exchanges_status: Dict[str, Dict] = {}  # Статус каждой биржи

        # Инициализация ccxt exchanges (без API ключей - публичные данные)
        self.exchange_instances = {}
        for exchange_id in self.EXCHANGES:
            try:
                exchange_class = getattr(ccxt, exchange_id)
                self.exchange_instances[exchange_id] = exchange_class({
                    'enableRateLimit': True,
                    'timeout': 5000  # 5 секунд таймаут
                })
                self.exchanges_status[exchange_id] = {
                    'available': True,
                    'last_success': None,
                    'last_error': None,
                    'error_count': 0
                }
            except Exception as e:
                logger.warning(f"Could not initialize {exchange_id}: {e}")
                self.exchanges_status[exchange_id] = {
                    'available': False,
                    'last_success': None,
                    'last_error': str(e),
                    'error_count': 999
                }

    def start(self):
        """Запустить фоновый поток для обновления цен."""
        if self.running:
            logger.warning("Price service already running")
            return

        self.running = True
        self.thread = Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        logger.info("✓ Price service started")

    def stop(self):
        """Остановить фоновый поток."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        logger.info("✓ Price service stopped")

    def _run_loop(self):
        """Основной цикл обновления цен (ротация через биржи)."""
        while self.running:
            # Выбрать следующую доступную биржу
            exchange_id = self._get_next_exchange()

            if not exchange_id:
                logger.warning("No available exchanges, waiting 5s...")
                time.sleep(5)
                continue

            # Получить цены с этой биржи
            try:
                self._fetch_prices_from_exchange(exchange_id)

                # Обновить статус
                with self.lock:
                    self.exchanges_status[exchange_id]['available'] = True
                    self.exchanges_status[exchange_id]['last_success'] = datetime.now().isoformat()
                    self.exchanges_status[exchange_id]['error_count'] = 0

                logger.debug(f"✓ Fetched prices from {exchange_id}")

            except Exception as e:
                logger.warning(f"Error fetching from {exchange_id}: {e}")

                # Обновить статус
                with self.lock:
                    self.exchanges_status[exchange_id]['last_error'] = str(e)
                    self.exchanges_status[exchange_id]['error_count'] += 1

                    # Отметить как недоступную после 3 ошибок подряд
                    if self.exchanges_status[exchange_id]['error_count'] >= 3:
                        self.exchanges_status[exchange_id]['available'] = False
                        logger.error(f"Marking {exchange_id} as unavailable after 3 errors")

            # Подождать 1 секунду до следующего запроса
            time.sleep(1)

    def _get_next_exchange(self) -> Optional[str]:
        """Получить следующую доступную биржу для ротации."""
        # Попробовать все биржи по кругу
        for _ in range(len(self.EXCHANGES)):
            exchange_id = self.EXCHANGES[self.current_exchange_idx]
            self.current_exchange_idx = (self.current_exchange_idx + 1) % len(self.EXCHANGES)

            # Проверить доступность
            with self.lock:
                if self.exchanges_status.get(exchange_id, {}).get('available', False):
                    return exchange_id

        return None  # Нет доступных бирж

    def _fetch_prices_from_exchange(self, exchange_id: str):
        """Получить цены с конкретной биржи."""
        exchange = self.exchange_instances[exchange_id]

        # Получить все тикеры одним запросом (быстрее)
        tickers = exchange.fetch_tickers(self.SYMBOLS)

        # Обновить кэш цен
        timestamp = datetime.now().isoformat()

        with self.lock:
            for symbol in self.SYMBOLS:
                if symbol in tickers:
                    ticker = tickers[symbol]
                    self.prices[symbol] = {
                        'price': ticker['last'],
                        'exchange': exchange_id,
                        'timestamp': timestamp,
                        'bid': ticker.get('bid'),
                        'ask': ticker.get('ask'),
                        'volume': ticker.get('baseVolume')
                    }

    def get_price(self, symbol: str) -> Optional[float]:
        """Получить последнюю известную цену символа."""
        with self.lock:
            if symbol in self.prices:
                return self.prices[symbol]['price']
        return None

    def get_all_prices(self) -> Dict[str, Dict]:
        """Получить все последние цены."""
        with self.lock:
            return self.prices.copy()

    def get_exchanges_status(self) -> Dict[str, Dict]:
        """Получить статус всех бирж."""
        with self.lock:
            return self.exchanges_status.copy()


# Глобальный singleton instance
_price_service_instance: Optional[PriceService] = None


def get_price_service() -> PriceService:
    """Получить глобальный экземпляр PriceService."""
    global _price_service_instance
    if _price_service_instance is None:
        _price_service_instance = PriceService()
    return _price_service_instance
