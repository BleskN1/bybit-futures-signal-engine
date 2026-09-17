"""Standardized structured reason codes and explanation mappings for Signal Scoring."""

# HTF Trend Reasons
HTF_BULLISH_ALIGNMENT = "HTF_BULLISH_ALIGNMENT"
HTF_BEARISH_ALIGNMENT = "HTF_BEARISH_ALIGNMENT"
HTF_STRONG_ADX_TREND = "HTF_STRONG_ADX_TREND"
H1_TREND_CONFIRMATION = "H1_TREND_CONFIRMATION"

# Market Structure Reasons
H1_BULLISH_STRUCTURE = "H1_BULLISH_STRUCTURE"
H1_BEARISH_STRUCTURE = "H1_BEARISH_STRUCTURE"
BULLISH_BOS = "BULLISH_BOS"
BEARISH_BOS = "BEARISH_BOS"
BULLISH_CHOCH = "BULLISH_CHOCH"
BEARISH_CHOCH = "BEARISH_CHOCH"
HH_HL_PROGRESSION = "HH_HL_PROGRESSION"
LH_LL_PROGRESSION = "LH_LL_PROGRESSION"

# Liquidity Reasons
SELL_SIDE_SWEEP = "SELL_SIDE_SWEEP"
BUY_SIDE_SWEEP = "BUY_SIDE_SWEEP"
BULLISH_REJECTION_POST_SWEEP = "BULLISH_REJECTION_POST_SWEEP"
BEARISH_REJECTION_POST_SWEEP = "BEARISH_REJECTION_POST_SWEEP"
KEY_LIQUIDITY_BOUNCE = "KEY_LIQUIDITY_BOUNCE"

# Momentum Reasons
RSI_BULLISH_MOMENTUM = "RSI_BULLISH_MOMENTUM"
RSI_BEARISH_MOMENTUM = "RSI_BEARISH_MOMENTUM"
STOCH_RSI_BULLISH_CROSS = "STOCH_RSI_BULLISH_CROSS"
STOCH_RSI_BEARISH_CROSS = "STOCH_RSI_BEARISH_CROSS"
MACD_BULLISH_EXPANSION = "MACD_BULLISH_EXPANSION"
MACD_BEARISH_EXPANSION = "MACD_BEARISH_EXPANSION"

# Volume Reasons
VOLUME_EXPANSION = "VOLUME_EXPANSION"
PRICE_ABOVE_VWAP = "PRICE_ABOVE_VWAP"
PRICE_BELOW_VWAP = "PRICE_BELOW_VWAP"
OBV_BULLISH_CONFIRMATION = "OBV_BULLISH_CONFIRMATION"
OBV_BEARISH_CONFIRMATION = "OBV_BEARISH_CONFIRMATION"

# Volatility Reasons
VOLATILITY_COMPRESSION_BREAKOUT = "VOLATILITY_COMPRESSION_BREAKOUT"
HEALTHY_VOLATILITY_BANDWIDTH = "HEALTHY_VOLATILITY_BANDWIDTH"

# Derivatives Reasons
OI_PRICE_CONFIRMATION_LONG = "OI_PRICE_CONFIRMATION_LONG"
OI_PRICE_CONFIRMATION_SHORT = "OI_PRICE_CONFIRMATION_SHORT"
FUNDING_SUPPORTIVE_LONG = "FUNDING_SUPPORTIVE_LONG"
FUNDING_SUPPORTIVE_SHORT = "FUNDING_SUPPORTIVE_SHORT"

# Price Action / Confirmation Reasons
BULLISH_REJECTION_CANDLE = "BULLISH_REJECTION_CANDLE"
BEARISH_REJECTION_CANDLE = "BEARISH_REJECTION_CANDLE"
BULLISH_ENGULFING_CANDLE = "BULLISH_ENGULFING_CANDLE"
BEARISH_ENGULFING_CANDLE = "BEARISH_ENGULFING_CANDLE"
M5_BULLISH_CONFIRMATION = "M5_BULLISH_CONFIRMATION"
M5_BEARISH_CONFIRMATION = "M5_BEARISH_CONFIRMATION"
STRONG_BULLISH_CLOSE = "STRONG_BULLISH_CLOSE"
STRONG_BEARISH_CLOSE = "STRONG_BEARISH_CLOSE"

# Negative / Penalty Warning Codes
LOW_RR = "LOW_RR"
CHOPPY_REGIME = "CHOPPY_REGIME"
COUNTER_TREND = "COUNTER_TREND"
ELEVATED_FUNDING = "ELEVATED_FUNDING"
STALE_DERIVATIVES = "STALE_DERIVATIVES"
LOW_VOLUME_WARNING = "LOW_VOLUME_WARNING"
EXTREME_VOLATILITY = "EXTREME_VOLATILITY"
OPPOSITE_MOMENTUM = "OPPOSITE_MOMENTUM"


HUMAN_REASON_LABELS: dict[str, str] = {
    HTF_BULLISH_ALIGNMENT: "4H Bullish EMA alignment",
    HTF_BEARISH_ALIGNMENT: "4H Bearish EMA alignment",
    HTF_STRONG_ADX_TREND: "4H Strong ADX trend confirmation",
    H1_TREND_CONFIRMATION: "1H Trend confirmation",
    H1_BULLISH_STRUCTURE: "1H Bullish HH/HL market structure",
    H1_BEARISH_STRUCTURE: "1H Bearish LH/LL market structure",
    BULLISH_BOS: "Bullish Break of Structure (BOS)",
    BEARISH_BOS: "Bearish Break of Structure (BOS)",
    BULLISH_CHOCH: "Bullish Change of Character (CHOCH)",
    BEARISH_CHOCH: "Bearish Change of Character (CHOCH)",
    HH_HL_PROGRESSION: "Confirmed HH & HL progression",
    LH_LL_PROGRESSION: "Confirmed LH & LL progression",
    SELL_SIDE_SWEEP: "Sell-side liquidity sweep & reclaim",
    BUY_SIDE_SWEEP: "Buy-side liquidity sweep & reclaim",
    BULLISH_REJECTION_POST_SWEEP: "Bullish rejection wick after sweep",
    BEARISH_REJECTION_POST_SWEEP: "Bearish rejection wick after sweep",
    KEY_LIQUIDITY_BOUNCE: "Bounce off key swing liquidity level",
    RSI_BULLISH_MOMENTUM: "RSI bullish momentum acceleration",
    RSI_BEARISH_MOMENTUM: "RSI bearish momentum acceleration",
    STOCH_RSI_BULLISH_CROSS: "Stoch RSI bullish crossover",
    STOCH_RSI_BEARISH_CROSS: "Stoch RSI bearish crossover",
    MACD_BULLISH_EXPANSION: "MACD bullish histogram expansion",
    MACD_BEARISH_EXPANSION: "MACD bearish histogram expansion",
    VOLUME_EXPANSION: "Volume expansion > 1.2x SMA20",
    PRICE_ABOVE_VWAP: "Price holding above session VWAP",
    PRICE_BELOW_VWAP: "Price holding below session VWAP",
    OBV_BULLISH_CONFIRMATION: "OBV uptrend confirming price advance",
    OBV_BEARISH_CONFIRMATION: "OBV downtrend confirming price drop",
    VOLATILITY_COMPRESSION_BREAKOUT: "Volatility compression into breakout",
    HEALTHY_VOLATILITY_BANDWIDTH: "Healthy Bollinger bandwidth",
    OI_PRICE_CONFIRMATION_LONG: "Open interest rising alongside price (Aggressive Longs)",
    OI_PRICE_CONFIRMATION_SHORT: "Open interest rising as price drops (Aggressive Shorts)",
    FUNDING_SUPPORTIVE_LONG: "Funding rate supportive for long",
    FUNDING_SUPPORTIVE_SHORT: "Funding rate supportive for short",
    BULLISH_REJECTION_CANDLE: "Bullish rejection pinbar candle",
    BEARISH_REJECTION_CANDLE: "Bearish rejection pinbar candle",
    BULLISH_ENGULFING_CANDLE: "Bullish engulfing price action",
    BEARISH_ENGULFING_CANDLE: "Bearish engulfing price action",
    M5_BULLISH_CONFIRMATION: "5M Bullish entry confirmation",
    M5_BEARISH_CONFIRMATION: "5M Bearish entry confirmation",
    STRONG_BULLISH_CLOSE: "Strong candle close near high",
    STRONG_BEARISH_CLOSE: "Strong candle close near low",
    # Warnings
    LOW_RR: "Low risk-to-reward ratio for setup",
    CHOPPY_REGIME: "Choppy market regime detected",
    COUNTER_TREND: "Counter-trend setup (against 4H/1H global context)",
    ELEVATED_FUNDING: "Elevated funding rate (potential crowded trade)",
    STALE_DERIVATIVES: "Derivatives metrics are stale or lagging",
    LOW_VOLUME_WARNING: "Breakout lacks strong volume confirmation",
    EXTREME_VOLATILITY: "Extreme volatility conditions (wide ATR)",
    OPPOSITE_MOMENTUM: "Momentum indicators in opposing direction",
}


def format_reason(code: str) -> str:
    """Returns human-readable text for a reason code."""
    return HUMAN_REASON_LABELS.get(code, code.replace("_", " ").title())
