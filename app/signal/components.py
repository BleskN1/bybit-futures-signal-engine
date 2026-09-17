"""Deterministic Component Scorers for Multi-Factor Trading Signal Evaluation.

Each component calculates independent LONG and SHORT scores (0.0 - 100.0)
using only confirmed technical, structural, and derivative features.
"""

from typing import Any

from app.analysis.models import BreakType, MarketRegime, MarketStructureState
from app.signal import explanation as exp
from app.signal.models import ComponentScore
from app.signal.mtf import MTFContext


class HTFTrendScorer:
    """Component 1 (Weight ~15%): 4H and 1H High Timeframe Trend & Directional Context."""

    def __init__(self, weight: float = 0.15):
        self.weight = weight

    def score(self, mtf: MTFContext) -> ComponentScore:
        long_score = 0.0
        short_score = 0.0
        reasons: list[str] = []
        penalties: list[str] = []

        h4_ind = mtf.h4.indicators
        h4_struct = mtf.h4.structure
        h1_ind = mtf.h1.indicators
        h1_struct = mtf.h1.structure

        # 1. 4H EMA Alignment (20/50/100/200)
        if h4_ind:
            if h4_ind.ema_alignment == "BULLISH":
                long_score += 30.0
                reasons.append(exp.HTF_BULLISH_ALIGNMENT)
            elif h4_ind.ema_alignment == "BEARISH":
                short_score += 30.0
                reasons.append(exp.HTF_BEARISH_ALIGNMENT)

            # 4H EMA20 Slope
            if h4_ind.ema_slope_20 is not None:
                if h4_ind.ema_slope_20 > 0.05:
                    long_score += 15.0
                elif h4_ind.ema_slope_20 < -0.05:
                    short_score += 15.0

            # 4H ADX & Directional Movement (+DI vs -DI)
            if h4_ind.adx is not None and h4_ind.adx >= 20.0:
                if (h4_ind.plus_di or 0) > (h4_ind.minus_di or 0):
                    long_score += 15.0
                    reasons.append(exp.HTF_STRONG_ADX_TREND)
                elif (h4_ind.minus_di or 0) > (h4_ind.plus_di or 0):
                    short_score += 15.0
                    reasons.append(exp.HTF_STRONG_ADX_TREND)

        # 2. 4H Market Structure State
        if h4_struct:
            if h4_struct.structure_state == MarketStructureState.BULLISH:
                long_score += 15.0
            elif h4_struct.structure_state == MarketStructureState.BEARISH:
                short_score += 15.0

        # 3. 1H Trend Confirmation
        if h1_ind:
            if h1_ind.ema_alignment == "BULLISH":
                long_score += 15.0
                reasons.append(exp.H1_TREND_CONFIRMATION)
            elif h1_ind.ema_alignment == "BEARISH":
                short_score += 15.0
                reasons.append(exp.H1_TREND_CONFIRMATION)

        if h1_struct:
            if h1_struct.structure_state == MarketStructureState.BULLISH:
                long_score += 10.0
            elif h1_struct.structure_state == MarketStructureState.BEARISH:
                short_score += 10.0

        return ComponentScore(
            name="htf_trend",
            long_score=min(max(long_score, 0.0), 100.0),
            short_score=min(max(short_score, 0.0), 100.0),
            weight=self.weight,
            reasons=list(set(reasons)),
            penalties=list(set(penalties)),
        )


class MarketStructureScorer:
    """Component 2 (Weight ~15%): 1H and 15M Swing Progression, BOS, CHOCH."""

    def __init__(self, weight: float = 0.15):
        self.weight = weight

    def score(self, mtf: MTFContext) -> ComponentScore:
        long_score = 0.0
        short_score = 0.0
        reasons: list[str] = []
        penalties: list[str] = []

        h1_struct = mtf.h1.structure
        m15_struct = mtf.m15.structure

        # 1. 1H Structure State
        if h1_struct:
            if h1_struct.structure_state == MarketStructureState.BULLISH:
                long_score += 30.0
                reasons.append(exp.H1_BULLISH_STRUCTURE)
            elif h1_struct.structure_state == MarketStructureState.BEARISH:
                short_score += 30.0
                reasons.append(exp.H1_BEARISH_STRUCTURE)
            elif h1_struct.structure_state == MarketStructureState.RANGE:
                long_score += 10.0
                short_score += 10.0

        # 2. 15M Setup Structure State & BOS/CHOCH
        if m15_struct:
            if m15_struct.structure_state == MarketStructureState.BULLISH:
                long_score += 25.0
            elif m15_struct.structure_state == MarketStructureState.BEARISH:
                short_score += 25.0

            # Latest Break Event
            if m15_struct.latest_break:
                brk = m15_struct.latest_break.break_type
                if brk == BreakType.BOS_BULLISH:
                    long_score += 25.0
                    reasons.append(exp.BULLISH_BOS)
                elif brk == BreakType.BOS_BEARISH:
                    short_score += 25.0
                    reasons.append(exp.BEARISH_BOS)
                elif brk == BreakType.CHOCH_BULLISH:
                    long_score += 30.0
                    reasons.append(exp.BULLISH_CHOCH)
                elif brk == BreakType.CHOCH_BEARISH:
                    short_score += 30.0
                    reasons.append(exp.BEARISH_CHOCH)

            # Swing Sequence Inspection (HH/HL vs LH/LL)
            swings = m15_struct.recent_swings
            if len(swings) >= 2:
                labels = [s.label for s in swings if s.label]
                if "HH" in labels and "HL" in labels:
                    long_score += 15.0
                    reasons.append(exp.HH_HL_PROGRESSION)
                if "LH" in labels and "LL" in labels:
                    short_score += 15.0
                    reasons.append(exp.LH_LL_PROGRESSION)

        return ComponentScore(
            name="market_structure",
            long_score=min(max(long_score, 0.0), 100.0),
            short_score=min(max(short_score, 0.0), 100.0),
            weight=self.weight,
            reasons=list(set(reasons)),
            penalties=list(set(penalties)),
        )


class LiquidityScorer:
    """Component 3 (Weight ~15%): Buy-Side and Sell-Side Liquidity Sweeps."""

    def __init__(self, weight: float = 0.15):
        self.weight = weight

    def score(self, mtf: MTFContext) -> ComponentScore:
        long_score = 0.0
        short_score = 0.0
        reasons: list[str] = []
        penalties: list[str] = []

        m15_struct = mtf.m15.structure
        m5_struct = mtf.m5.structure

        # 1. 15M Liquidity Sweeps
        if m15_struct and m15_struct.latest_sweep:
            sweep = m15_struct.latest_sweep
            if sweep.sweep_type == "BULLISH_SWEEP":
                long_score += 55.0
                reasons.append(exp.SELL_SIDE_SWEEP)
                if m15_struct.candle_event and m15_struct.candle_event.rejection == "BULLISH_REJECTION":
                    long_score += 25.0
                    reasons.append(exp.BULLISH_REJECTION_POST_SWEEP)
            elif sweep.sweep_type == "BEARISH_SWEEP":
                short_score += 55.0
                reasons.append(exp.BUY_SIDE_SWEEP)
                if m15_struct.candle_event and m15_struct.candle_event.rejection == "BEARISH_REJECTION":
                    short_score += 25.0
                    reasons.append(exp.BEARISH_REJECTION_POST_SWEEP)

        # 2. 5M Liquidity Sweeps (Micro Entry Sweep)
        if m5_struct and m5_struct.latest_sweep:
            sweep = m5_struct.latest_sweep
            if sweep.sweep_type == "BULLISH_SWEEP":
                long_score += 35.0
                reasons.append(exp.SELL_SIDE_SWEEP)
            elif sweep.sweep_type == "BEARISH_SWEEP":
                short_score += 35.0
                reasons.append(exp.BUY_SIDE_SWEEP)

        # 3. Bounce off key swing level without deep pierce
        if m15_struct and m15_struct.last_swing_low:
            curr_close = m15_struct.close
            sl_price = m15_struct.last_swing_low.price
            dist_pct = (curr_close - sl_price) / sl_price if sl_price > 0 else 1.0
            if 0.0 <= dist_pct <= 0.006:
                long_score += 20.0
                reasons.append(exp.KEY_LIQUIDITY_BOUNCE)

        if m15_struct and m15_struct.last_swing_high:
            curr_close = m15_struct.close
            sh_price = m15_struct.last_swing_high.price
            dist_pct = (sh_price - curr_close) / sh_price if sh_price > 0 else 1.0
            if 0.0 <= dist_pct <= 0.006:
                short_score += 20.0
                reasons.append(exp.KEY_LIQUIDITY_BOUNCE)

        # Neutral baseline if no sweep occurred
        if long_score == 0.0 and short_score == 0.0:
            long_score = 30.0
            short_score = 30.0

        return ComponentScore(
            name="liquidity",
            long_score=min(max(long_score, 0.0), 100.0),
            short_score=min(max(short_score, 0.0), 100.0),
            weight=self.weight,
            reasons=list(set(reasons)),
            penalties=list(set(penalties)),
        )


class MomentumScorer:
    """Component 4 (Weight ~10%): RSI, Stoch RSI, MACD & Histogram, ROC."""

    def __init__(self, weight: float = 0.10):
        self.weight = weight

    def score(self, mtf: MTFContext) -> ComponentScore:
        long_score = 0.0
        short_score = 0.0
        reasons: list[str] = []
        penalties: list[str] = []

        m15_ind = mtf.m15.indicators
        if not m15_ind:
            return ComponentScore(
                name="momentum",
                long_score=50.0,
                short_score=50.0,
                weight=self.weight,
            )

        # 1. RSI (14)
        if m15_ind.rsi is not None:
            if 48.0 <= m15_ind.rsi <= 68.0:
                long_score += 25.0
                reasons.append(exp.RSI_BULLISH_MOMENTUM)
            elif 32.0 <= m15_ind.rsi <= 52.0:
                short_score += 25.0
                reasons.append(exp.RSI_BEARISH_MOMENTUM)
            elif m15_ind.rsi > 75.0:
                penalties.append(exp.OPPOSITE_MOMENTUM)
                short_score += 15.0  # Overbought pullback potential
            elif m15_ind.rsi < 25.0:
                penalties.append(exp.OPPOSITE_MOMENTUM)
                long_score += 15.0   # Oversold bounce potential

        # 2. Stoch RSI (%K, %D)
        k, d = m15_ind.stoch_rsi_k, m15_ind.stoch_rsi_d
        if k is not None and d is not None:
            if k > d:
                if k < 80.0:
                    long_score += 25.0
                if k < 30.0:  # Bullish cross in oversold territory
                    long_score += 10.0
                    reasons.append(exp.STOCH_RSI_BULLISH_CROSS)
            elif k < d:
                if k > 20.0:
                    short_score += 25.0
                if k > 70.0:  # Bearish cross in overbought territory
                    short_score += 10.0
                    reasons.append(exp.STOCH_RSI_BEARISH_CROSS)

        # 3. MACD Line & Histogram
        if m15_ind.macd_line is not None and m15_ind.macd_signal is not None:
            if m15_ind.macd_line > m15_ind.macd_signal:
                long_score += 20.0
            else:
                short_score += 20.0

        if m15_ind.macd_hist is not None:
            if m15_ind.macd_hist > 0:
                long_score += 15.0
                reasons.append(exp.MACD_BULLISH_EXPANSION)
            else:
                short_score += 15.0
                reasons.append(exp.MACD_BEARISH_EXPANSION)

        # 4. Rate of Change (ROC 14)
        if m15_ind.roc is not None:
            if m15_ind.roc > 0.1:
                long_score += 15.0
            elif m15_ind.roc < -0.1:
                short_score += 15.0

        return ComponentScore(
            name="momentum",
            long_score=min(max(long_score, 0.0), 100.0),
            short_score=min(max(short_score, 0.0), 100.0),
            weight=self.weight,
            reasons=list(set(reasons)),
            penalties=list(set(penalties)),
        )


class VolumeScorer:
    """Component 5 (Weight ~10%): Volume Ratio, VWAP, OBV & OBV Slope."""

    def __init__(self, weight: float = 0.10):
        self.weight = weight

    def score(self, mtf: MTFContext) -> ComponentScore:
        long_score = 0.0
        short_score = 0.0
        reasons: list[str] = []
        penalties: list[str] = []

        m15_ind = mtf.m15.indicators
        if not m15_ind:
            return ComponentScore(
                name="volume",
                long_score=50.0,
                short_score=50.0,
                weight=self.weight,
            )

        # 1. Volume Ratio vs 20-period SMA
        vol_ratio = m15_ind.volume_ratio or 1.0
        if vol_ratio >= 1.2:
            long_score += 25.0
            short_score += 25.0
            reasons.append(exp.VOLUME_EXPANSION)
        elif vol_ratio < 0.6:
            penalties.append(exp.LOW_VOLUME_WARNING)
            long_score = max(long_score - 10.0, 0.0)
            short_score = max(short_score - 10.0, 0.0)

        # 2. VWAP Alignment
        if m15_ind.vwap and m15_ind.close:
            if m15_ind.close > m15_ind.vwap:
                long_score += 35.0
                reasons.append(exp.PRICE_ABOVE_VWAP)
            else:
                short_score += 35.0
                reasons.append(exp.PRICE_BELOW_VWAP)

        # 3. OBV Slope
        if m15_ind.obv_slope is not None:
            if m15_ind.obv_slope > 0.01:
                long_score += 40.0
                reasons.append(exp.OBV_BULLISH_CONFIRMATION)
            elif m15_ind.obv_slope < -0.01:
                short_score += 40.0
                reasons.append(exp.OBV_BEARISH_CONFIRMATION)
            else:
                long_score += 15.0
                short_score += 15.0

        return ComponentScore(
            name="volume",
            long_score=min(max(long_score, 0.0), 100.0),
            short_score=min(max(short_score, 0.0), 100.0),
            weight=self.weight,
            reasons=list(set(reasons)),
            penalties=list(set(penalties)),
        )


class VolatilityScorer:
    """Component 6 (Weight ~5%): ATR, Bollinger Bandwidth, %B, Market Regime."""

    def __init__(self, weight: float = 0.05):
        self.weight = weight

    def score(self, mtf: MTFContext) -> ComponentScore:
        long_score = 40.0
        short_score = 40.0
        reasons: list[str] = []
        penalties: list[str] = []

        m15_ind = mtf.m15.indicators
        m15_struct = mtf.m15.structure

        if not m15_ind or not m15_struct:
            return ComponentScore(
                name="volatility",
                long_score=50.0,
                short_score=50.0,
                weight=self.weight,
            )

        regime = m15_struct.regime
        if regime == MarketRegime.CONSOLIDATION:
            # Compression setup quality is high for breakouts
            long_score += 25.0
            short_score += 25.0
            reasons.append(exp.VOLATILITY_COMPRESSION_BREAKOUT)
        elif regime == MarketRegime.EXPANSION:
            long_score += 30.0
            short_score += 30.0
            reasons.append(exp.HEALTHY_VOLATILITY_BANDWIDTH)
        elif regime == MarketRegime.TRENDING:
            long_score += 35.0
            short_score += 35.0

        # Bollinger %B Positioning
        pct_b = m15_ind.bb_percent_b
        if pct_b is not None:
            if 0.35 <= pct_b <= 0.85:
                long_score += 20.0
            elif 0.15 <= pct_b <= 0.65:
                short_score += 20.0
            elif pct_b > 1.05:
                penalties.append(exp.EXTREME_VOLATILITY)
                long_score = max(long_score - 15.0, 0.0)
            elif pct_b < -0.05:
                penalties.append(exp.EXTREME_VOLATILITY)
                short_score = max(short_score - 15.0, 0.0)

        return ComponentScore(
            name="volatility",
            long_score=min(max(long_score, 0.0), 100.0),
            short_score=min(max(short_score, 0.0), 100.0),
            weight=self.weight,
            reasons=list(set(reasons)),
            penalties=list(set(penalties)),
        )


class DerivativesScorer:
    """Component 7 (Weight ~15%): Open Interest, Funding Rate, Sentiment."""

    def __init__(
        self,
        weight: float = 0.15,
        freshness_max_age_ms: int = 3600 * 1000,
        stale_penalty: float = 25.0,
    ):
        self.weight = weight
        self.freshness_max_age_ms = freshness_max_age_ms
        self.stale_penalty = stale_penalty

    def score(
        self,
        mtf: MTFContext,
        derivatives_data: dict[str, Any],
        as_of: int,
    ) -> ComponentScore:
        long_score = 45.0
        short_score = 45.0
        reasons: list[str] = []
        penalties: list[str] = []

        history = derivatives_data.get("history", [])
        current_oi = float(derivatives_data.get("open_interest") or 0.0)
        funding_rate = float(derivatives_data.get("funding_rate") or 0.0)

        # 1. Freshness Check
        latest_ts = history[-1]["timestamp"] if history else as_of
        if (as_of - latest_ts) > self.freshness_max_age_ms:
            penalties.append(exp.STALE_DERIVATIVES)
            long_score = max(long_score - self.stale_penalty, 0.0)
            short_score = max(short_score - self.stale_penalty, 0.0)

        # 2. Open Interest Delta & Price Relationship
        if len(history) >= 2:
            prev_oi = float(history[-2].get("open_interest") or current_oi)
            oi_change_pct = (current_oi - prev_oi) / prev_oi if prev_oi > 0 else 0.0

            m15_ind = mtf.m15.indicators
            price_change = m15_ind.roc if (m15_ind and m15_ind.roc is not None) else 0.0

            # Price up + OI up = Long build-up
            if price_change > 0 and oi_change_pct > 0.005:
                long_score += 35.0
                reasons.append(exp.OI_PRICE_CONFIRMATION_LONG)
            # Price down + OI up = Short build-up
            elif price_change < 0 and oi_change_pct > 0.005:
                short_score += 35.0
                reasons.append(exp.OI_PRICE_CONFIRMATION_SHORT)
            # Price up + OI down = Short covering (weaker continuation)
            elif price_change > 0 and oi_change_pct < -0.005:
                long_score += 15.0
            # Price down + OI down = Long liquidation
            elif price_change < 0 and oi_change_pct < -0.005:
                short_score += 15.0

        # 3. Funding Rate Asymmetry
        # Negative funding means shorts are paying longs: bullish sentiment tailwind
        if funding_rate < -0.0001:
            long_score += 25.0
            reasons.append(exp.FUNDING_SUPPORTIVE_LONG)
        elif funding_rate > 0.0005:  # Overheated positive funding
            penalties.append(exp.ELEVATED_FUNDING)
            long_score = max(long_score - 20.0, 0.0)
            short_score += 25.0
            reasons.append(exp.FUNDING_SUPPORTIVE_SHORT)
        else:
            long_score += 15.0
            short_score += 15.0

        return ComponentScore(
            name="derivatives",
            long_score=min(max(long_score, 0.0), 100.0),
            short_score=min(max(short_score, 0.0), 100.0),
            weight=self.weight,
            reasons=list(set(reasons)),
            penalties=list(set(penalties)),
            details={"open_interest": current_oi, "funding_rate": funding_rate},
        )


class PriceActionScorer:
    """Component 8 (Weight ~15%): Rejection Wicks, Engulfing, Candle Geometry."""

    def __init__(self, weight: float = 0.15):
        self.weight = weight

    def score(self, mtf: MTFContext) -> ComponentScore:
        long_score = 0.0
        short_score = 0.0
        reasons: list[str] = []
        penalties: list[str] = []

        m15_struct = mtf.m15.structure
        m5_struct = mtf.m5.structure

        # 1. 15M Candle Events
        if m15_struct and m15_struct.candle_event:
            ev = m15_struct.candle_event
            if ev.rejection == "BULLISH_REJECTION":
                long_score += 45.0
                reasons.append(exp.BULLISH_REJECTION_CANDLE)
            elif ev.rejection == "BEARISH_REJECTION":
                short_score += 45.0
                reasons.append(exp.BEARISH_REJECTION_CANDLE)

            if ev.engulfing == "BULLISH_ENGULFING":
                long_score += 40.0
                reasons.append(exp.BULLISH_ENGULFING_CANDLE)
            elif ev.engulfing == "BEARISH_ENGULFING":
                short_score += 40.0
                reasons.append(exp.BEARISH_ENGULFING_CANDLE)

            # Strong body close near extremes
            if ev.body_ratio > 0.60:
                if ev.lower_wick_ratio < 0.20:
                    long_score += 15.0
                    reasons.append(exp.STRONG_BULLISH_CLOSE)
                elif ev.upper_wick_ratio < 0.20:
                    short_score += 15.0
                    reasons.append(exp.STRONG_BEARISH_CLOSE)

        # 2. 5M Confirmation Candle Events
        if m5_struct and m5_struct.candle_event:
            ev5 = m5_struct.candle_event
            if ev5.rejection == "BULLISH_REJECTION" or ev5.engulfing == "BULLISH_ENGULFING":
                long_score += 25.0
                reasons.append(exp.M5_BULLISH_CONFIRMATION)
            elif ev5.rejection == "BEARISH_REJECTION" or ev5.engulfing == "BEARISH_ENGULFING":
                short_score += 25.0
                reasons.append(exp.M5_BEARISH_CONFIRMATION)

        # Default baseline if no distinct single-bar trigger occurred
        if long_score == 0.0 and short_score == 0.0:
            long_score = 30.0
            short_score = 30.0

        return ComponentScore(
            name="price_action",
            long_score=min(max(long_score, 0.0), 100.0),
            short_score=min(max(short_score, 0.0), 100.0),
            weight=self.weight,
            reasons=list(set(reasons)),
            penalties=list(set(penalties)),
        )
