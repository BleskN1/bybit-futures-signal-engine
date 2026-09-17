"""Volume and Money Flow indicator calculations (Volume SMA, Ratio, Rolling VWAP, OBV)."""


import numpy as np
import pandas as pd


def compute_volume_metrics(
    volume: pd.Series, sma_period: int = 20
) -> tuple[pd.Series, pd.Series]:
    """
    Computes Volume SMA and Volume Ratio:
    Volume Ratio = Volume / SMA(Volume, period)
    """
    volume_sma = volume.rolling(window=sma_period, min_periods=sma_period).mean()
    safe_sma = volume_sma.replace(0.0, np.nan)
    volume_ratio = volume / safe_sma
    return volume_sma, volume_ratio


def compute_rolling_vwap(
    high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, window: int = 288
) -> pd.Series:
    """
    Computes Rolling VWAP (Volume-Weighted Average Price) over a sliding bar window.
    
    In 24/7 crypto perpetual markets with no exchange open/close bells, rolling VWAP
    (e.g., 288 bars for 24 hours on 5m timeframe, or 24 bars on 1H timeframe)
    provides a stationary, continuous benchmark without arbitrary midnight boundary jumps.

    VWAP = Rolling_Sum(TypicalPrice * Volume) / Rolling_Sum(Volume)
    Typical Price = (High + Low + Close) / 3
    """
    typical_price = (high + low + close) / 3.0
    price_volume = typical_price * volume

    # Rolling window VWAP with minimum periods 1 to prevent early NaN
    rolling_pv = price_volume.rolling(window=window, min_periods=1).sum()
    rolling_vol = volume.rolling(window=window, min_periods=1).sum()

    safe_vol = rolling_vol.replace(0.0, np.nan)
    vwap = rolling_pv / safe_vol
    return vwap


def compute_obv(
    close: pd.Series, volume: pd.Series, slope_n: int = 5
) -> tuple[pd.Series, pd.Series]:
    """
    Computes On-Balance Volume (OBV) and normalized OBV slope.
    
    OBV logic:
    - If Close[t] > Close[t-1]: OBV[t] = OBV[t-1] + Volume[t]
    - If Close[t] < Close[t-1]: OBV[t] = OBV[t-1] - Volume[t]
    - If Close[t] == Close[t-1]: OBV[t] = OBV[t-1]
    
    OBV slope:
    Normalized by 20-period standard deviation of OBV to avoid unbounded drift.
    """
    delta = close.diff()
    direction = pd.Series(
        np.where(delta > 0, 1.0, np.where(delta < 0, -1.0, 0.0)),
        index=close.index,
    )
    # First candle has no diff, direction is 0
    signed_vol = direction * volume
    obv = signed_vol.cumsum()

    # OBV slope normalized by rolling std of OBV
    obv_diff = obv - obv.shift(slope_n)
    obv_std = obv.rolling(window=20, min_periods=5).std(ddof=0).replace(0.0, np.nan)
    obv_slope = obv_diff / obv_std

    return obv, obv_slope
