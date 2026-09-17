"""Multi-Timeframe (MTF) Context Analyzer ensuring strict temporal alignment and no lookahead."""

from dataclasses import dataclass, field
from typing import Any

from app.analysis.engine import MarketStructureEngine
from app.analysis.models import MarketStructureState, PriceActionSnapshot
from app.indicators.calculator import IndicatorCalculator
from app.indicators.models import IndicatorSnapshot
from app.market_data.provider import MarketDataProvider
from app.signal import explanation as exp


TIMEFRAME_DURATIONS_MS: dict[str, int] = {
    "5": 5 * 60 * 1000,
    "15": 15 * 60 * 1000,
    "60": 60 * 60 * 1000,
    "240": 240 * 60 * 1000,
    "D": 24 * 60 * 60 * 1000,
}


@dataclass
class MTFTimeframeData:
    """Holds indicators and price action snapshot for a single timeframe."""
    timeframe: str
    indicators: IndicatorSnapshot | None = None
    structure: PriceActionSnapshot | None = None
    candles_count: int = 0
    is_ready: bool = False
    last_closed_ts: int | None = None


@dataclass
class MTFContext:
    """
    Unified Multi-Timeframe Context.
    Roles:
    - 4H (240): Global Context
    - 1H (60): Market Structure
    - 15M (15): Setup
    - 5M (5): Entry Confirmation
    """
    symbol: str
    as_of_timestamp: int
    h4: MTFTimeframeData
    h1: MTFTimeframeData
    m15: MTFTimeframeData
    m5: MTFTimeframeData

    long_alignment_score: float = 0.0
    short_alignment_score: float = 0.0

    trend_alignment: str = "NEUTRAL"      # BULLISH | BEARISH | CONFLICTED | NEUTRAL
    setup_alignment: str = "NEUTRAL"      # BULLISH | BEARISH | NEUTRAL
    entry_confirmation: str = "NEUTRAL"   # BULLISH | BEARISH | NEUTRAL
    is_counter_trend: bool = False

    reasons: list[str] = field(default_factory=list)
    penalties: list[str] = field(default_factory=list)

    @property
    def is_ready(self) -> bool:
        """True if all 4 timeframes met minimum warmup and calculated indicators."""
        return (
            self.h4.is_ready
            and self.h1.is_ready
            and self.m15.is_ready
            and self.m5.is_ready
        )


class MTFAnalyzer:
    """
    Orchestrates multi-timeframe indicator and market structure calculation
    with mathematical guarantees against lookahead bias.
    """

    def __init__(
        self,
        indicator_calc: IndicatorCalculator | None = None,
        structure_engine: MarketStructureEngine | None = None,
        min_warmup_bars: int = 200,
    ):
        self.calc = indicator_calc or IndicatorCalculator(config={"warmup_bars": min_warmup_bars})
        self.structure_engine = structure_engine or MarketStructureEngine()
        self.min_warmup_bars = min_warmup_bars

    def filter_closed_bars(
        self,
        candles: list[dict[str, Any]],
        timeframe: str,
        as_of: int,
    ) -> list[dict[str, Any]]:
        """
        Guarantees that only candles completely closed at or before `as_of` are considered.
        A candle starting at timestamp T with duration D closes at T + D.
        Only bars where T + D <= as_of are returned.
        """
        duration = TIMEFRAME_DURATIONS_MS.get(timeframe, 0)
        closed_bars = []
        for c in candles:
            # Rule 3: Unfinished/forming candles must NEVER enter the signal engine
            if not c.get("is_closed", True):
                continue

            ts = c["timestamp"]
            # If bar has duration, candle must finish at or before as_of
            if duration > 0:
                if ts + duration <= as_of:
                    closed_bars.append(c)
            else:
                if ts <= as_of:
                    closed_bars.append(c)
        return closed_bars

    def analyze(
        self,
        symbol: str,
        provider: MarketDataProvider,
        as_of: int,
    ) -> MTFContext:
        """
        Builds MTFContext strictly using closed candles as of `as_of` timestamp.
        """
        tf_data_map: dict[str, MTFTimeframeData] = {}

        for tf in ["240", "60", "15", "5"]:
            raw_candles = provider.get_candles(symbol, tf, limit=300, as_of=as_of)
            closed_candles = self.filter_closed_bars(raw_candles, tf, as_of=as_of)

            ind_snap: IndicatorSnapshot | None = None
            struct_snap: PriceActionSnapshot | None = None
            is_ready = False
            last_ts: int | None = None

            if closed_candles:
                last_ts = closed_candles[-1]["timestamp"]
                ind_snap = self.calc.compute_all(symbol, tf, closed_candles)
                struct_snap = self.structure_engine.analyze(
                    symbol, tf, closed_candles, indicator_snapshot=ind_snap
                )
                is_ready = ind_snap.is_ready if ind_snap else False

            tf_data_map[tf] = MTFTimeframeData(
                timeframe=tf,
                indicators=ind_snap,
                structure=struct_snap,
                candles_count=len(closed_candles),
                is_ready=is_ready,
                last_closed_ts=last_ts,
            )

        h4 = tf_data_map["240"]
        h1 = tf_data_map["60"]
        m15 = tf_data_map["15"]
        m5 = tf_data_map["5"]

        # Evaluate cross-timeframe alignment
        long_align, short_align, trend_align, setup_align, entry_conf, is_counter, reasons, penalties = (
            self._evaluate_alignment(h4, h1, m15, m5)
        )

        return MTFContext(
            symbol=symbol,
            as_of_timestamp=as_of,
            h4=h4,
            h1=h1,
            m15=m15,
            m5=m5,
            long_alignment_score=long_align,
            short_alignment_score=short_align,
            trend_alignment=trend_align,
            setup_alignment=setup_align,
            entry_confirmation=entry_conf,
            is_counter_trend=is_counter,
            reasons=reasons,
            penalties=penalties,
        )

    def _evaluate_alignment(
        self,
        h4: MTFTimeframeData,
        h1: MTFTimeframeData,
        m15: MTFTimeframeData,
        m5: MTFTimeframeData,
    ) -> tuple[float, float, str, str, str, bool, list[str], list[str]]:
        """
        Scores cross-timeframe harmony for LONG and SHORT independently.
        """
        long_points = 0.0
        short_points = 0.0
        reasons: list[str] = []
        penalties: list[str] = []

        # 1. Global Context (4H)
        h4_bull = False
        h4_bear = False
        if h4.indicators:
            if h4.indicators.ema_alignment == "BULLISH":
                long_points += 25.0
                h4_bull = True
            elif h4.indicators.ema_alignment == "BEARISH":
                short_points += 25.0
                h4_bear = True

            if h4.indicators.ema_slope_20 and h4.indicators.ema_slope_20 > 0:
                long_points += 10.0
            elif h4.indicators.ema_slope_20 and h4.indicators.ema_slope_20 < 0:
                short_points += 10.0

        if h4.structure:
            if h4.structure.structure_state == MarketStructureState.BULLISH:
                long_points += 15.0
            elif h4.structure.structure_state == MarketStructureState.BEARISH:
                short_points += 15.0

        # 2. Intermediate Market Structure (1H)
        h1_bull = False
        h1_bear = False
        if h1.structure:
            if h1.structure.structure_state == MarketStructureState.BULLISH:
                long_points += 20.0
                h1_bull = True
            elif h1.structure.structure_state == MarketStructureState.BEARISH:
                short_points += 20.0
                h1_bear = True

        if h1.indicators:
            if h1.indicators.ema_alignment == "BULLISH":
                long_points += 10.0
            elif h1.indicators.ema_alignment == "BEARISH":
                short_points += 10.0

        # Trend alignment synthesis
        if h4_bull and h1_bull:
            trend_align = "BULLISH"
            reasons.append(exp.HTF_BULLISH_ALIGNMENT)
            reasons.append(exp.H1_BULLISH_STRUCTURE)
        elif h4_bear and h1_bear:
            trend_align = "BEARISH"
            reasons.append(exp.HTF_BEARISH_ALIGNMENT)
            reasons.append(exp.H1_BEARISH_STRUCTURE)
        elif (h4_bull and h1_bear) or (h4_bear and h1_bull):
            trend_align = "CONFLICTED"
        else:
            trend_align = "NEUTRAL"

        # 3. Setup Timeframe (15M)
        setup_align = "NEUTRAL"
        if m15.structure:
            if m15.structure.structure_state == MarketStructureState.BULLISH:
                long_points += 10.0
                setup_align = "BULLISH"
            elif m15.structure.structure_state == MarketStructureState.BEARISH:
                short_points += 10.0
                setup_align = "BEARISH"

            if m15.structure.latest_sweep:
                if m15.structure.latest_sweep.sweep_type == "BULLISH_SWEEP":
                    long_points += 15.0
                    setup_align = "BULLISH"
                elif m15.structure.latest_sweep.sweep_type == "BEARISH_SWEEP":
                    short_points += 15.0
                    setup_align = "BEARISH"

        # 4. Entry Confirmation (5M)
        entry_conf = "NEUTRAL"
        if m5.indicators and m5.structure:
            if (
                m5.indicators.close > (m5.indicators.ema20 or 0)
                and m5.structure.structure_state != MarketStructureState.BEARISH
            ):
                long_points += 10.0
                entry_conf = "BULLISH"
                reasons.append(exp.M5_BULLISH_CONFIRMATION)
            elif (
                m5.indicators.close < (m5.indicators.ema20 or float("inf"))
                and m5.structure.structure_state != MarketStructureState.BULLISH
            ):
                short_points += 10.0
                entry_conf = "BEARISH"
                reasons.append(exp.M5_BEARISH_CONFIRMATION)

        # Counter-trend detection
        is_counter = False
        if trend_align == "BEARISH" and (setup_align == "BULLISH" or entry_conf == "BULLISH"):
            is_counter = True
            penalties.append(exp.COUNTER_TREND)
            long_points *= 0.75  # 25% alignment haircut
        elif trend_align == "BULLISH" and (setup_align == "BEARISH" or entry_conf == "BEARISH"):
            is_counter = True
            penalties.append(exp.COUNTER_TREND)
            short_points *= 0.75  # 25% alignment haircut

        long_score = min(max(long_points, 0.0), 100.0)
        short_score = min(max(short_points, 0.0), 100.0)

        return (
            long_score,
            short_score,
            trend_align,
            setup_align,
            entry_conf,
            is_counter,
            reasons,
            penalties,
        )
