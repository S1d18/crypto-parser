"""EMA Retest — continuation after pullback into EMA zone.

Logic:
- EMA stack defines trend (fast > mid > slow for longs, inverse for shorts)
- Price must pull back into the EMA fast/mid zone without breaking structure badly
- Current candle should show reclaim / continuation from the EMA zone
- Volume and ADX improve confidence
- SL: max(swing-based buffer, ATR-based floor)
- TP: multiple of SL distance
"""

from __future__ import annotations

import numpy as np

from scalper.indicators import calc_adx, calc_atr, calc_ema, calc_volume_ratio
from scalper.signals import Signal


class EmaRetestEngine:
    """Trend continuation entries after EMA pullback and reclaim."""

    ema_fast: int = 9
    ema_mid: int = 21
    ema_slow: int = 55
    atr_period: int = 14
    adx_period: int = 14
    volume_ma_period: int = 20

    adx_min: int = 18
    volume_min: float = 1.05
    tp_ratio: float = 2.4
    atr_sl_mult: float = 1.2
    min_sl_pct: float = 0.6
    reclaim_body_ratio: float = 0.25

    def evaluate(self, ohlcv: dict[str, np.ndarray]) -> Signal | None:
        close = ohlcv['close']
        high = ohlcv['high']
        low = ohlcv['low']
        open_ = ohlcv['open']
        volume = ohlcv['volume']

        if len(close) < self.ema_slow + 8:
            return None

        ema_f = calc_ema(close, self.ema_fast)
        ema_m = calc_ema(close, self.ema_mid)
        ema_s = calc_ema(close, self.ema_slow)
        atr = calc_atr(high, low, close, self.atr_period)
        adx = calc_adx(high, low, close, self.adx_period)
        vol_r = calc_volume_ratio(volume, self.volume_ma_period)

        last = len(close) - 1
        prev = last - 1

        ef, em, es = ema_f[last], ema_m[last], ema_s[last]
        ef_prev, em_prev, es_prev = ema_f[prev], ema_m[prev], ema_s[prev]
        atr_val = atr[last]
        adx_val = adx[last]
        vr_val = vol_r[last]

        if any(np.isnan(v) for v in [ef, em, es, ef_prev, em_prev, es_prev, atr_val, adx_val]):
            return None
        if atr_val <= 0 or adx_val < self.adx_min:
            return None

        body = abs(close[last] - open_[last])
        candle_range = max(high[last] - low[last], 1e-9)
        body_ratio = body / candle_range

        reasons = []
        direction = None
        confidence = 62

        zone_low = min(ef, em)
        zone_high = max(ef, em)
        prev_zone_low = min(ef_prev, em_prev)
        prev_zone_high = max(ef_prev, em_prev)

        # LONG continuation after pullback into EMA zone and reclaim.
        if ef > em > es and close[last] > es:
            pulled_back = low[prev] <= prev_zone_high * 1.003 and close[prev] >= es_prev * 0.995
            reclaimed = close[last] > zone_high and low[last] <= zone_high * 1.002 and close[last] > open_[last]
            structure_ok = low[last] > es * 0.992

            if pulled_back and reclaimed and structure_ok:
                direction = 'long'
                reasons.extend(['ema_bull_stack', 'pullback_into_ema', 'ema_reclaim'])

                if body_ratio >= self.reclaim_body_ratio:
                    reasons.append('strong_reclaim_candle')
                    confidence += 8

                if not np.isnan(vr_val) and vr_val >= self.volume_min:
                    reasons.append('volume_confirm')
                    confidence += 7

                ema_spread = (ef - es) / es * 100 if es > 0 else 0
                if ema_spread >= 0.35:
                    reasons.append('trend_separation')
                    confidence += 6

                if adx_val >= 25:
                    reasons.append('trend_strength')
                    confidence += 7

        # SHORT continuation after pullback into EMA zone and rejection.
        elif ef < em < es and close[last] < es:
            pulled_back = high[prev] >= prev_zone_low * 0.997 and close[prev] <= es_prev * 1.005
            reclaimed = close[last] < zone_low and high[last] >= zone_low * 0.998 and close[last] < open_[last]
            structure_ok = high[last] < es * 1.008

            if pulled_back and reclaimed and structure_ok:
                direction = 'short'
                reasons.extend(['ema_bear_stack', 'pullback_into_ema', 'ema_reject'])

                if body_ratio >= self.reclaim_body_ratio:
                    reasons.append('strong_reclaim_candle')
                    confidence += 8

                if not np.isnan(vr_val) and vr_val >= self.volume_min:
                    reasons.append('volume_confirm')
                    confidence += 7

                ema_spread = (es - ef) / es * 100 if es > 0 else 0
                if ema_spread >= 0.35:
                    reasons.append('trend_separation')
                    confidence += 6

                if adx_val >= 25:
                    reasons.append('trend_strength')
                    confidence += 7

        if direction is None:
            return None

        confidence = min(confidence, 100)
        entry_price = float(close[last])

        if direction == 'long':
            swing_ref = min(low[last], low[prev], zone_low)
            sl_price = swing_ref - atr_val * 0.2
            sl_distance = entry_price - sl_price
        else:
            swing_ref = max(high[last], high[prev], zone_high)
            sl_price = swing_ref + atr_val * 0.2
            sl_distance = sl_price - entry_price

        min_sl = max(atr_val * self.atr_sl_mult, entry_price * self.min_sl_pct / 100)
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
            sl_price=float(sl_price),
            tp_price=float(tp_price),
            confidence=confidence,
            reasons=reasons,
        )
