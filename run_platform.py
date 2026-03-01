"""
Trading Platform - Единая точка входа

Запускает:
- Flask веб-сервер (порт 5001)
- StrategyManager с 100+ стратегиями
- WebSocket для real-time updates
- Все в одном месте!
"""

import sys
import logging
import asyncio
from pathlib import Path
import threading
import time
import os

# Добавить корень проекта в PYTHONPATH
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

import ccxt
from dotenv import load_dotenv

from api.app import app, socketio
from strategies.strategy_manager import StrategyManager
from core.database import Database

# Загрузить .env
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(PROJECT_ROOT / "data" / "logs" / "platform.log", encoding="utf-8"),
    ]
)

logger = logging.getLogger("platform")


class TradingPlatform:
    """Главная платформа - управляет всеми компонентами."""

    def __init__(self):
        self.db = Database()

        # Создать ccxt exchange для Bybit DEMO
        self.exchange = self._create_exchange()

        # Создать StrategyManager с exchange
        self.strategy_manager = StrategyManager(exchange=self.exchange, db=self.db)
        self.running = False

    def _create_exchange(self):
        """Создать ccxt exchange instance для Bybit (публичный доступ для свечей)."""
        # Для paper trading не нужны API ключи - используем публичный доступ
        exchange = ccxt.bybit({
            'enableRateLimit': True,
            'options': {
                'defaultType': 'linear',  # USDT futures
            }
        })

        logger.info("Bybit exchange initialized (public API для получения свечей)")
        logger.info("Paper trading mode: сделки виртуальные, API ключи не требуются")

        return exchange

    def start(self):
        """Запустить платформу."""
        logger.info("=" * 60)
        logger.info("Trading Platform - Запуск")
        logger.info("=" * 60)

        # БД инициализируется автоматически в Database.__init__
        logger.info("База данных подключена")

        # Загрузка стратегий из конфига
        logger.info("Загрузка стратегий...")
        self._load_strategies()

        # Запуск StrategyManager в отдельном потоке
        logger.info("Запуск StrategyManager...")
        self.running = True
        strategy_thread = threading.Thread(target=self._run_strategies, daemon=True)
        strategy_thread.start()

        # Запуск Flask веб-сервера (blocking)
        logger.info("=" * 60)
        logger.info("Trading Platform запущена!")
        logger.info("=" * 60)
        logger.info("Веб-интерфейс: http://localhost:5001")
        logger.info("Watchlist: http://localhost:5001/")
        logger.info("Screener: http://localhost:5001/screener")
        logger.info("Analytics: http://localhost:5001/analytics")
        logger.info("=" * 60)
        logger.info("Нажмите CTRL+C для остановки")
        logger.info("=" * 60)

        try:
            socketio.run(app, host="0.0.0.0", port=5001, debug=False)
        except KeyboardInterrupt:
            logger.info("\nОстановка платформы...")
            self.stop()

    def _load_strategies(self):
        """Загрузить стратегии из БД."""
        strategies = self.db.get_all_strategies()

        if not strategies:
            logger.warning("Нет стратегий в БД. Создайте стратегии через веб-интерфейс или скрипт.")
            logger.info("Подсказка: запустите 'python scripts/generate_strategies.py'")
        else:
            logger.info(f"Найдено стратегий: {len(strategies)}")

            # Группировка по категориям
            by_category = {}
            for s in strategies:
                cat = s.get('category', 'unknown')
                by_category[cat] = by_category.get(cat, 0) + 1

            for cat, count in by_category.items():
                logger.info(f"  - {cat}: {count} стратегий")

    def _run_strategies(self):
        """Запустить все активные стратегии (в отдельном потоке)."""
        logger.info("StrategyManager: поток запущен")

        # Создать новый event loop для этого потока
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Запустить StrategyManager
        self.strategy_manager.start()

        try:
            # Запустить asyncio loop
            loop.run_until_complete(self.strategy_manager.run_loop())
        except Exception as e:
            logger.error(f"Ошибка в StrategyManager: {e}", exc_info=True)
        finally:
            loop.close()

        logger.info("StrategyManager: поток остановлен")

    def stop(self):
        """Остановить платформу."""
        self.running = False
        logger.info("Остановка всех стратегий...")
        self.strategy_manager.stop()
        logger.info("Платформа остановлена")


def main():
    """Главная функция."""
    platform = TradingPlatform()
    platform.start()


if __name__ == "__main__":
    main()
