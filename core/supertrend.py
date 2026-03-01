import numpy as np


def calculate_supertrend(
    ohlcv: list[list],
    period: int = 10,
    multiplier: float = 3.0,
) -> dict:
    """
    Рассчитывает Supertrend по OHLCV данным от ccxt.

    Параметры:
        ohlcv: список свечей [[timestamp, open, high, low, close, volume], ...]
        period: период ATR
        multiplier: множитель ATR

    Возвращает:
        {
            "direction": 1 (Long/UP) или -1 (Short/DOWN),
            "supertrend": значение линии Supertrend,
            "upper_band": верхняя полоса,
            "lower_band": нижняя полоса,
            "directions": массив направлений для всех свечей,
            "changed": True если направление изменилось на последней свече,
        }
    """
    if len(ohlcv) < period + 1:
        raise ValueError(f"Недостаточно данных: {len(ohlcv)} свечей, нужно минимум {period + 1}")

    high = np.array([c[2] for c in ohlcv], dtype=float)
    low = np.array([c[3] for c in ohlcv], dtype=float)
    close = np.array([c[4] for c in ohlcv], dtype=float)

    # True Range
    tr = np.zeros(len(ohlcv))
    tr[0] = high[0] - low[0]
    for i in range(1, len(ohlcv)):
        tr[i] = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1]),
        )

    # ATR (Simple Moving Average of TR)
    atr = np.zeros(len(ohlcv))
    atr[:period] = np.nan
    atr[period] = np.mean(tr[1 : period + 1])
    for i in range(period + 1, len(ohlcv)):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period

    # HL2 (средняя цена)
    hl2 = (high + low) / 2

    # Базовые полосы
    upper_basic = hl2 + multiplier * atr
    lower_basic = hl2 - multiplier * atr

    # Финальные полосы (с учётом предыдущих значений)
    upper_band = np.zeros(len(ohlcv))
    lower_band = np.zeros(len(ohlcv))
    direction = np.zeros(len(ohlcv), dtype=int)

    upper_band[period] = upper_basic[period]
    lower_band[period] = lower_basic[period]
    direction[period] = 1  # начинаем с Long

    for i in range(period + 1, len(ohlcv)):
        # Upper band: берём минимум из текущей и предыдущей (если close[i-1] <= prev upper)
        if upper_basic[i] < upper_band[i - 1] or close[i - 1] > upper_band[i - 1]:
            upper_band[i] = upper_basic[i]
        else:
            upper_band[i] = upper_band[i - 1]

        # Lower band: берём максимум из текущей и предыдущей (если close[i-1] >= prev lower)
        if lower_basic[i] > lower_band[i - 1] or close[i - 1] < lower_band[i - 1]:
            lower_band[i] = lower_basic[i]
        else:
            lower_band[i] = lower_band[i - 1]

        # Направление
        if direction[i - 1] == 1:  # был Long
            if close[i] < lower_band[i]:
                direction[i] = -1  # переключаемся на Short
            else:
                direction[i] = 1
        else:  # был Short
            if close[i] > upper_band[i]:
                direction[i] = 1  # переключаемся на Long
            else:
                direction[i] = -1

    last = len(ohlcv) - 1
    prev = last - 1

    return {
        "direction": int(direction[last]),
        "supertrend": float(lower_band[last] if direction[last] == 1 else upper_band[last]),
        "upper_band": float(upper_band[last]),
        "lower_band": float(lower_band[last]),
        "directions": direction[period:].tolist(),
        "changed": int(direction[last]) != int(direction[prev]),
    }
