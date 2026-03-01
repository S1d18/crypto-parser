"""
Supertrend торговая стратегия.

Логика:
- Long: открывается когда цена пересекает Supertrend снизу вверх
- Short: открывается когда цена пересекает Supertrend сверху вниз
- Закрытие: при обратном пересечении
"""
import numpy as np
from typing import Optional, List

from strategies.base_strategy import Strategy
from core.supertrend import calculate_supertrend


class SupertrendStrategy(Strategy):
    """Торговая стратегия на основе индикатора Supertrend."""

    def calculate_signal(self, ohlcv: List[List]) -> Optional[str]:
        """
        Рассчитать сигнал на основе Supertrend.

        Args:
            ohlcv: Список свечей [[timestamp, open, high, low, close, volume], ...]

        Returns:
            'buy' - открыть Long
            'sell' - открыть Short
            'close' - закрыть позицию
            None - нет сигнала
        """
        if len(ohlcv) < 50:
            return None

        # Параметры из конфига (st_period/st_multiplier из generate_strategies)
        period = self.params.get('st_period', self.params.get('period', 10))
        multiplier = self.params.get('st_multiplier', self.params.get('multiplier', 3.0))

        # Рассчитать Supertrend
        result = calculate_supertrend(
            ohlcv=ohlcv,
            period=period,
            multiplier=multiplier
        )

        # Извлечь направления
        directions = result['directions']

        # Текущее и предыдущее направление
        current_dir = directions[-1]
        prev_dir = directions[-2] if len(directions) > 1 else current_dir

        close = np.array([candle[4] for candle in ohlcv])

        current_price = close[-1]

        # Если есть открытая позиция
        if self.position is not None:
            side = self.position['side']

            # Long позиция
            if side == 'buy':
                # Закрыть если тренд сменился на DOWN
                if current_dir == -1 and prev_dir == 1:
                    return 'close'

            # Short позиция
            elif side == 'sell':
                # Закрыть если тренд сменился на UP
                if current_dir == 1 and prev_dir == -1:
                    return 'close'

            return None

        # Нет позиции - проверяем сигналы на открытие
        # Long сигнал: тренд сменился на UP
        if current_dir == 1 and prev_dir == -1:
            if self.can_open_long():
                return 'buy'

        # Short сигнал: тренд сменился на DOWN
        if current_dir == -1 and prev_dir == 1:
            if self.can_open_short():
                return 'sell'

        return None
