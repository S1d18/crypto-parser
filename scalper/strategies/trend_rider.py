"""Trend Rider — вход по тренду на откатах.

Логика:
- EMA fast > EMA slow определяет тренд (2 EMA — основа)
- EMA mid alignment — бонус к confidence
- ADX > 20 подтверждает силу тренда
- RSI в зоне отката (35-60 лонг, 40-65 шорт) — не перекуплен/перепродан
- Объём подтверждает возобновление движения
- SL: 1.5×ATR, TP: 2.5× SL
"""

from __future__ import annotations

import numpy as np

from scalper.indicators import (
    calc_atr, calc_adx, calc_ema, calc_rsi, calc_volume_ratio,
)
from scalper.signals import Signal


class TrendRiderEngine:
    """Trend-following entries on pullbacks."""

    ema_fast: int = 9
    ema_mid: int = 21
    ema_slow: int = 55
    rsi_period: int = 14
    atr_period: int = 14
    adx_period: int = 14
    adx_min: int = 20
    volume_ma_period: int = 20

    # Wider RSI zones
    rsi_pullback_long_low: int = 35
    rsi_pullback_long_high: int = 60
    rsi_pullback_short_low: int = 40
    rsi_pullback_short_high: int = 65

    atr_sl_mult: float = 1.5
    tp_ratio: float = 2.5
    min_sl_pct: float = 0.8

    def evaluate(self, ohlcv: dict[str, np.ndarray]) -> Signal | None:
        close = ohlcv['close']
        high = ohlcv['high']
        low = ohlcv['low']
        volume = ohlcv['volume']

        if len(close) < self.ema_slow + 5:
            return None

        ema_f = calc_ema(close, self.ema_fast)
        ema_m = calc_ema(close, self.ema_mid)
        ema_s = calc_ema(close, self.ema_slow)
        rsi = calc_rsi(close, self.rsi_period)
        atr = calc_atr(high, low, close, self.atr_period)
        adx = calc_adx(high, low, close, self.adx_period)
        vol_r = calc_volume_ratio(volume, self.volume_ma_period)

        last = len(close) - 1

        adx_val = adx[last]
        if np.isnan(adx_val) or adx_val < self.adx_min:
            return None

        atr_val = atr[last]
        if np.isnan(atr_val) or atr_val <= 0:
            return None

        ef, em, es = ema_f[last], ema_m[last], ema_s[last]
        rsi_val = rsi[last]
        vr_val = vol_r[last]

        if any(np.isnan(v) for v in [ef, em, es, rsi_val]):
            return None

        reasons = []
        direction = None
        confidence = 60  # base

        # --- LONG: EMA fast > slow (core) ---
        if ef > es:
            if self.rsi_pullback_long_low <= rsi_val <= self.rsi_pullback_long_high:
                reasons.append('ema_uptrend')
                reasons.append('rsi_pullback')
                direction = 'long'

                # Bonuses
                if ef > em > es:
                    reasons.append('full_alignment')
                    confidence += 10

                if close[last] >= ef * 0.997 and close[last - 1] <= ef * 1.001:
                    reasons.append('ema_bounce')
                    confidence += 10

                if not np.isnan(vr_val) and vr_val > 1.1:
                    reasons.append('volume_confirm')
                    confidence += 10

                if adx_val > 35:
                    reasons.append('strong_trend')
                    confidence += 5

        # --- SHORT: EMA fast < slow (core) ---
        elif ef < es:
            if self.rsi_pullback_short_low <= rsi_val <= self.rsi_pullback_short_high:
                reasons.append('ema_downtrend')
                reasons.append('rsi_pullback')
                direction = 'short'

                if ef < em < es:
                    reasons.append('full_alignment')
                    confidence += 10

                if close[last] <= ef * 1.003 and close[last - 1] >= ef * 0.999:
                    reasons.append('ema_bounce')
                    confidence += 10

                if not np.isnan(vr_val) and vr_val > 1.1:
                    reasons.append('volume_confirm')
                    confidence += 10

                if adx_val > 35:
                    reasons.append('strong_trend')
                    confidence += 5

        if direction is None:
            return None

        confidence = min(confidence, 100)

        entry_price = float(close[last])
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
            confidence=confidence,
            reasons=reasons,
        )
