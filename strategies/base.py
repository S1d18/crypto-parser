"""
Базовые классы для всех торговых стратегий.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Signal:
    """Торговый сигнал."""
    timestamp: datetime
    action: str  # 'buy', 'sell', 'close'
    price: float
    confidence: float  # 0-100
    reason: str


class Strategy(ABC):
    """
    Базовый класс для всех торговых стратегий.

    Каждая стратегия должна реализовать:
    - name: уникальное имя
    - description: описание логики
    - calculate_signal: расчёт сигнала на основе OHLCV данных
    - should_close: проверка условий закрытия позиции
    """

    def __init__(self, symbol: str, timeframe: str, config: dict):
        self.symbol = symbol
        self.timeframe = timeframe
        self.config = config
        self.position = None  # None или dict с данными позиции

    @property
    @abstractmethod
    def name(self) -> str:
        """Уникальное имя стратегии."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Описание стратегии."""
        pass

    @abstractmethod
    async def calculate_signal(self, ohlcv: list) -> Optional[Signal]:
        """
        Рассчитать торговый сигнал на основе OHLCV данных.

        Args:
            ohlcv: список свечей [[timestamp, open, high, low, close, volume], ...]

        Returns:
            Signal или None если нет сигнала
        """
        pass

    @abstractmethod
    def should_close(self, current_price: float) -> tuple[bool, str]:
        """
        Проверить нужно ли закрыть текущую позицию.

        Args:
            current_price: текущая цена

        Returns:
            (should_close, reason) - нужно ли закрыть и причина
        """
        pass

    def open_position(self, side: str, price: float, qty: float):
        """Открыть позицию."""
        self.position = {
            'side': side,
            'price': price,
            'qty': qty,
            'timestamp': datetime.now()
        }

    def close_position(self):
        """Закрыть позицию."""
        self.position = None

    def has_position(self) -> bool:
        """Проверить есть ли открытая позиция."""
        return self.position is not None
