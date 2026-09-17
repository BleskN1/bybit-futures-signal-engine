"""Signal Data Models and Type Definitions for deterministic multi-factor scoring."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class SignalStatus(str, Enum):
    IGNORE = "IGNORE"          # Score < 60: filtered out
    WATCH = "WATCH"            # Score 60 - 74: monitor watchlist
    SIGNAL = "SIGNAL"          # Score 75 - 84: standard qualified signal
    STRONG_SIGNAL = "STRONG_SIGNAL"  # Score 85 - 100: high conviction setup


class SignalDirection(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class ComponentScore(BaseModel):
    """
    Score contribution from an individual deterministic analysis component.
    Score range: 0.0 - 100.0 computed independently for LONG and SHORT.
    """

    name: str
    long_score: float = Field(ge=0.0, le=100.0)
    short_score: float = Field(ge=0.0, le=100.0)
    weight: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)
    penalties: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class SignalCandidate(BaseModel):
    """
    Structured signal candidate object representing a fully evaluated,
    deterministic trading setup.

    CRITICAL:
    `score` represents multi-factor heuristic quality alignment (0 - 100).
    It is NOT an empirical or calibrated win probability.
    """

    id: str = Field(default_factory=lambda: uuid4().hex[:16])
    symbol: str
    timestamp: datetime
    as_of_timestamp: int  # Epoch ms of evaluation moment

    direction: Literal["LONG", "SHORT"]

    long_score: float = Field(ge=0.0, le=100.0)
    short_score: float = Field(ge=0.0, le=100.0)
    directional_edge: float = Field(ge=0.0, le=100.0)

    signal_status: SignalStatus
    regime: str

    entry_zone_low: float
    entry_zone_high: float
    current_price: float

    stop_loss: float
    take_profit_1: float
    take_profit_2: float

    risk_reward_tp1: float
    risk_reward_tp2: float

    confidence_score: float | None = Field(
        default=None,
        description="Optional heuristic confidence (NOT a probability). Kept None by default on STEP 4.",
    )

    reason_codes: list[str] = Field(default_factory=list)
    warning_codes: list[str] = Field(default_factory=list)

    component_scores: dict[str, float] = Field(
        default_factory=dict,
        description="Mapping of component_name -> active direction score (0 - 100)",
    )
    component_details: dict[str, ComponentScore] = Field(default_factory=dict)

    timeframe_context: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DiagnosticEvaluation(BaseModel):
    """
    Detailed evaluation record capturing every scoring pass (including IGNORE and WATCH)
    for exhaustive distribution analysis, component benchmarking, and filter audits.
    """

    symbol: str
    as_of: int
    is_ready: bool
    direction: Literal["LONG", "SHORT"]
    long_score: float
    short_score: float
    directional_edge: float
    signal_status: SignalStatus
    regime: str
    component_scores: dict[str, float] = Field(default_factory=dict)
    component_details: dict[str, dict[str, Any]] = Field(default_factory=dict)
    filter_passed: bool = False
    filter_stop_reason: str | None = None
    candidate: SignalCandidate | None = None

