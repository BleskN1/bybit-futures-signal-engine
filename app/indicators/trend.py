"""Trend indicator calculations using pandas and numpy (EMA, EMA slopes, distances, ADX)."""

import numpy as np
import pandas as pd


def rma(series: pd.Series, length: int) -> pd.Series:
    """
    Wilder's Exponential Moving Average (Running Moving Average / RMA).
    Equivalent to Pine Script ta.rma.
    """
    return series.ewm(alpha=1.0 / length, min_periods=length, adjust=False).mean()


def compute_ema(series: pd.Series, period: int) -> pd.Series:
    """Calculates Exponential Moving Average (EMA)."""
    return series.ewm(span=period, min_periods=period, adjust=False).mean()


def compute_ema_slope(ema: pd.Series, atr: pd.Series, n: int = 5) -> pd.Series:
    """
    Calculates EMA slope normalized by ATR:
    Slope = (EMA[t] - EMA[t-n]) / ATR[t]
    This eliminates price-scale dependency across crypto pairs.
    """
    diff = ema - ema.shift(n)
    safe_atr = atr.replace(0, np.nan)
    return diff / safe_atr


def compute_ema_distances(
    ema20: pd.Series, ema50: pd.Series, ema200: pd.Series
) -> tuple[pd.Series, pd.Series]:
    """
    Calculates normalized percentage distances between EMAs:
    - (EMA20 - EMA50) / EMA50 * 100
    - (EMA50 - EMA200) / EMA200 * 100
    """
    dist_20_50 = ((ema20 - ema50) / ema50) * 100.0
    dist_50_200 = ((ema50 - ema200) / ema200) * 100.0
    return dist_20_50, dist_50_200


def get_ema_alignment(
    ema20: float, ema50: float, ema100: float, ema200: float
) -> str:
    """Determines multi-EMA directional alignment."""
    if np.isnan(ema20) or np.isnan(ema50) or np.isnan(ema100) or np.isnan(ema200):
        return "UNKNOWN"
    if ema20 > ema50 > ema100 > ema200:
        return "BULLISH"
    if ema20 < ema50 < ema100 < ema200:
        return "BEARISH"
    return "MIXED"


def compute_adx(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Computes standard Welles Wilder's Average Directional Index (ADX),
    along with +DI and -DI lines.
    """
    high_prev = high.shift(1)
    low_prev = low.shift(1)
    close_prev = close.shift(1)

    # True Range
    tr1 = high - low
    tr2 = (high - close_prev).abs()
    tr3 = (low - close_prev).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # Directional Movement (+DM, -DM)
    up_move = high - high_prev
    down_move = low_prev - low

    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0),
        index=high.index,
    )
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0),
        index=low.index,
    )

    # Wilder's Smoothing
    smoothed_tr = rma(tr, period)
    smoothed_plus_dm = rma(plus_dm, period)
    smoothed_minus_dm = rma(minus_dm, period)

    # +DI and -DI
    safe_tr = smoothed_tr.replace(0, np.nan)
    plus_di = (smoothed_plus_dm / safe_tr) * 100.0
    minus_di = (smoothed_minus_dm / safe_tr) * 100.0

    # Directional Movement Index (DX)
    di_sum = plus_di + minus_di
    di_diff = (plus_di - minus_di).abs()
    safe_di_sum = di_sum.replace(0, np.nan)
    dx = (di_diff / safe_di_sum) * 100.0

    # ADX is the smoothed DX
    adx = rma(dx, period)

    return adx, plus_di, minus_di
