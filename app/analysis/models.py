"""Data models and Enums for Market Structure and Price Action Analysis."""

from enum import Enum

from pydantic import BaseModel, Field


class SwingType(str, Enum):
    HIGH = "HIGH"
    LOW = "LOW"


class MarketStructureState(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    RANGE = "RANGE"
    UNKNOWN = "UNKNOWN"


class BreakType(str, Enum):
    BOS_BULLISH = "BOS_BULLISH"
    BOS_BEARISH = "BOS_BEARISH"
    CHOCH_BULLISH = "CHOCH_BULLISH"
    CHOCH_BEARISH = "CHOCH_BEARISH"


class MarketRegime(str, Enum):
    CONSOLIDATION = "CONSOLIDATION"
    EXPANSION = "EXPANSION"
    TRENDING = "TRENDING"
    NORMAL = "NORMAL"


class SwingPoint(BaseModel):
    """
    Confirmed pivot swing point.
    Strictly look-ahead-bias protected:
    A swing formed at index `i` is ONLY confirmed and usable at index `confirmed_index` = i + right_bars.
    """

    index: int
    timestamp: int
    type: SwingType
    price: float
    confirmed_index: int
    confirmed_timestamp: int
    is_broken: bool = False
    broken_timestamp: int | None = None
    label: str | None = Field(
        default=None,
        description="HH (Higher High), LH (Lower High), HL (Higher Low), LL (Lower Low)",
    )


class StructureBreakEvent(BaseModel):
    """Details of a BOS (Break of Structure) or CHOCH (Change of Character)."""

    break_type: BreakType
    timestamp: int
    swing_level: float
    breakout_price: float
    close_price: float
    swing_timestamp: int
    description: str


class LiquiditySweepEvent(BaseModel):
    """
    Liquidity sweep (Turtle Soup / Stop Run):
    A wick pierces a prior swing level but the candle closes back inside the range.
    """

    sweep_type: str = Field(description="BULLISH_SWEEP (swept low) | BEARISH_SWEEP (swept high)")
    timestamp: int
    level_swept: float
    extreme_price: float
    close_price: float
    description: str


class PriceActionCandleEvent(BaseModel):
    """Candle-level price action features (Rejection pinbar, Engulfing)."""

    rejection: str | None = Field(
        default=None,
        description="BULLISH_REJECTION | BEARISH_REJECTION | None",
    )
    engulfing: str | None = Field(
        default=None,
        description="BULLISH_ENGULFING | BEARISH_ENGULFING | None",
    )
    upper_wick_ratio: float = 0.0
    lower_wick_ratio: float = 0.0
    body_ratio: float = 0.0
    range_atr_ratio: float = 0.0


class PriceActionSnapshot(BaseModel):
    """Unified snapshot of market structure and price action for a timeframe."""

    symbol: str
    timeframe: str
    timestamp: int
    close: float
    structure_state: MarketStructureState = MarketStructureState.UNKNOWN
    last_swing_high: SwingPoint | None = None
    last_swing_low: SwingPoint | None = None
    recent_swings: list[SwingPoint] = Field(default_factory=list)
    latest_break: StructureBreakEvent | None = None
    latest_sweep: LiquiditySweepEvent | None = None
    candle_event: PriceActionCandleEvent | None = None
    regime: MarketRegime = MarketRegime.NORMAL
    bb_bandwidth: float | None = None
