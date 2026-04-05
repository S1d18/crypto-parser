"""VWAP Bounce — отскок от VWAP с подтверждением объёма.

Логика:
- VWAP как "справедливая цена" — магнит для цены
- Цена подходит к VWAP (в пределах 0.3% от VWAP)
- OBV slope подтверждает направление (покупатели/продавцы доминируют)
- Volume на касании выше среднего
- EMA trend для фильтра направления
- SL: 1×ATR за VWAP
- TP: 2× SL distance
"""

from __future__ import annotations

import numpy as np

from scalper.indicators import (
    calc_atr, calc_ema, calc_rsi, calc_volume_ratio,
    calc_vwap, calc_obv, calc_obv_slope,
)
from scalper.signals import Signal


class VwapBounceEngine:
    """Entries on VWAP bounces with volume confirmation."""

    ema_fast: int = 9
    ema_slow: int = 21
    rsi_period: int = 14
    atr_period: int = 14
    volume_ma_period: int = 20
    obv_slope_period: int = 5

    # VWAP proximity: price within 0.3% of VWAP
    vwap_proximity_pct: float = 0.3

    # Volume confirmation
    volume_min: float = 1.2

    # SL/TP
    atr_sl_mult: float = 1.2
    tp_ratio: float = 2.0
    min_sl_pct: float = 0.6

    def evaluate(self, ohlcv: dict[str, np.ndarray]) -> Signal | None:
        close = ohlcv['close']
        high = ohlcv['high']
        low = ohlcv['low']
        volume = ohlcv['volume']

        if len(close) < 50:
            return None

        vwap = calc_vwap(high, low, close, volume)
        obv = calc_obv(close, volume)
        obv_sl = calc_obv_slope(obv, self.obv_slope_period)
        ema_f = calc_ema(close, self.ema_fast)
        ema_s = calc_ema(close, self.ema_slow)
        rsi = calc_rsi(close, self.rsi_period)
        atr = calc_atr(high, low, close, self.atr_period)
        vol_r = calc_volume_ratio(volume, self.volume_ma_period)

        last = len(close) - 1

        vwap_val = vwap[last]
        atr_val = atr[last]
        rsi_val = rsi[last]
        obv_slope = obv_sl[last]
        ef, es = ema_f[last], ema_s[last]
        vr_val = vol_r[last]

        if any(np.isnan(v) for v in [vwap_val, atr_val, rsi_val, ef, es]):
            return None

        if atr_val <= 0 or vwap_val <= 0:
            return None

        # --- Price near VWAP ---
        price = close[last]
        distance_to_vwap = abs(price - vwap_val) / vwap_val * 100

        if distance_to_vwap > self.vwap_proximity_pct:
            return None

        # --- Check if price is bouncing (was further, now returning) ---
        prev_distance = abs(close[last - 1] - vwap_val) / vwap_val * 100
        approaching = prev_distance > distance_to_vwap

        reasons = []
        direction = None

        # --- LONG: price at/below VWAP, bouncing up ---
        if price <= vwap_val * 1.001:  # at or below VWAP
            # OBV rising = buyers accumulating
            if not np.isnan(obv_slope) and obv_slope > 0:
                reasons.append('obv_accumulation')

            # EMA trend supports long
            if ef > es:
                reasons.append('ema_uptrend')

            # Volume present
            if not np.isnan(vr_val) and vr_val > self.volume_min:
                reasons.append('volume_confirm')

            # RSI not overbought
            if 30 < rsi_val < 60:
                reasons.append('rsi_neutral')

            # Approaching VWAP from below
            if price >= vwap_val * 0.998 and approaching:
                reasons.append('vwap_bounce')

            if len(reasons) >= 3:
                direction = 'long'

        # --- SHORT: price at/above VWAP, bouncing down ---
        elif price >= vwap_val * 0.999:
            if not np.isnan(obv_slope) and obv_slope < 0:
                reasons.append('obv_distribution')

            if ef < es:
                reasons.append('ema_downtrend')

            if not np.isnan(vr_val) and vr_val > self.volume_min:
                reasons.append('volume_confirm')

            if 40 < rsi_val < 70:
                reasons.append('rsi_neutral')

            if price <= vwap_val * 1.002 and approaching:
                reasons.append('vwap_bounce')

            if len(reasons) >= 3:
                direction = 'short'

        if direction is None:
            return None

        entry_price = float(price)
        sl_distance = atr_val * self.atr_sl_mult
        min_sl = entry_price * self.min_sl_pct / 100
        sl_distance = max(sl_distance, min_sl)

        if direction == 'long':
            sl_price = entry_price - sl_distance
            tp_price = entry_price + sl_distance * self.tp_ratio
        else:
            sl_price = entry_price + sl_distance
            tp_price = entry_price - sl_distance * self.tp_ratio

        return Signal(
            direction=direction,
            strength=len(reasons),
            entry_price=entry_price,
            sl_price=sl_price,
            tp_price=tp_price,
            reasons=reasons,
        )
