"""
RSI (Relative Strength Index) торговая стратегия.

Логика:
- Long: открывается когда RSI < oversold (перепродано)
- Short: открывается когда RSI > overbought (перекуплено)
- Закрытие: когда RSI возвращается к средним значениям
"""
import numpy as np
from typing import Optional, List

from strategies.base_strategy import Strategy


def calculate_rsi(prices: np.ndarray, period: int = 14) -> np.ndarray:
    """
    Рассчитать RSI (Relative Strength Index).

    Args:
        prices: Массив цен закрытия
        period: Период RSI

    Returns:
        Массив значений RSI
    """
    if len(prices) < period + 1:
        return np.array([])

    # Рассчитать изменения цены
    deltas = np.diff(prices)

    # Разделить на прибыли и убытки
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)

    # Рассчитать среднюю прибыль и средний убыток
    avg_gain = np.zeros(len(gains))
    avg_loss = np.zeros(len(losses))

    # Первое значение - простое среднее
    avg_gain[period - 1] = np.mean(gains[:period])
    avg_loss[period - 1] = np.mean(losses[:period])

    # Остальные значения - экспоненциальное скользящее среднее
    for i in range(period, len(gains)):
        avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gains[i]) / period
        avg_loss[i] = (avg_loss[i - 1] * (period - 1) + losses[i]) / period

    # Рассчитать RS и RSI
    rs = np.divide(avg_gain, avg_loss, where=avg_loss != 0, out=np.zeros_like(avg_gain))
    rsi = 100 - (100 / (1 + rs))

    # Добавить NaN в начало для выравнивания с исходным массивом
    rsi = np.concatenate([np.full(period, np.nan), rsi[period - 1:]])

    return rsi


class RSIStrategy(Strategy):
    """Торговая стратегия на основе индикатора RSI."""

    def calculate_signal(self, ohlcv: List[List]) -> Optional[str]:
        """
        Рассчитать сигнал на основе RSI.

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

        # Извлечь цены закрытия
        close = np.array([candle[4] for candle in ohlcv])

        # Параметры из конфига
        period = self.params.get('rsi_period', 14)
        oversold = self.params.get('rsi_oversold', 30)
        overbought = self.params.get('rsi_overbought', 70)

        # Рассчитать RSI
        rsi = calculate_rsi(close, period=period)

        if len(rsi) < 2:
            return None

        # Текущее и предыдущее значение RSI
        current_rsi = rsi[-1]
        prev_rsi = rsi[-2]

        # Если есть открытая позиция
        if self.position is not None:
            side = self.position['side']

            # Long позиция
            if side == 'buy':
                # Закрыть когда RSI поднялся выше 50 (середина)
                if current_rsi > 50:
                    return 'close'

            # Short позиция
            elif side == 'sell':
                # Закрыть когда RSI опустился ниже 50
                if current_rsi < 50:
                    return 'close'

            return None

        # Нет позиции - проверяем сигналы на открытие
        # Long сигнал: RSI пересекает oversold снизу вверх
        if prev_rsi < oversold and current_rsi >= oversold:
            if self.can_open_long():
                self.logger.info(f"RSI Long signal: {current_rsi:.1f} (oversold: {oversold})")
                return 'buy'

        # Short сигнал: RSI пересекает overbought сверху вниз
        if prev_rsi > overbought and current_rsi <= overbought:
            if self.can_open_short():
                self.logger.info(f"RSI Short signal: {current_rsi:.1f} (overbought: {overbought})")
                return 'sell'

        return None
