"""Breakout — пробой после сжатия (Bollinger Squeeze).

Логика:
- BB width ниже среднего = сжатие (рынок копит энергию)
- Цена пробивает BB с ускорением объёма (ОБЯЗАТЕЛЬНО > 1.5×)
- ADX > 20 — минимальный импульс для подтверждения
- Свеча пробоя закрывается за BB (не просто тень)
- SL: 2×ATR (шире — дать пробою пространство)
- TP: ширина BB спроецирована или 2.5× SL
"""

from __future__ import annotations

import numpy as np

from scalper.indicators import (
    calc_atr, calc_adx, calc_bollinger, calc_bb_width,
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

    squeeze_lookback: int = 50
    volume_surge: float = 1.5
    adx_min: int = 20

    atr_sl_mult: float = 2.0       # wider SL for breakouts
    min_sl_pct: float = 1.0
    tp_ratio: float = 2.5          # bigger TP target

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

        # --- ADX must show some momentum ---
        adx_val = adx[last]
        if np.isnan(adx_val) or adx_val < self.adx_min:
            return None

        # --- Volume REQUIRED (not optional) ---
        vr_val = vol_r[last]
        if np.isnan(vr_val) or vr_val < self.volume_surge:
            return None

        # --- Squeeze: BB width was below average recently ---
        lookback_start = max(0, last - self.squeeze_lookback)
        recent_widths = bb_w[lookback_start:last]
        valid_widths = recent_widths[~np.isnan(recent_widths)]
        if len(valid_widths) < 10:
            return None

        avg_width = np.mean(valid_widths)
        was_squeezed = False
        for i in range(max(0, last - 8), last):
            if not np.isnan(bb_w[i]) and bb_w[i] < avg_width * 0.85:
                was_squeezed = True
                break

        if not was_squeezed:
            return None

        upper_val = upper[last]
        lower_val = lower[last]
        mid_val = mid[last]

        if any(np.isnan(v) for v in [upper_val, lower_val, mid_val]):
            return None

        # --- Direction: close must be BEYOND BB (not just wick) ---
        reasons = []
        direction = None
        confidence = 65  # base higher since volume + ADX already confirmed

        if close[last] > upper_val and close[last - 1] <= upper_val * 1.002:
            # Reject if price already too far from BB (late entry)
            overshoot = (close[last] - upper_val) / atr_val
            if overshoot > 1.5:
                return None
            reasons.append('bb_breakout_up')
            direction = 'long'
        elif close[last] < lower_val and close[last - 1] >= lower_val * 0.998:
            overshoot = (lower_val - close[last]) / atr_val
            if overshoot > 1.5:
                return None
            reasons.append('bb_breakout_down')
            direction = 'short'
        else:
            return None

        reasons.append('squeeze')
        reasons.append('volume_confirmed')

        # Bonuses
        if not np.isnan(adx_val) and last >= 1:
            adx_prev = adx[last - 1]
            if not np.isnan(adx_prev) and adx_val > adx_prev:
                reasons.append('adx_rising')
                confidence += 10

        if adx_val > 30:
            reasons.append('strong_momentum')
            confidence += 5

        if vr_val > 2.0:
            reasons.append('strong_volume')
            confidence += 5

        # 2+ consecutive candles in breakout direction = momentum
        if last >= 2:
            if direction == 'long' and close[last] > close[last-1] > close[last-2]:
                reasons.append('momentum_candles')
                confidence += 5
            elif direction == 'short' and close[last] < close[last-1] < close[last-2]:
                reasons.append('momentum_candles')
                confidence += 5

        confidence = min(confidence, 100)
        entry_price = float(close[last])

        # Wider SL for breakouts
        sl_distance = atr_val * self.atr_sl_mult
        min_sl = entry_price * self.min_sl_pct / 100
        sl_distance = max(sl_distance, min_sl)

        # TP: BB width projected or ratio * SL
        bb_range = upper_val - lower_val
        tp_distance = max(bb_range, sl_distance * self.tp_ratio)

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
            confidence=confidence,
            reasons=reasons,
        )
