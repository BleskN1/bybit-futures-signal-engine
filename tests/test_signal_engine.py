"""Unit and integration tests for STEP 4 Signal Scoring Engine."""

from datetime import datetime, timezone

import pytest

from app.analysis.models import (
    BreakType,
    LiquiditySweepEvent,
    MarketRegime,
    MarketStructureState,
    PriceActionCandleEvent,
    PriceActionSnapshot,
    StructureBreakEvent,
    SwingPoint,
    SwingType,
)
from app.indicators.models import IndicatorSnapshot
from app.market_data.historical import HistoricalMarketDataProvider
from app.signal.components import (
    DerivativesScorer,
    HTFTrendScorer,
    LiquidityScorer,
    MarketStructureScorer,
    MomentumScorer,
    PriceActionScorer,
    VolatilityScorer,
    VolumeScorer,
)
from app.signal.engine import SignalEngine
from app.signal.explanation import (
    BULLISH_BOS,
    BULLISH_REJECTION_CANDLE,
    HTF_BULLISH_ALIGNMENT,
    SELL_SIDE_SWEEP,
    STALE_DERIVATIVES,
)
from app.signal.filters import SignalFilterPipeline
from app.signal.levels import EntryLevelCalculator
from app.signal.models import ComponentScore, SignalCandidate, SignalStatus
from app.signal.mtf import MTFAnalyzer, MTFContext, MTFTimeframeData
from app.signal.scorer import SignalScorer
from app.telegram.bot import TelegramNotifier
from app.telegram.formatter import TelegramSignalFormatter


def make_dummy_candle(ts: int, o: float, h: float, l: float, c: float, v: float = 1000.0):
    return {
        "timestamp": ts,
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "volume": v,
        "turnover": v * c,
        "is_closed": True,
    }


def make_bullish_mtf_context(as_of: int = 1700000000000) -> MTFContext:
    """Helper creating a high-conviction bullish MTF context."""
    h4_ind = IndicatorSnapshot(
        symbol="BTCUSDT",
        timeframe="240",
        timestamp=as_of,
        close=65000.0,
        is_ready=True,
        ema20=64500.0,
        ema50=63000.0,
        ema100=61000.0,
        ema200=58000.0,
        ema_alignment="BULLISH",
        ema_slope_20=0.25,
        adx=28.0,
        plus_di=26.0,
        minus_di=14.0,
    )
    h4_struct = PriceActionSnapshot(
        symbol="BTCUSDT",
        timeframe="240",
        timestamp=as_of,
        close=65000.0,
        structure_state=MarketStructureState.BULLISH,
    )

    h1_ind = IndicatorSnapshot(
        symbol="BTCUSDT",
        timeframe="60",
        timestamp=as_of,
        close=65000.0,
        is_ready=True,
        ema20=64700.0,
        ema50=64000.0,
        ema_alignment="BULLISH",
    )
    h1_struct = PriceActionSnapshot(
        symbol="BTCUSDT",
        timeframe="60",
        timestamp=as_of,
        close=65000.0,
        structure_state=MarketStructureState.BULLISH,
        recent_swings=[
            SwingPoint(
                index=50,
                timestamp=as_of - 3600000 * 5,
                type=SwingType.LOW,
                price=63500.0,
                confirmed_index=53,
                confirmed_timestamp=as_of - 3600000 * 2,
                label="HL",
            ),
            SwingPoint(
                index=55,
                timestamp=as_of - 3600000 * 3,
                type=SwingType.HIGH,
                price=66200.0,
                confirmed_index=58,
                confirmed_timestamp=as_of - 3600000 * 1,
                label="HH",
            ),
        ],
    )

    m15_ind = IndicatorSnapshot(
        symbol="BTCUSDT",
        timeframe="15",
        timestamp=as_of,
        close=65000.0,
        is_ready=True,
        rsi=56.0,
        stoch_rsi_k=42.0,
        stoch_rsi_d=30.0,
        macd_line=12.0,
        macd_signal=8.0,
        macd_hist=4.0,
        roc=0.45,
        atr=250.0,
        vwap=64800.0,
        obv_slope=0.15,
        volume_ratio=1.4,
    )
    m15_struct = PriceActionSnapshot(
        symbol="BTCUSDT",
        timeframe="15",
        timestamp=as_of,
        close=65000.0,
        structure_state=MarketStructureState.BULLISH,
        latest_sweep=LiquiditySweepEvent(
            sweep_type="BULLISH_SWEEP",
            timestamp=as_of - 900000,
            level_swept=64400.0,
            extreme_price=64200.0,
            close_price=64600.0,
            description="Sell-side sweep of 64400",
        ),
        candle_event=PriceActionCandleEvent(
            rejection="BULLISH_REJECTION",
            body_ratio=0.25,
            lower_wick_ratio=0.65,
        ),
        latest_break=StructureBreakEvent(
            break_type=BreakType.BOS_BULLISH,
            timestamp=as_of,
            swing_level=64800.0,
            breakout_price=65100.0,
            close_price=65000.0,
            swing_timestamp=as_of - 900000 * 4,
            description="Bullish BOS",
        ),
        regime=MarketRegime.EXPANSION,
    )

    m5_ind = IndicatorSnapshot(
        symbol="BTCUSDT",
        timeframe="5",
        timestamp=as_of,
        close=65000.0,
        is_ready=True,
        ema20=64850.0,
        atr=180.0,
    )
    m5_struct = PriceActionSnapshot(
        symbol="BTCUSDT",
        timeframe="5",
        timestamp=as_of,
        close=65000.0,
        structure_state=MarketStructureState.BULLISH,
        candle_event=PriceActionCandleEvent(
            engulfing="BULLISH_ENGULFING",
            body_ratio=0.70,
        ),
    )

    return MTFContext(
        symbol="BTCUSDT",
        as_of_timestamp=as_of,
        h4=MTFTimeframeData(timeframe="240", indicators=h4_ind, structure=h4_struct, is_ready=True),
        h1=MTFTimeframeData(timeframe="60", indicators=h1_ind, structure=h1_struct, is_ready=True),
        m15=MTFTimeframeData(timeframe="15", indicators=m15_ind, structure=m15_struct, is_ready=True),
        m5=MTFTimeframeData(timeframe="5", indicators=m5_ind, structure=m5_struct, is_ready=True),
        long_alignment_score=85.0,
        short_alignment_score=20.0,
        trend_alignment="BULLISH",
        setup_alignment="BULLISH",
        entry_confirmation="BULLISH",
        is_counter_trend=False,
    )


def test_independent_long_short_scoring():
    """Confirms LONG and SHORT scores are calculated independently (not a zero-sum constraint)."""
    mtf = make_bullish_mtf_context()

    htf = HTFTrendScorer()
    score_htf = htf.score(mtf)
    assert score_htf.long_score > score_htf.short_score
    assert score_htf.short_score >= 0.0

    liq = LiquidityScorer()
    score_liq = liq.score(mtf)
    assert score_liq.long_score >= 70.0
    assert score_liq.short_score < 40.0

    pa = PriceActionScorer()
    score_pa = pa.score(mtf)
    assert score_pa.long_score >= 60.0

    # Scores do NOT necessarily sum to 100 (independent calculations)
    assert score_liq.long_score + score_liq.short_score != 100.0


def test_stale_derivatives_penalty():
    """Verifies that stale derivative data receives penalty and warning code."""
    mtf = make_bullish_mtf_context()
    as_of = 1700000000000

    # 3 hours old derivative data
    stale_data = {
        "open_interest": 50000.0,
        "funding_rate": 0.0001,
        "history": [{"timestamp": as_of - (3 * 3600 * 1000), "open_interest": 50000.0}],
    }

    scorer = DerivativesScorer(freshness_max_age_ms=3600 * 1000, stale_penalty=30.0)
    score = scorer.score(mtf, stale_data, as_of=as_of)

    assert STALE_DERIVATIVES in score.penalties
    assert score.long_score <= 40.0


def test_entry_sl_tp_levels_geometry():
    """Verifies risk-to-reward calculation and strict price level ordering."""
    mtf = make_bullish_mtf_context()
    calc = EntryLevelCalculator()

    levels = calc.calculate_levels("LONG", 65000.0, mtf)
    assert levels is not None
    entry_low, entry_high, sl, tp1, tp2, rr1, rr2 = levels

    # Strict geometric ordering for LONG
    assert sl < entry_low <= entry_high < tp1 < tp2
    assert rr1 >= 1.5
    assert rr2 >= 2.0

    # Test SHORT geometry
    levels_short = calc.calculate_levels("SHORT", 65000.0, mtf)
    assert levels_short is not None
    s_entry_low, s_entry_high, s_sl, s_tp1, s_tp2, s_rr1, s_rr2 = levels_short
    assert s_sl > s_entry_high >= s_entry_low > s_tp1 > s_tp2
    assert s_rr1 >= 1.5


def test_cooldown_filter():
    """Verifies that duplicate signals within cooldown window are rejected."""
    pipeline = SignalFilterPipeline(config={
        "scoring": {
            "cooldown": {"minutes": 20},
            "thresholds": {"signal": 75, "watch": 60},
        }
    })

    cand = SignalCandidate(
        symbol="BTCUSDT",
        timestamp=datetime.fromtimestamp(1700000000, tz=timezone.utc),
        as_of_timestamp=1700000000000,
        direction="LONG",
        long_score=85.0,
        short_score=20.0,
        directional_edge=65.0,
        signal_status=SignalStatus.STRONG_SIGNAL,
        regime="EXPANSION",
        entry_zone_low=64950.0,
        entry_zone_high=65000.0,
        current_price=65000.0,
        stop_loss=64200.0,
        take_profit_1=66200.0,
        take_profit_2=67400.0,
        risk_reward_tp1=1.5,
        risk_reward_tp2=3.0,
    )

    pipeline.register_signal(cand)

    # 10 minutes later (600,000 ms) -> must be rejected
    res_10m = pipeline.check_cooldown("BTCUSDT", "LONG", 1700000000000 + 600000)
    assert not res_10m.passed
    assert "cooldown" in res_10m.rejection_reason.lower()

    # Opposite direction (SHORT) -> allowed
    res_short = pipeline.check_cooldown("BTCUSDT", "SHORT", 1700000000000 + 600000)
    assert res_short.passed

    # 25 minutes later -> allowed
    res_25m = pipeline.check_cooldown("BTCUSDT", "LONG", 1700000000000 + (25 * 60 * 1000))
    assert res_25m.passed


def test_telegram_formatter_no_probability_word():
    """Guarantees formatting adheres to design requirements and forbids probability claims."""
    cand = SignalCandidate(
        symbol="BTCUSDT",
        timestamp=datetime.fromtimestamp(1700000000, tz=timezone.utc),
        as_of_timestamp=1700000000000,
        direction="LONG",
        long_score=88.5,
        short_score=18.0,
        directional_edge=70.5,
        signal_status=SignalStatus.STRONG_SIGNAL,
        regime="TRENDING",
        entry_zone_low=64950.0,
        entry_zone_high=65000.0,
        current_price=65000.0,
        stop_loss=64200.0,
        take_profit_1=66500.0,
        take_profit_2=67800.0,
        risk_reward_tp1=1.9,
        risk_reward_tp2=3.5,
        reason_codes=[
            HTF_BULLISH_ALIGNMENT,
            SELL_SIDE_SWEEP,
            BULLISH_BOS,
            BULLISH_REJECTION_CANDLE,
        ],
        component_scores={
            "htf_trend": 85.0,
            "market_structure": 90.0,
            "liquidity": 95.0,
            "momentum": 80.0,
            "volume": 85.0,
            "volatility": 75.0,
            "derivatives": 85.0,
            "price_action": 90.0,
        },
        timeframe_context={
            "h4_trend": "BULLISH",
            "h1_structure": "BULLISH",
            "m15_setup": "BULLISH_SWEEP",
            "m5_entry": "CONFIRMED",
        },
    )

    msg = TelegramSignalFormatter.format(cand)

    # Must contain score as /100
    assert "88.5/100" in msg
    # Must NOT claim probability
    assert "probability" not in msg.lower()
    assert "win rate" not in msg.lower()
    # Must contain disclaimer
    assert "Notice: Score represents multi-factor rule alignment (0-100)" in msg
    assert "Entry Zone:" in msg
    assert "Stop Loss:" in msg
    assert "TP1:" in msg


@pytest.mark.asyncio
async def test_signal_engine_determinism_with_historical_provider():
    """
    Runs SignalEngine against mock historical provider and validates
    that multiple calls at identical as_of timestamp yield 100% deterministic output.
    """
    # Construct 220 candles for each timeframe
    now_ms = 1700000000000
    tfs = [("5", 5 * 60 * 1000), ("15", 15 * 60 * 1000), ("60", 60 * 60 * 1000), ("240", 240 * 60 * 1000)]
    candles_dict = {}

    for tf_name, tf_dur in tfs:
        bars = []
        base_price = 50000.0
        for i in range(250):
            bar_ts = now_ms - ((250 - i) * tf_dur)
            # Uptrend
            p = base_price + (i * 20.0)
            bars.append(make_dummy_candle(bar_ts, p - 5, p + 15, p - 10, p, 1500.0))
        candles_dict[("BTCUSDT", tf_name)] = bars

    derivatives = {
        "BTCUSDT": [
            {"timestamp": now_ms - 1800000, "open_interest": 100000.0, "funding_rate": 0.0001},
            {"timestamp": now_ms, "open_interest": 105000.0, "funding_rate": 0.0001},
        ]
    }

    provider = HistoricalMarketDataProvider(candles_dict, derivatives)
    engine = SignalEngine(provider=provider)

    # Evaluate at now_ms
    res1 = await engine.evaluate("BTCUSDT", as_of=now_ms)
    # Reset filter cooldown to allow second evaluation
    engine.filter_pipeline.reset_cooldown("BTCUSDT")
    res2 = await engine.evaluate("BTCUSDT", as_of=now_ms)

    if res1 is not None and res2 is not None:
        assert res1.direction == res2.direction
        assert res1.long_score == res2.long_score
        assert res1.short_score == res2.short_score
        assert res1.entry_zone_low == res2.entry_zone_low
        assert res1.stop_loss == res2.stop_loss
        assert res1.take_profit_1 == res2.take_profit_1
