"""
Торговые стратегии.

Содержит:
- base.py: базовые классы Strategy и Signal
- live/: реальные торговые стратегии
- paper/: бумажные торговые стратегии
- arbitrage/: арбитражные стратегии
"""

from .base import Strategy, Signal

__all__ = [
    'Strategy',
    'Signal',
]
