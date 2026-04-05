"""Breakout — пробой после сжатия (Bollinger Squeeze).

Логика:
- Bollinger Band width ниже своего среднего = сжатие (рынок копит энергию)
- Цена пробивает верхнюю/нижнюю BB с ускорением объёма (> 1.8× среднего)
- ADX растёт (переход от боковика к тренду)
- SL: mid BB (или 1×ATR)
- TP: ширина BB спроецирована от точки пробоя
"""

from __future__ import annotations

import numpy as np

from scalper.indicators import (
    calc_atr, calc_adx, calc_ema, calc_bollinger, calc_bb_width,
    calc_volume_ratio,
)
from scalper.signals import Signal


class BreakoutEngine:
    """Breakout from Bollinger squeeze."""

    bb_period: int = 20
    bb_std: float = 2.0
    atr_period: int = 14
    adx_period: int = 14
    volume_ma_period: int = 20

    # Squeeze: BB width below its own SMA
    squeeze_lookback: int = 50

    # Entry thresholds
    volume_surge: float = 1.8  # volume ratio for breakout confirmation
    adx_rising_bars: int = 3   # ADX must be rising for N bars

    # SL/TP
    atr_sl_mult: float = 1.5
    min_sl_pct: float = 0.8
    tp_ratio: float = 2.0  # TP = BB width or 2×SL, whichever larger

    def evaluate(self, ohlcv: dict[str, np.ndarray]) -> Signal | None:
        close = ohlcv['close']
        high = ohlcv['high']
        low = ohlcv['low']
        volume = ohlcv['volume']

        if len(close) < self.squeeze_lookback + self.bb_period:
            return None

        mid, upper, lower = calc_bollinger(close, self.bb_period, self.bb_std)
        bb_w = calc_bb_width(upper, lower, mid)
        atr = calc_atr(high, low, close, self.atr_period)
        adx = calc_adx(high, low, close, self.adx_period)
        vol_r = calc_volume_ratio(volume, self.volume_ma_period)

        last = len(close) - 1

        atr_val = atr[last]
        if np.isnan(atr_val) or atr_val <= 0:
            return None

        bb_w_val = bb_w[last]
        if np.isnan(bb_w_val):
            return None

        # --- Check squeeze: current BB width below average of recent ---
        lookback_start = max(0, last - self.squeeze_lookback)
        recent_widths = bb_w[lookback_start:last]
        valid_widths = recent_widths[~np.isnan(recent_widths)]
        if len(valid_widths) < 10:
            return None

        avg_width = np.mean(valid_widths)
        # Width was squeezed recently (in last 5 bars)
        was_squeezed = False
        for i in range(max(0, last - 5), last):
            if not np.isnan(bb_w[i]) and bb_w[i] < avg_width * 0.8:
                was_squeezed = True
                break

        if not was_squeezed:
            return None

        # --- ADX rising (trend building) ---
        adx_rising = True
        for i in range(1, min(self.adx_rising_bars + 1, last)):
            a1 = adx[last - i + 1]
            a0 = adx[last - i]
            if np.isnan(a1) or np.isnan(a0) or a1 <= a0:
                adx_rising = False
                break

        # --- Volume surge ---
        vr_val = vol_r[last]
        has_volume = not np.isnan(vr_val) and vr_val > self.volume_surge

        # --- Direction: breakout above upper or below lower ---
        upper_val = upper[last]
        lower_val = lower[last]
        mid_val = mid[last]

        if np.isnan(upper_val) or np.isnan(lower_val):
            return None

        reasons = []
        direction = None

        # Breakout long: close > upper BB
        if close[last] > upper_val and close[last - 1] <= upper_val:
            reasons.append('bb_breakout_up')
            direction = 'long'
        # Breakout short: close < lower BB
        elif close[last] < lower_val and close[last - 1] >= lower_val:
            reasons.append('bb_breakout_down')
            direction = 'short'
        else:
            return None

        reasons.append('squeeze')

        if adx_rising:
            reasons.append('adx_rising')
        if has_volume:
            reasons.append('volume_surge')

        # Need at least 3 reasons
        if len(reasons) < 3:
            return None

        entry_price = float(close[last])

        # SL: mid BB or ATR-based, whichever is tighter
        sl_atr = atr_val * self.atr_sl_mult
        sl_bb = abs(entry_price - mid_val)
        sl_distance = min(sl_atr, sl_bb) if sl_bb > 0 else sl_atr
        min_sl = entry_price * self.min_sl_pct / 100
        sl_distance = max(sl_distance, min_sl)

        # TP: BB width projected or ratio×SL
        bb_range = upper_val - lower_val
        tp_from_bb = bb_range
        tp_from_ratio = sl_distance * self.tp_ratio
        tp_distance = max(tp_from_bb, tp_from_ratio)

        if direction == 'long':
            sl_price = entry_price - sl_distance
            tp_price = entry_price + tp_distance
        else:
            sl_price = entry_price + sl_distance
            tp_price = entry_price - tp_distance

        return Signal(
            direction=direction,
            strength=len(reasons),
            entry_price=entry_price,
            sl_price=sl_price,
            tp_price=tp_price,
            reasons=reasons,
        )
