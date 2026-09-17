# -*- coding: utf-8 -*-
"""
Derivatives analysis module (Open Interest tracking, Funding Rate analysis).
Identifies directional shifts based on Price and Open Interest correlation.
"""

import numpy as np
import pandas as pd


def analyze_oi_dynamics(price: pd.Series, open_interest: pd.Series, window: int = 5) -> pd.Series:
    """
    Classifies Price and Open Interest (OI) co-movement over a specified sliding window.
    
    Returns a Series with the following categorical structural features:
    - PRICE_UP_OI_UP: Long Build-up (Aggressive buyers entering).
    - PRICE_DOWN_OI_UP: Short Build-up (Aggressive sellers entering).
    - PRICE_UP_OI_DOWN: Short Covering (Sellers closing positions, fuel for pump).
    - PRICE_DOWN_OI_DOWN: Long Liquidation (Buyers forced out / capitulating).
    - NEUTRAL: No significant directional shift.
    """
    price_diff = price.diff(window)
    oi_diff = open_interest.diff(window)
    
    # Задаем минимальные пороги изменений, чтобы отсечь рыночный шум (например, изменение OI > 0.5%)
    oi_pct_change = (oi_diff / open_interest.shift(window)) * 100.0
    
    conditions = [
        (price_diff > 0) & (oi_pct_change > 0.5),
        (price_diff < 0) & (oi_pct_change > 0.5),
        (price_diff > 0) & (oi_pct_change < -0.5),
        (price_diff < 0) & (oi_pct_change < -0.5)
    ]
    
    choices = [
        "PRICE_UP_OI_UP",
        "PRICE_DOWN_OI_UP",
        "PRICE_UP_OI_DOWN",
        "PRICE_DOWN_OI_DOWN"
    ]
    
    return pd.Series(np.select(conditions, choices, default="NEUTRAL"), index=price.index)


def evaluate_funding_anomalies(funding_rate: pd.Series, threshold: float = 0.0005) -> pd.Series:
    """
    Identifies high premium/discount conditions from the Funding Rate.
    Standard Bybit base funding is 0.0001 (0.01%).
    
    - EXTREME_PREMIUM: Longs paying heavily (Potential exhaustion / Long squeeze risk).
    - EXTREME_DISCOUNT: Shorts paying heavily (Potential capitulation / Short squeeze risk).
    - NORMAL: Healthy funding distribution.
    """
    conditions = [
        funding_rate >= threshold,
        funding_rate <= -threshold
    ]
    
    choices = [
        "EXTREME_PREMIUM",
        "EXTREME_DISCOUNT"
    ]
    
    return pd.Series(np.select(conditions, choices, default="NORMAL"), index=funding_rate.index)
