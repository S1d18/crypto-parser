"""Multi-indicator signal generator with adaptive SL/TP."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from scalper.config import Config
from scalper.indicators import (
    calc_adx,
    calc_atr,
    calc_ema,
    calc_rsi,
    calc_volume_ratio,
)


@dataclass
class Signal:
    direction: str          # 'long' or 'short'
    strength: int           # number of matching indicators (1-4)
    entry_price: float
    sl_price: float         # adaptive SL based on ATR
    tp_price: float         # TP = SL distance * tp_ratio
    confidence: int = 60    # 0-100, entry confidence score
    reasons: list[str] = field(default_factory=list)


class SignalEngine:
    """Evaluate OHLCV data and produce a Signal (or None)."""

    def __init__(self, config: Config) -> None:
        self.cfg = config

    # ------------------------------------------------------------------
    def evaluate(self, ohlcv: dict[str, np.ndarray]) -> Signal | None:
        """Return a Signal when >= 2 reasons align, else None.

        Steps:
        1. Compute indicators (EMA fast/slow, RSI, ATR, ADX, volume_ratio).
        2. If ADX < adx_min -> None (sideways / choppy market).
        3. Collect long / short reasons.
        4. Require at least 2 reasons to emit a signal.
        5. Compute adaptive SL (ATR-based) and TP (SL * tp_ratio).
        """
        close = ohlcv['close']
        high = ohlcv['high']
        low = ohlcv['low']
        volume = ohlcv['volume']

        cfg = self.cfg

        # --- indicators ---------------------------------------------------
        ema_fast = calc_ema(close, cfg.ema_fast)
        ema_slow = calc_ema(close, cfg.ema_slow)
        rsi = calc_rsi(close, cfg.rsi_period)
        atr = calc_atr(high, low, close, cfg.atr_period)
        adx = calc_adx(high, low, close, cfg.adx_period)
        vol_ratio = calc_volume_ratio(volume, cfg.volume_ma_period)

        # We need the latest valid values
        last = len(close) - 1

        # ADX filter — skip sideways markets
        adx_val = adx[last]
        if np.isnan(adx_val) or adx_val < cfg.adx_min:
            return None

        atr_val = atr[last]
        if np.isnan(atr_val) or atr_val <= 0:
            return None

        ema_f = ema_fast[last]
        ema_s = ema_slow[last]
        rsi_val = rsi[last]
        vr_val = vol_ratio[last]

        if np.isnan(ema_f) or np.isnan(ema_s) or np.isnan(rsi_val):
            return None

        # --- collect reasons ----------------------------------------------
        long_reasons: list[str] = []
        short_reasons: list[str] = []

        # 1. EMA cross / trend direction
        if ema_f > ema_s:
            long_reasons.append('ema_cross')
        elif ema_f < ema_s:
            short_reasons.append('ema_cross')

        # 2. RSI
        if rsi_val < cfg.rsi_oversold:
            long_reasons.append('rsi_oversold')
        elif rsi_val > cfg.rsi_overbought:
            short_reasons.append('rsi_overbought')

        # 3. Volume spike
        if not np.isnan(vr_val) and vr_val > 1.2:
            long_reasons.append('volume_spike')
            short_reasons.append('volume_spike')

        # 4. Momentum (close vs close[-3])
        if last >= 3:
            if close[last] > close[last - 3]:
                long_reasons.append('momentum')
            elif close[last] < close[last - 3]:
                short_reasons.append('momentum')

        # --- pick dominant direction, need >= min_signals reasons ----------
        min_sig = getattr(cfg, 'min_signals', 2)
        if len(long_reasons) >= min_sig and len(long_reasons) >= len(short_reasons):
            direction = 'long'
            reasons = long_reasons
        elif len(short_reasons) >= min_sig:
            direction = 'short'
            reasons = short_reasons
        else:
            return None

        # --- confidence scoring ------------------------------------------
        confidence = 60 + (len(reasons) - min_sig) * 10
        if adx_val > 35:
            confidence += 5
        if not np.isnan(vr_val) and vr_val > 1.5:
            confidence += 5
        confidence = min(confidence, 100)

        # --- adaptive SL / TP --------------------------------------------
        entry_price = float(close[last])
        sl_distance = atr_val * cfg.atr_sl_multiplier

        # Минимальный SL — не менее min_sl_pct% от цены
        min_sl_pct = getattr(cfg, 'min_sl_pct', 1.5)
        min_sl_distance = entry_price * min_sl_pct / 100
        if sl_distance < min_sl_distance:
            sl_distance = min_sl_distance

        if direction == 'long':
            sl_price = entry_price - sl_distance
            tp_price = entry_price + sl_distance * cfg.tp_ratio
        else:
            sl_price = entry_price + sl_distance
            tp_price = entry_price - sl_distance * cfg.tp_ratio

        return Signal(
            direction=direction,
            strength=len(reasons),
            entry_price=entry_price,
            sl_price=sl_price,
            tp_price=tp_price,
            confidence=confidence,
            reasons=reasons,
        )
