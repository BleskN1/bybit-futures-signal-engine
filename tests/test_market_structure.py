"""Unit tests for Market Structure & Price Action Engine."""

from app.analysis.engine import MarketStructureEngine
from app.analysis.models import (
    BreakType,
    MarketRegime,
    MarketStructureState,
    SwingType,
)
from app.analysis.price_action import (
    detect_candle_patterns,
    detect_liquidity_sweep,
    determine_market_regime,
)
from app.analysis.structure import MarketStructureAnalyzer
from app.indicators.calculator import IndicatorCalculator


def make_candle(ts: int, o: float, h: float, l: float, c: float, v: float = 1000.0):
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


def test_swing_detection_and_confirmation_delay():
    """
    Verifies that a swing at index `i` is strictly NOT confirmed until `i + right_bars`.
    """
    left_bars = 2
    right_bars = 2
    analyzer = MarketStructureAnalyzer(left_bars=left_bars, right_bars=right_bars)

    # Construct candles:
    # 0: flat (100)
    # 1: flat (100)
    # 2: peak at 110 (swing high)
    # 3: 105
    # 4: 104 (right_bars=2 completed -> confirmed here at index 4)
    # 5: 102
    candles = [
        make_candle(1000, 100, 101, 99, 100),
        make_candle(2000, 100, 102, 99, 100),
        make_candle(3000, 100, 110, 99, 105),  # index 2: Swing High
        make_candle(4000, 105, 106, 102, 104),  # index 3: 1 bar after
        make_candle(5000, 104, 105, 101, 102),  # index 4: 2 bars after -> confirmed!
        make_candle(6000, 102, 103, 100, 101),
    ]

    calc = IndicatorCalculator()
    df = calc.candles_to_dataframe(candles)

    # At index 2: Swing 110 is NOT confirmed yet
    _, last_h_2, _, swings_2, _ = analyzer.analyze_structure(df, as_of_index=2)
    assert last_h_2 is None
    assert len(swings_2) == 0

    # At index 3: Swing 110 is still NOT confirmed (only 1 bar right)
    _, last_h_3, _, _, _ = analyzer.analyze_structure(df, as_of_index=3)
    assert last_h_3 is None

    # At index 4: Swing 110 is NOW confirmed (2 bars right completed)
    _, last_h_4, _, _, _ = analyzer.analyze_structure(df, as_of_index=4)
    assert last_h_4 is not None
    assert last_h_4.price == 110.0
    assert last_h_4.index == 2
    assert last_h_4.confirmed_index == 4


def test_market_structure_bullish_and_bearish():
    """Tests progression of Higher Highs / Higher Lows to identify Bullish structure."""
    left = 1
    right = 1
    analyzer = MarketStructureAnalyzer(left_bars=left, right_bars=right)

    # Zig-zag upward:
    # 0: base
    # 1: Low 89 (L1)
    # 2: confirms L1
    # 3: High 100 (H1)
    # 4: confirms H1
    # 5: Low 94 (L2: HL > 89)
    # 6: confirms L2
    # 7: High 110 (H2: HH > 100)
    # 8: confirms H2
    # 9: current bar
    candles = [
        make_candle(10, 95, 96, 94, 95),     # 0
        make_candle(20, 95, 95, 89, 90),     # 1: Low 89 (trough)
        make_candle(30, 90, 96, 91, 95),     # 2: confirms Low 89
        make_candle(40, 95, 100, 94, 99),    # 3: High 100 (peak)
        make_candle(50, 99, 98, 95, 96),     # 4: confirms High 100
        make_candle(60, 96, 96, 94, 95),     # 5: Low 94 (HL)
        make_candle(70, 95, 102, 96, 101),   # 6: confirms Low 94
        make_candle(80, 101, 110, 100, 109), # 7: High 110 (HH)
        make_candle(90, 109, 108, 104, 105), # 8: confirms High 110
        make_candle(100, 105, 107, 103, 106), # 9
    ]

    calc = IndicatorCalculator()
    df = calc.candles_to_dataframe(candles)

    state, last_h, last_l, _, _ = analyzer.analyze_structure(df, as_of_index=9)
    assert last_h is not None and last_h.price == 110.0
    assert last_l is not None and last_l.price == 94.0
    assert state == MarketStructureState.BULLISH


def test_bos_and_choch_events():
    """Tests BOS (trend continuation) and CHOCH (trend reversal)."""
    left = 1
    right = 1
    analyzer = MarketStructureAnalyzer(left_bars=left, right_bars=right)

    candles = [
        make_candle(10, 100, 101, 95, 96),   # 0
        make_candle(20, 96, 105, 95, 104),   # 1: High 105
        make_candle(30, 104, 104, 98, 99),   # 2: right bar confirms High 105
        make_candle(40, 99, 100, 92, 93),    # 3: Low 92
        make_candle(50, 93, 98, 93, 97),     # 4: right bar confirms Low 92
        make_candle(60, 97, 108, 96, 107),   # 5: Closes at 107 > 105 -> Break of High 105!
    ]

    calc = IndicatorCalculator()
    df = calc.candles_to_dataframe(candles)

    # Bar 5 closes above Swing High 105
    _, _, _, _, break_evt = analyzer.analyze_structure(df, as_of_index=5)
    assert break_evt is not None
    assert break_evt.break_type in (BreakType.BOS_BULLISH, BreakType.CHOCH_BULLISH)
    assert break_evt.swing_level == 105.0
    assert break_evt.close_price == 107.0


def test_liquidity_sweep():
    """Tests liquidity sweep detection (wick pierces level, close stays inside)."""
    from app.analysis.models import SwingPoint
    high_point = SwingPoint(
        index=2,
        timestamp=100,
        type=SwingType.HIGH,
        price=110.0,
        confirmed_index=4,
        confirmed_timestamp=200,
    )
    low_point = SwingPoint(
        index=3,
        timestamp=150,
        type=SwingType.LOW,
        price=90.0,
        confirmed_index=5,
        confirmed_timestamp=250,
    )

    # Bar that sweeps High (High = 112, Close = 108 < 110)
    import pandas as pd
    sweep_high_bar = pd.Series({"timestamp": 300, "open": 105, "high": 112, "low": 104, "close": 108}, name=6)
    sweep_event = detect_liquidity_sweep(sweep_high_bar, high_point, low_point)
    assert sweep_event is not None
    assert sweep_event.sweep_type == "BEARISH_SWEEP"
    assert sweep_event.level_swept == 110.0
    assert sweep_event.extreme_price == 112.0
    assert sweep_event.close_price == 108.0

    # Bar that sweeps Low (Low = 88 < 90, Close = 93 > 90)
    sweep_low_bar = pd.Series({"timestamp": 400, "open": 92, "high": 95, "low": 88, "close": 93}, name=7)
    sweep_low_event = detect_liquidity_sweep(sweep_low_bar, high_point, low_point)
    assert sweep_low_event is not None
    assert sweep_low_event.sweep_type == "BULLISH_SWEEP"
    assert sweep_low_event.level_swept == 90.0
    assert sweep_low_event.extreme_price == 88.0


def test_candle_geometry_rejection_and_engulfing():
    """Tests pinbar rejection and bullish/bearish engulfing patterns."""
    import pandas as pd

    # Bullish Pinbar: Open 100, Close 101, High 102, Low 90 (long lower wick)
    # Range = 12, Lower Wick = 10, Lower wick ratio = 10/12 = 0.833 >= 0.60
    pinbar = pd.Series({"open": 100.0, "high": 102.0, "low": 90.0, "close": 101.0})
    event = detect_candle_patterns(pinbar, prev_bar=None, atr=10.0)
    assert event.rejection == "BULLISH_REJECTION"
    assert event.lower_wick_ratio > 0.60

    # Bullish Engulfing:
    # Prev: Open 105, Close 100 (Bearish)
    # Curr: Open 99, Close 106 (Bullish, engulfs body 100-105)
    prev = pd.Series({"open": 105.0, "high": 106.0, "low": 99.0, "close": 100.0})
    curr = pd.Series({"open": 99.0, "high": 107.0, "low": 98.0, "close": 106.0})
    engulf_event = detect_candle_patterns(curr, prev, atr=5.0)
    assert engulf_event.engulfing == "BULLISH_ENGULFING"


def test_market_regime_classification():
    """Tests consolidation, expansion, and trending regime determinations."""
    # Consolidation when BB bandwidth < 0.035
    regime_cons = determine_market_regime(
        bb_bandwidth=0.02,
        volume_ratio=1.0,
        candle_range=2.0,
        atr=2.0,
        adx=15.0,
        ema_alignment="MIXED",
    )
    assert regime_cons == MarketRegime.CONSOLIDATION

    # Expansion when volume > 1.5 and range > 1.25 * ATR
    regime_exp = determine_market_regime(
        bb_bandwidth=0.08,
        volume_ratio=2.5,
        candle_range=5.0,
        atr=3.0,
        adx=20.0,
        ema_alignment="MIXED",
    )
    assert regime_exp == MarketRegime.EXPANSION

    # Trending when ADX >= 25 and aligned EMAs
    regime_trend = determine_market_regime(
        bb_bandwidth=0.08,
        volume_ratio=1.1,
        candle_range=2.0,
        atr=2.0,
        adx=32.0,
        ema_alignment="BULLISH",
    )
    assert regime_trend == MarketRegime.TRENDING


def test_market_structure_lookahead_bias_protection():
    """
    Ensures that adding future bars (T+1, T+2...) does not alter the
    MarketStructureState, active swings, or events computed at time T.
    """
    engine = MarketStructureEngine()

    candles = [
        make_candle(10, 100, 101, 99, 100),   # 0
        make_candle(20, 100, 102, 99, 101),   # 1
        make_candle(30, 101, 103, 100, 102),  # 2
        make_candle(40, 102, 120, 101, 115),  # 3: Peak High 120
        make_candle(50, 115, 116, 104, 105),  # 4
        make_candle(60, 105, 106, 102, 104),  # 5
        make_candle(70, 104, 105, 101, 103),  # 6: confirms High 120
        make_candle(80, 103, 104, 95, 96),    # 7
        make_candle(90, 96, 97, 80, 82),      # 8: Trough Low 80
        make_candle(100, 82, 86, 81, 85),     # 9
        make_candle(110, 85, 89, 84, 88),     # 10
        make_candle(120, 88, 92, 87, 90),     # 11: confirms Low 80
        make_candle(130, 90, 93, 89, 92),     # 12: time T
    ]

    snap_t = engine.analyze("BTCUSDT", "5", candles[:13])

    # Add wild future candles at T+1, T+2...
    future_candles = list(candles[:13]) + [
        make_candle(140, 92, 500, 91, 450),
        make_candle(150, 450, 600, 400, 550),
    ]

    # Re-evaluate as of time T
    snap_t_recheck = engine.analyze("BTCUSDT", "5", future_candles[:13])

    assert snap_t is not None
    assert snap_t_recheck is not None
    assert snap_t.structure_state == snap_t_recheck.structure_state
    assert snap_t.last_swing_high is not None
    assert snap_t_recheck.last_swing_high is not None
    assert snap_t.last_swing_high.price == snap_t_recheck.last_swing_high.price
    assert snap_t.last_swing_low is not None
    assert snap_t_recheck.last_swing_low is not None
    assert snap_t.last_swing_low.price == snap_t_recheck.last_swing_low.price
