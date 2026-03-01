"""
Core modules для торговой системы.

Содержит базовые компоненты:
- Config: конфигурация из .env
- calc_supertrend: расчёт индикатора Supertrend
- TradeStorage: SQLite хранилище сделок
- TelegramNotifier: уведомления в Telegram
"""

from .config import Config
from .supertrend import calculate_supertrend
from .storage import TradeStorage
from .notifier import TelegramNotifier

__all__ = [
    'Config',
    'calculate_supertrend',
    'TradeStorage',
    'TelegramNotifier',
]
