"""Scalp Reversal — быстрый отскок от экстремумов в боковике.

Логика:
- ADX < 25 (рынок в рейндже)
- Цена в зоне BB lower/upper band (в пределах 0.5%)
- RSI < 30 (лонг) или > 70 (шорт)
- Свеча отторжения — бонус к confidence
- Быстрый TP: цель mid BB
- Tight SL за пределами BB
"""

from __future__ import annotations

import numpy as np

from scalper.indicators import (
    calc_atr, calc_adx, calc_rsi, calc_bollinger, calc_volume_ratio,
)
from scalper.signals import Signal


class ScalpReversalEngine:
    """Mean reversion scalps in ranging markets."""

    bb_period: int = 20
    bb_std: float = 2.0
    rsi_period: int = 14
    atr_period: int = 14
    adx_period: int = 14
    volume_ma_period: int = 20

    adx_max: int = 25
    rsi_oversold: int = 30
    rsi_overbought: int = 70

    sl_buffer_atr: float = 0.5
    min_sl_pct: float = 0.5

    def evaluate(self, ohlcv: dict[str, np.ndarray]) -> Signal | None:
        close = ohlcv['close']
        high = ohlcv['high']
        low = ohlcv['low']
        volume = ohlcv['volume']
        open_ = ohlcv['open']

        if len(close) < self.bb_period + 10:
            return None

        mid, upper, lower = calc_bollinger(close, self.bb_period, self.bb_std)
        rsi = calc_rsi(close, self.rsi_period)
        atr = calc_atr(high, low, close, self.atr_period)
        adx = calc_adx(high, low, close, self.adx_period)
        vol_r = calc_volume_ratio(volume, self.volume_ma_period)

        last = len(close) - 1

        adx_val = adx[last]
        atr_val = atr[last]
        rsi_val = rsi[last]

        if any(np.isnan(v) for v in [adx_val, atr_val, rsi_val]):
            return None

        if adx_val > self.adx_max:
            return None

        if atr_val <= 0:
            return None

        upper_val = upper[last]
        lower_val = lower[last]
        mid_val = mid[last]

        if any(np.isnan(v) for v in [upper_val, lower_val, mid_val]):
            return None

        body = abs(close[last] - open_[last])
        upper_wick = high[last] - max(close[last], open_[last])
        lower_wick = min(close[last], open_[last]) - low[last]

        reasons = []
        direction = None
        confidence = 60

        # --- LONG: price near/below lower BB + RSI oversold ---
        if close[last] <= lower_val * 1.005 or low[last] <= lower_val:
            if rsi_val < self.rsi_oversold:
                reasons.append('bb_lower_touch')
                reasons.append('rsi_oversold')
                direction = 'long'

                # Bonus: rejection candle
                if body > 0 and lower_wick > body * 1.0:
                    reasons.append('rejection_candle')
                    confidence += 10

                # Bonus: normal volume
                vr_val = vol_r[last]
                if not np.isnan(vr_val) and vr_val < 3.0:
                    reasons.append('normal_volume')
                    confidence += 5

                # Bonus: very extreme RSI
                if rsi_val < 20:
                    confidence += 10

                # Bonus: very low ADX = strong range
                if adx_val < 15:
                    confidence += 5

        # --- SHORT: price near/above upper BB + RSI overbought ---
        elif close[last] >= upper_val * 0.995 or high[last] >= upper_val:
            if rsi_val > self.rsi_overbought:
                reasons.append('bb_upper_touch')
                reasons.append('rsi_overbought')
                direction = 'short'

                if body > 0 and upper_wick > body * 1.0:
                    reasons.append('rejection_candle')
                    confidence += 10

                vr_val = vol_r[last]
                if not np.isnan(vr_val) and vr_val < 3.0:
                    reasons.append('normal_volume')
                    confidence += 5

                if rsi_val > 80:
                    confidence += 10

                if adx_val < 15:
                    confidence += 5

        if direction is None:
            return None

        confidence = min(confidence, 100)
        entry_price = float(close[last])

        sl_buffer = atr_val * self.sl_buffer_atr
        min_sl = entry_price * self.min_sl_pct / 100

        if direction == 'long':
            sl_price = lower_val - sl_buffer
            sl_distance = entry_price - sl_price
            sl_distance = max(sl_distance, min_sl)
            sl_price = entry_price - sl_distance
            tp_price = mid_val
        else:
            sl_price = upper_val + sl_buffer
            sl_distance = sl_price - entry_price
            sl_distance = max(sl_distance, min_sl)
            sl_price = entry_price + sl_distance
            tp_price = mid_val

        return Signal(
            direction=direction,
            strength=len(reasons),
            entry_price=entry_price,
            sl_price=sl_price,
            tp_price=tp_price,
            confidence=confidence,
            reasons=reasons,
        )
