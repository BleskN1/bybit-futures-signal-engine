"""Volatility indicator calculations using pandas and numpy (ATR, ATR%, Bollinger Bands)."""


import numpy as np
import pandas as pd

from app.indicators.trend import rma


def compute_true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """Calculates True Range (TR)."""
    close_prev = close.shift(1)
    tr1 = high - low
    tr2 = (high - close_prev).abs()
    tr3 = (low - close_prev).abs()
    return pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)


def compute_atr(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> tuple[pd.Series, pd.Series]:
    """
    Computes Welles Wilder's Average True Range (ATR) and normalized ATR%:
    ATR% = (ATR / Close) * 100
    """
    tr = compute_true_range(high, low, close)
    atr = rma(tr, period)
    safe_close = close.replace(0.0, np.nan)
    atr_pct = (atr / safe_close) * 100.0
    return atr, atr_pct


def compute_bollinger_bands(
    close: pd.Series, period: int = 20, stddev: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series, pd.Series]:
    """
    Computes Bollinger Bands:
    - Middle: SMA(Close, period)
    - Upper: Middle + stddev * StdDev
    - Lower: Middle - stddev * StdDev
    - Bandwidth: (Upper - Lower) / Middle
    - %B: (Close - Lower) / (Upper - Lower)
    """
    middle = close.rolling(window=period, min_periods=period).mean()
    std = close.rolling(window=period, min_periods=period).std(ddof=0)

    upper = middle + (stddev * std)
    lower = middle - (stddev * std)

    bandwidth = (upper - lower) / middle.replace(0.0, np.nan)
    band_range = (upper - lower).replace(0.0, np.nan)
    percent_b = (close - lower) / band_range

    return upper, middle, lower, bandwidth, percent_b
