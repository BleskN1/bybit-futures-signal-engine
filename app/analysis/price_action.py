"""Price action patterns: Liquidity sweeps, rejection pinbars, engulfing, market regimes."""

import pandas as pd

from app.analysis.models import (
    LiquiditySweepEvent,
    MarketRegime,
    PriceActionCandleEvent,
    SwingPoint,
)


def detect_liquidity_sweep(
    bar: pd.Series,
    last_swing_high: SwingPoint | None,
    last_swing_low: SwingPoint | None,
) -> LiquiditySweepEvent | None:
    """
    Detects Liquidity Sweeps (Stop Hunts / Turtle Soup):
    - Bearish Sweep: High pierces above prior confirmed swing high, but close finishes below it.
    - Bullish Sweep: Low pierces below prior confirmed swing low, but close finishes above it.
    """
    curr_high = float(bar["high"])
    curr_low = float(bar["low"])
    curr_close = float(bar["close"])
    curr_ts = int(bar["timestamp"])

    # Check Bearish Sweep of Swing High
    if (
        last_swing_high is not None
        and last_swing_high.index < bar.name
        and curr_high > last_swing_high.price
        and curr_close < last_swing_high.price
    ):
        return LiquiditySweepEvent(
            sweep_type="BEARISH_SWEEP",
            timestamp=curr_ts,
            level_swept=last_swing_high.price,
            extreme_price=curr_high,
            close_price=curr_close,
            description=(
                f"Bearish Liquidity Sweep: Wick ran {curr_high:.2f} above Swing High "
                f"{last_swing_high.price:.2f}, closed lower at {curr_close:.2f}"
            ),
        )

    # Check Bullish Sweep of Swing Low
    if (
        last_swing_low is not None
        and last_swing_low.index < bar.name
        and curr_low < last_swing_low.price
        and curr_close > last_swing_low.price
    ):
        return LiquiditySweepEvent(
            sweep_type="BULLISH_SWEEP",
            timestamp=curr_ts,
            level_swept=last_swing_low.price,
            extreme_price=curr_low,
            close_price=curr_close,
            description=(
                f"Bullish Liquidity Sweep: Wick swept {curr_low:.2f} below Swing Low "
                f"{last_swing_low.price:.2f}, closed higher at {curr_close:.2f}"
            ),
        )

    return None


def detect_candle_patterns(
    curr_bar: pd.Series,
    prev_bar: pd.Series | None,
    atr: float | None = None,
    min_wick_ratio: float = 0.60,
    max_body_ratio: float = 0.35,
    min_range_atr: float = 0.80,
    engulf_range_atr: float = 0.50,
) -> PriceActionCandleEvent:
    """
    Evaluates current candle geometry for Rejection Pinbars and Engulfing patterns.
    """
    c_open = float(curr_bar["open"])
    c_high = float(curr_bar["high"])
    c_low = float(curr_bar["low"])
    c_close = float(curr_bar["close"])

    candle_range = c_high - c_low
    if candle_range <= 0.0:
        return PriceActionCandleEvent()

    body = abs(c_close - c_open)
    body_ratio = body / candle_range

    upper_wick = c_high - max(c_open, c_close)
    lower_wick = min(c_open, c_close) - c_low

    upper_wick_ratio = upper_wick / candle_range
    lower_wick_ratio = lower_wick / candle_range

    range_atr_ratio = (candle_range / atr) if (atr and atr > 0) else 1.0

    # 1. Rejection Pinbars
    rejection = None
    has_sufficient_range = (atr is None) or (range_atr_ratio >= min_range_atr)

    if has_sufficient_range and body_ratio <= max_body_ratio:
        if lower_wick_ratio >= min_wick_ratio:
            rejection = "BULLISH_REJECTION"
        elif upper_wick_ratio >= min_wick_ratio:
            rejection = "BEARISH_REJECTION"

    # 2. Engulfing Patterns
    engulfing = None
    if prev_bar is not None:
        p_open = float(prev_bar["open"])
        p_close = float(prev_bar["close"])

        has_engulf_range = (atr is None) or (range_atr_ratio >= engulf_range_atr)
        if has_engulf_range:
            # Bullish Engulfing: Prior candle was bearish, current candle is bullish,
            # and current body engulfs prior body
            if p_close < p_open and c_close > c_open:
                if c_open <= p_close and c_close >= p_open:
                    engulfing = "BULLISH_ENGULFING"

            # Bearish Engulfing: Prior candle was bullish, current candle is bearish,
            # and current body engulfs prior body
            elif (
                p_close > p_open
                and c_close < c_open
                and c_open >= p_close
                and c_close <= p_open
            ):
                engulfing = "BEARISH_ENGULFING"

    return PriceActionCandleEvent(
        rejection=rejection,
        engulfing=engulfing,
        upper_wick_ratio=round(upper_wick_ratio, 4),
        lower_wick_ratio=round(lower_wick_ratio, 4),
        body_ratio=round(body_ratio, 4),
        range_atr_ratio=round(range_atr_ratio, 4),
    )


def determine_market_regime(
    bb_bandwidth: float | None,
    volume_ratio: float | None,
    candle_range: float,
    atr: float | None,
    adx: float | None,
    ema_alignment: str,
    consolidation_bandwidth: float = 0.035,
    expansion_volume_ratio: float = 1.5,
    expansion_atr_ratio: float = 1.25,
) -> MarketRegime:
    """
    Classifies market regime into CONSOLIDATION, EXPANSION, TRENDING, or NORMAL.
    """
    # 1. Consolidation (Volatility compression / squeeze)
    if bb_bandwidth is not None and bb_bandwidth < consolidation_bandwidth:
        return MarketRegime.CONSOLIDATION

    # 2. Expansion (High volume volatility breakout)
    if atr is not None and atr > 0:
        range_ratio = candle_range / atr
        if (
            volume_ratio is not None
            and volume_ratio >= expansion_volume_ratio
            and range_ratio >= expansion_atr_ratio
        ):
            return MarketRegime.EXPANSION

    # 3. Trending
    if adx is not None and adx >= 25.0 and ema_alignment in ("BULLISH", "BEARISH"):
        return MarketRegime.TRENDING

    return MarketRegime.NORMAL
