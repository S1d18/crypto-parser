"""
Paper trading strategies.

Тестирование стратегий без риска (demo data).
"""

from .paper_trader import PaperTrader
from .paper_storage import PaperTradeStorage
from .strategies import PAPER_STRATEGIES

__all__ = [
    'PaperTrader',
    'PaperTradeStorage',
    'PAPER_STRATEGIES',
]
