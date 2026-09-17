"""Momentum indicator calculations using pandas and numpy (RSI, StochRSI, MACD, ROC)."""


import numpy as np
import pandas as pd

from app.indicators.trend import compute_ema, rma


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """
    Computes Welles Wilder's Relative Strength Index (RSI).
    Uses Wilder's RMA smoothing for gain and loss.
    """
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)

    avg_gain = rma(gain, period)
    avg_loss = rma(loss, period)

    # Calculate RS
    # When avg_loss is 0, RSI is 100. When avg_gain is 0, RSI is 0.
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))

    # Clean edge cases
    rsi = rsi.where(~(avg_loss == 0.0), 100.0)
    rsi = rsi.where(~(avg_gain == 0.0), 0.0)
    return rsi


def compute_stoch_rsi(
    close: pd.Series,
    rsi_period: int = 14,
    stoch_period: int = 14,
    k_period: int = 3,
    d_period: int = 3,
) -> tuple[pd.Series, pd.Series]:
    """
    Computes Stochastic RSI (%K and %D).
    FastK = (RSI - min(RSI)) / (max(RSI) - min(RSI)) * 100
    %K = SMA(FastK, k_period)
    %D = SMA(%K, d_period)
    """
    rsi = compute_rsi(close, period=rsi_period)
    rsi_min = rsi.rolling(window=stoch_period, min_periods=stoch_period).min()
    rsi_max = rsi.rolling(window=stoch_period, min_periods=stoch_period).max()

    denom = (rsi_max - rsi_min).replace(0.0, np.nan)
    fast_k = ((rsi - rsi_min) / denom) * 100.0
    fast_k = fast_k.fillna(50.0)

    stoch_k = fast_k.rolling(window=k_period, min_periods=k_period).mean()
    stoch_d = stoch_k.rolling(window=d_period, min_periods=d_period).mean()

    return stoch_k, stoch_d


def compute_macd(
    close: pd.Series,
    fast_period: int = 12,
    slow_period: int = 26,
    signal_period: int = 9,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Computes MACD (Moving Average Convergence Divergence).
    MACD Line = Fast EMA - Slow EMA
    Signal Line = EMA of MACD Line
    Histogram = MACD Line - Signal Line
    """
    ema_fast = compute_ema(close, fast_period)
    ema_slow = compute_ema(close, slow_period)
    macd_line = ema_fast - ema_slow
    macd_signal = compute_ema(macd_line, signal_period)
    macd_hist = macd_line - macd_signal

    return macd_line, macd_signal, macd_hist


def compute_roc(close: pd.Series, period: int = 14) -> pd.Series:
    """
    Computes Rate of Change (ROC %):
    ROC = (Close[t] - Close[t-n]) / Close[t-n] * 100
    """
    shift_close = close.shift(period)
    safe_shift = shift_close.replace(0.0, np.nan)
    return ((close - safe_shift) / safe_shift) * 100.0
