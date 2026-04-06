"""VWAP Reversion — fade overextension back toward VWAP.

Logic:
- Price is materially stretched away from VWAP (ATR-normalized)
- Move is extended enough to be worth fading, but not in strong runaway trend
- Need reversal-style confirmation from candle / RSI / OBV slope
- Target is reversion toward VWAP neighborhood
"""

from __future__ import annotations

import numpy as np

from scalper.indicators import (
    calc_adx,
    calc_atr,
    calc_ema,
    calc_obv,
    calc_obv_slope,
    calc_rsi,
    calc_volume_ratio,
    calc_vwap,
)
from scalper.signals import Signal


class VwapReversionEngine:
    """Fade stretched intraday moves back toward VWAP."""

    ema_fast: int = 9
    ema_slow: int = 21
    rsi_period: int = 14
    atr_period: int = 14
    adx_period: int = 14
    volume_ma_period: int = 20
    obv_slope_period: int = 5

    adx_max: int = 24
    stretch_atr_min: float = 1.6
    stretch_atr_max: float = 4.5
    volume_max: float = 2.8
    tp_ratio: float = 1.8
    atr_sl_mult: float = 1.1
    min_sl_pct: float = 0.6

    def evaluate(self, ohlcv: dict[str, np.ndarray]) -> Signal | None:
        close = ohlcv['close']
        high = ohlcv['high']
        low = ohlcv['low']
        open_ = ohlcv['open']
        volume = ohlcv['volume']

        if len(close) < 60:
            return None

        vwap = calc_vwap(high, low, close, volume)
        atr = calc_atr(high, low, close, self.atr_period)
        adx = calc_adx(high, low, close, self.adx_period)
        rsi = calc_rsi(close, self.rsi_period)
        ema_f = calc_ema(close, self.ema_fast)
        ema_s = calc_ema(close, self.ema_slow)
        vol_r = calc_volume_ratio(volume, self.volume_ma_period)
        obv = calc_obv(close, volume)
        obv_sl = calc_obv_slope(obv, self.obv_slope_period)

        last = len(close) - 1
        prev = last - 1

        vals = [vwap[last], atr[last], adx[last], rsi[last], ema_f[last], ema_s[last]]
        if any(np.isnan(v) for v in vals):
            return None

        vwap_val = vwap[last]
        atr_val = atr[last]
        adx_val = adx[last]
        rsi_val = rsi[last]
        ef = ema_f[last]
        es = ema_s[last]
        vr_val = vol_r[last]
        obv_slope = obv_sl[last]

        if atr_val <= 0 or vwap_val <= 0:
            return None
        if adx_val > self.adx_max:
            return None
        if not np.isnan(vr_val) and vr_val > self.volume_max:
            return None

        price = close[last]
        distance = price - vwap_val
        stretch_atr = abs(distance) / atr_val
        if stretch_atr < self.stretch_atr_min or stretch_atr > self.stretch_atr_max:
            return None

        candle_body = abs(close[last] - open_[last])
        candle_range = max(high[last] - low[last], 1e-9)
        upper_wick = high[last] - max(close[last], open_[last])
        lower_wick = min(close[last], open_[last]) - low[last]

        reasons = []
        direction = None
        confidence = 64

        # SHORT reversion: price extended above VWAP, look for rejection.
        if price > vwap_val:
            confirmations = 0

            if rsi_val >= 67:
                reasons.append('rsi_overextended')
                confirmations += 1
                confidence += 8

            if upper_wick > candle_body * 0.8 or close[last] < open_[last]:
                reasons.append('rejection_candle')
                confirmations += 1
                confidence += 8

            if not np.isnan(obv_slope) and obv_slope <= 0:
                reasons.append('obv_rollover')
                confirmations += 1
                confidence += 6

            if ef <= es or close[last] < ef:
                reasons.append('ema_rollover')
                confirmations += 1
                confidence += 6

            if confirmations >= 2:
                direction = 'short'
                reasons.append('vwap_stretch_up')

        # LONG reversion: price extended below VWAP, look for reclaim.
        elif price < vwap_val:
            confirmations = 0

            if rsi_val <= 33:
                reasons.append('rsi_overextended')
                confirmations += 1
                confidence += 8

            if lower_wick > candle_body * 0.8 or close[last] > open_[last]:
                reasons.append('rejection_candle')
                confirmations += 1
                confidence += 8

            if not np.isnan(obv_slope) and obv_slope >= 0:
                reasons.append('obv_rollover')
                confirmations += 1
                confidence += 6

            if ef >= es or close[last] > ef:
                reasons.append('ema_rollover')
                confirmations += 1
                confidence += 6

            if confirmations >= 2:
                direction = 'long'
                reasons.append('vwap_stretch_down')

        if direction is None:
            return None

        confidence = min(confidence, 100)
        entry_price = float(price)
        sl_distance = max(atr_val * self.atr_sl_mult, entry_price * self.min_sl_pct / 100)

        if direction == 'long':
            sl_price = entry_price - sl_distance
            target_distance = min(vwap_val - entry_price, sl_distance * self.tp_ratio)
            tp_price = entry_price + max(target_distance, sl_distance * 0.8)
        else:
            sl_price = entry_price + sl_distance
            target_distance = min(entry_price - vwap_val, sl_distance * self.tp_ratio)
            tp_price = entry_price - max(target_distance, sl_distance * 0.8)

        return Signal(
            direction=direction,
            strength=len(reasons),
            entry_price=entry_price,
            sl_price=float(sl_price),
            tp_price=float(tp_price),
            confidence=confidence,
            reasons=reasons,
        )
