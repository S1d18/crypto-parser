"""Donchian Breakout — range expansion through recent high/low.

Logic:
- Recent price range contracts relative to its own history
- Current candle closes through Donchian channel high/low
- Volume must expand
- ADX should be acceptable or rising
- Avoid very overextended breakouts via ATR-based overshoot checks
"""

from __future__ import annotations

import numpy as np

from scalper.indicators import calc_adx, calc_atr, calc_volume_ratio
from scalper.signals import Signal


class DonchianBreakoutEngine:
    """Breakout from local range using Donchian channels."""

    channel_period: int = 20
    squeeze_lookback: int = 50
    atr_period: int = 14
    adx_period: int = 14
    volume_ma_period: int = 20

    volume_surge: float = 1.35
    adx_min: int = 16
    tp_ratio: float = 2.6
    atr_sl_mult: float = 1.6
    min_sl_pct: float = 0.8
    overshoot_atr_max: float = 1.2
    breakout_body_ratio: float = 0.3

    def evaluate(self, ohlcv: dict[str, np.ndarray]) -> Signal | None:
        close = ohlcv['close']
        high = ohlcv['high']
        low = ohlcv['low']
        open_ = ohlcv['open']
        volume = ohlcv['volume']

        min_len = self.channel_period + self.squeeze_lookback + 5
        if len(close) < min_len:
            return None

        atr = calc_atr(high, low, close, self.atr_period)
        adx = calc_adx(high, low, close, self.adx_period)
        vol_r = calc_volume_ratio(volume, self.volume_ma_period)

        last = len(close) - 1
        prev = last - 1

        atr_val = atr[last]
        adx_val = adx[last]
        vr_val = vol_r[last]

        if any(np.isnan(v) for v in [atr_val, adx_val]) or atr_val <= 0:
            return None
        if adx_val < self.adx_min:
            return None
        if np.isnan(vr_val) or vr_val < self.volume_surge:
            return None

        upper_prev = np.max(high[last - self.channel_period:last])
        lower_prev = np.min(low[last - self.channel_period:last])
        range_prev = upper_prev - lower_prev
        if range_prev <= 0:
            return None

        # Check recent contraction relative to older lookback ranges.
        widths = []
        start = max(self.channel_period, last - self.squeeze_lookback)
        for i in range(start, last):
            hi = np.max(high[i - self.channel_period:i])
            lo = np.min(low[i - self.channel_period:i])
            widths.append(hi - lo)
        widths = np.array(widths, dtype=float)
        widths = widths[widths > 0]
        if len(widths) < 10:
            return None

        width_threshold = np.percentile(widths, 35)
        if range_prev > width_threshold * 1.15:
            return None

        body = abs(close[last] - open_[last])
        candle_range = max(high[last] - low[last], 1e-9)
        body_ratio = body / candle_range

        reasons = ['range_contraction', 'volume_confirmed']
        direction = None
        confidence = 66

        # LONG breakout
        if close[last] > upper_prev and close[prev] <= upper_prev:
            overshoot = (close[last] - upper_prev) / atr_val
            if overshoot > self.overshoot_atr_max:
                return None
            if body_ratio < self.breakout_body_ratio:
                return None

            direction = 'long'
            reasons.append('donchian_breakout_up')

            if close[last] >= high[last] - candle_range * 0.2:
                reasons.append('close_near_high')
                confidence += 6

            if adx_val >= 22:
                reasons.append('trend_strength')
                confidence += 6

            adx_prev = adx[prev]
            if not np.isnan(adx_prev) and adx_val > adx_prev:
                reasons.append('adx_rising')
                confidence += 6

            if vr_val >= 1.8:
                reasons.append('strong_volume')
                confidence += 6

        # SHORT breakout
        elif close[last] < lower_prev and close[prev] >= lower_prev:
            overshoot = (lower_prev - close[last]) / atr_val
            if overshoot > self.overshoot_atr_max:
                return None
            if body_ratio < self.breakout_body_ratio:
                return None

            direction = 'short'
            reasons.append('donchian_breakout_down')

            if close[last] <= low[last] + candle_range * 0.2:
                reasons.append('close_near_low')
                confidence += 6

            if adx_val >= 22:
                reasons.append('trend_strength')
                confidence += 6

            adx_prev = adx[prev]
            if not np.isnan(adx_prev) and adx_val > adx_prev:
                reasons.append('adx_rising')
                confidence += 6

            if vr_val >= 1.8:
                reasons.append('strong_volume')
                confidence += 6

        if direction is None:
            return None

        confidence = min(confidence, 100)
        entry_price = float(close[last])

        sl_distance = max(atr_val * self.atr_sl_mult, entry_price * self.min_sl_pct / 100)
        tp_distance = max(range_prev, sl_distance * self.tp_ratio)

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
            sl_price=float(sl_price),
            tp_price=float(tp_price),
            confidence=confidence,
            reasons=reasons,
        )
