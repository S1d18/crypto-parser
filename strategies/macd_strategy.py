"""
MACD (Moving Average Convergence Divergence) торговая стратегия.

Логика:
- Long: открывается когда MACD пересекает сигнальную линию снизу вверх
- Short: открывается когда MACD пересекает сигнальную линию сверху вниз
- Закрытие: при обратном пересечении
"""
import numpy as np
from typing import Optional, List, Tuple

from strategies.base_strategy import Strategy


def calculate_ema(prices: np.ndarray, period: int) -> np.ndarray:
    """
    Рассчитать EMA (Exponential Moving Average).

    Args:
        prices: Массив цен
        period: Период EMA

    Returns:
        Массив значений EMA
    """
    if len(prices) < period:
        return np.array([])

    ema = np.zeros(len(prices))
    ema[period - 1] = np.mean(prices[:period])

    multiplier = 2 / (period + 1)

    for i in range(period, len(prices)):
        ema[i] = (prices[i] - ema[i - 1]) * multiplier + ema[i - 1]

    # Заполнить начальные значения NaN
    ema[:period - 1] = np.nan

    return ema


def calculate_macd(prices: np.ndarray, fast: int = 12, slow: int = 26,
                   signal: int = 9) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Рассчитать MACD (Moving Average Convergence Divergence).

    Args:
        prices: Массив цен закрытия
        fast: Период быстрой EMA
        slow: Период медленной EMA
        signal: Период сигнальной линии

    Returns:
        Tuple (macd_line, signal_line, histogram)
    """
    if len(prices) < slow + signal:
        return np.array([]), np.array([]), np.array([])

    # Рассчитать быструю и медленную EMA
    ema_fast = calculate_ema(prices, fast)
    ema_slow = calculate_ema(prices, slow)

    # MACD линия = EMA(fast) - EMA(slow)
    macd_line = ema_fast - ema_slow

    # Сигнальная линия = EMA(MACD, signal)
    # Убрать NaN значения для расчёта сигнальной линии
    valid_idx = ~np.isnan(macd_line)
    signal_line = np.full(len(prices), np.nan)

    if np.sum(valid_idx) >= signal:
        macd_valid = macd_line[valid_idx]
        signal_ema = calculate_ema(macd_valid, signal)

        # Вернуть сигнальную линию на правильные позиции
        valid_positions = np.where(valid_idx)[0]
        signal_line[valid_positions] = signal_ema

    # Гистограмма = MACD - Signal
    histogram = macd_line - signal_line

    return macd_line, signal_line, histogram


class MACDStrategy(Strategy):
    """Торговая стратегия на основе индикатора MACD."""

    def calculate_signal(self, ohlcv: List[List]) -> Optional[str]:
        """
        Рассчитать сигнал на основе MACD.

        Args:
            ohlcv: Список свечей [[timestamp, open, high, low, close, volume], ...]

        Returns:
            'buy' - открыть Long
            'sell' - открыть Short
            'close' - закрыть позицию
            None - нет сигнала
        """
        if len(ohlcv) < 100:
            return None

        # Извлечь цены закрытия
        close = np.array([candle[4] for candle in ohlcv])

        # Параметры из конфига
        fast = self.params.get('macd_fast', 12)
        slow = self.params.get('macd_slow', 26)
        signal_period = self.params.get('macd_signal', 9)

        # Рассчитать MACD
        macd_line, signal_line, histogram = calculate_macd(
            prices=close,
            fast=fast,
            slow=slow,
            signal=signal_period
        )

        if len(macd_line) < 2 or np.isnan(macd_line[-1]) or np.isnan(signal_line[-1]):
            return None

        # Текущие и предыдущие значения
        current_macd = macd_line[-1]
        prev_macd = macd_line[-2]
        current_signal = signal_line[-1]
        prev_signal = signal_line[-2]

        # Если есть открытая позиция
        if self.position is not None:
            side = self.position['side']

            # Long позиция
            if side == 'buy':
                # Закрыть когда MACD пересекает сигнальную линию сверху вниз
                if prev_macd > prev_signal and current_macd <= current_signal:
                    return 'close'

            # Short позиция
            elif side == 'sell':
                # Закрыть когда MACD пересекает сигнальную линию снизу вверх
                if prev_macd < prev_signal and current_macd >= current_signal:
                    return 'close'

            return None

        # Нет позиции - проверяем сигналы на открытие
        # Long сигнал: MACD пересекает сигнальную линию снизу вверх
        if prev_macd < prev_signal and current_macd >= current_signal:
            if self.can_open_long():
                self.logger.info(f"MACD Long signal: {current_macd:.4f} > {current_signal:.4f}")
                return 'buy'

        # Short сигнал: MACD пересекает сигнальную линию сверху вниз
        if prev_macd > prev_signal and current_macd <= current_signal:
            if self.can_open_short():
                self.logger.info(f"MACD Short signal: {current_macd:.4f} < {current_signal:.4f}")
                return 'sell'

        return None
