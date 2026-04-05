"""Technical indicators — pure numpy, no pandas."""

import numpy as np


def calc_ema(data: np.ndarray, period: int) -> np.ndarray:
    """Exponential Moving Average.

    Returns array same length as input; first (period-1) values are NaN.
    """
    out = np.full_like(data, np.nan, dtype=float)
    if len(data) < period:
        return out
    # seed with SMA
    out[period - 1] = np.mean(data[:period])
    k = 2.0 / (period + 1)
    for i in range(period, len(data)):
        out[i] = data[i] * k + out[i - 1] * (1 - k)
    return out


def calc_rsi(close: np.ndarray, period: int = 14) -> np.ndarray:
    """RSI with Wilder's smoothing. Range 0-100."""
    out = np.full(len(close), np.nan, dtype=float)
    if len(close) < period + 1:
        return out

    deltas = np.diff(close)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    if avg_loss == 0:
        out[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        out[period] = 100.0 - 100.0 / (1.0 + rs)

    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            out[i + 1] = 100.0
        else:
            rs = avg_gain / avg_loss
            out[i + 1] = 100.0 - 100.0 / (1.0 + rs)

    return out


def calc_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray,
             period: int = 14) -> np.ndarray:
    """Average True Range using Wilder's smoothing."""
    n = len(close)
    out = np.full(n, np.nan, dtype=float)
    if n < period + 1:
        return out

    tr = np.empty(n, dtype=float)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i],
                     abs(high[i] - close[i - 1]),
                     abs(low[i] - close[i - 1]))

    out[period] = np.mean(tr[1:period + 1])
    for i in range(period + 1, n):
        out[i] = (out[i - 1] * (period - 1) + tr[i]) / period

    return out


def calc_adx(high: np.ndarray, low: np.ndarray, close: np.ndarray,
             period: int = 14) -> np.ndarray:
    """Average Directional Index. Range 0-100."""
    n = len(close)
    out = np.full(n, np.nan, dtype=float)
    if n < 2 * period + 1:
        return out

    # True Range
    tr = np.empty(n, dtype=float)
    tr[0] = high[0] - low[0]
    plus_dm = np.zeros(n, dtype=float)
    minus_dm = np.zeros(n, dtype=float)

    for i in range(1, n):
        tr[i] = max(high[i] - low[i],
                     abs(high[i] - close[i - 1]),
                     abs(low[i] - close[i - 1]))
        up = high[i] - high[i - 1]
        down = low[i - 1] - low[i]
        if up > down and up > 0:
            plus_dm[i] = up
        if down > up and down > 0:
            minus_dm[i] = down

    # Wilder's smoothing for TR, +DM, -DM
    atr_s = np.mean(tr[1:period + 1])
    pdm_s = np.mean(plus_dm[1:period + 1])
    mdm_s = np.mean(minus_dm[1:period + 1])

    dx_vals = []

    def _dx(atr_v, pdm_v, mdm_v):
        if atr_v == 0:
            return 0.0
        pdi = 100.0 * pdm_v / atr_v
        mdi = 100.0 * mdm_v / atr_v
        s = pdi + mdi
        if s == 0:
            return 0.0
        return 100.0 * abs(pdi - mdi) / s

    dx_vals.append(_dx(atr_s, pdm_s, mdm_s))

    for i in range(period + 1, n):
        atr_s = (atr_s * (period - 1) + tr[i]) / period
        pdm_s = (pdm_s * (period - 1) + plus_dm[i]) / period
        mdm_s = (mdm_s * (period - 1) + minus_dm[i]) / period
        dx_vals.append(_dx(atr_s, pdm_s, mdm_s))

    # ADX = smoothed DX over `period`
    if len(dx_vals) < period:
        return out

    adx_val = np.mean(dx_vals[:period])
    idx = 2 * period  # index in original array
    out[idx] = adx_val

    for j in range(period, len(dx_vals)):
        adx_val = (adx_val * (period - 1) + dx_vals[j]) / period
        out[period + j] = adx_val

    return out


def calc_volume_ratio(volume: np.ndarray, period: int = 20) -> np.ndarray:
    """Current volume divided by EMA of volume."""
    ema_vol = calc_ema(volume, period)
    out = np.full(len(volume), np.nan, dtype=float)
    valid = ~np.isnan(ema_vol) & (ema_vol > 0)
    out[valid] = volume[valid] / ema_vol[valid]
    return out


def calc_bollinger(close: np.ndarray, period: int = 20,
                   num_std: float = 2.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Bollinger Bands: (middle, upper, lower).

    middle = SMA(period)
    upper  = middle + num_std * std
    lower  = middle - num_std * std
    """
    n = len(close)
    middle = np.full(n, np.nan, dtype=float)
    upper = np.full(n, np.nan, dtype=float)
    lower = np.full(n, np.nan, dtype=float)

    for i in range(period - 1, n):
        window = close[i - period + 1:i + 1]
        m = np.mean(window)
        s = np.std(window, ddof=0)
        middle[i] = m
        upper[i] = m + num_std * s
        lower[i] = m - num_std * s

    return middle, upper, lower


def calc_bb_width(upper: np.ndarray, lower: np.ndarray,
                  middle: np.ndarray) -> np.ndarray:
    """Bollinger Band width = (upper - lower) / middle. Measures squeeze."""
    out = np.full(len(upper), np.nan, dtype=float)
    valid = ~np.isnan(middle) & (middle > 0)
    out[valid] = (upper[valid] - lower[valid]) / middle[valid]
    return out


def calc_vwap(high: np.ndarray, low: np.ndarray, close: np.ndarray,
              volume: np.ndarray) -> np.ndarray:
    """Session VWAP (cumulative from start of data).

    VWAP = cumsum(typical_price * volume) / cumsum(volume)
    """
    typical = (high + low + close) / 3.0
    cum_tv = np.cumsum(typical * volume)
    cum_vol = np.cumsum(volume)
    out = np.full(len(close), np.nan, dtype=float)
    valid = cum_vol > 0
    out[valid] = cum_tv[valid] / cum_vol[valid]
    return out


def calc_obv(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
    """On-Balance Volume."""
    n = len(close)
    out = np.zeros(n, dtype=float)
    for i in range(1, n):
        if close[i] > close[i - 1]:
            out[i] = out[i - 1] + volume[i]
        elif close[i] < close[i - 1]:
            out[i] = out[i - 1] - volume[i]
        else:
            out[i] = out[i - 1]
    return out


def calc_obv_slope(obv: np.ndarray, period: int = 5) -> np.ndarray:
    """OBV slope over last N bars (positive = accumulation)."""
    n = len(obv)
    out = np.full(n, np.nan, dtype=float)
    for i in range(period, n):
        if not np.isnan(obv[i]) and not np.isnan(obv[i - period]):
            out[i] = obv[i] - obv[i - period]
    return out
