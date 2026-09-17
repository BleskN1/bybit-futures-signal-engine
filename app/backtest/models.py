"""Data models and type definitions for historical backtest simulation and metrics."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


class TradeState(str, Enum):
    WAITING_FOR_ENTRY = "WAITING_FOR_ENTRY"
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class TradeOutcome(str, Enum):
    STOP_LOSS = "STOP_LOSS"
    TP1_ONLY = "TP1_ONLY"
    TP2 = "TP2"
    EXPIRED = "EXPIRED"


class TradeRecord(BaseModel):
    """
    Detailed trade audit record tracking lifecycle, execution prices,
    costs, risk-normalized returns, and excursion excursions.
    """

    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    symbol: str
    direction: Literal["LONG", "SHORT"]
    signal_id: str
    signal_time: int  # Epoch ms
    signal_score: float
    component_scores: dict[str, float] = Field(default_factory=dict)
    regime: str
    reason_codes: list[str] = Field(default_factory=list)

    state: TradeState = TradeState.WAITING_FOR_ENTRY
    entry_zone_low: float
    entry_zone_high: float
    entry_time: int | None = None
    entry_price: float | None = None

    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    risk_reward_tp1: float
    risk_reward_tp2: float

    exit_time: int | None = None
    exit_price: float | None = None
    exit_reason: str | None = None
    outcome: TradeOutcome | None = None

    initial_risk: float = 0.0  # |entry - SL|
    gross_r: float = 0.0
    fee_cost_r: float = 0.0
    slippage_cost_r: float = 0.0
    funding_cost_r: float = 0.0
    net_r: float = 0.0

    mfe_price: float = 0.0
    mfe_r: float = 0.0
    mfe_pct: float = 0.0

    mae_price: float = 0.0
    mae_r: float = 0.0
    mae_pct: float = 0.0

    holding_time_minutes: float = 0.0
    ambiguous_candle: bool = False


class EquityPoint(BaseModel):
    """Equity and drawdown trajectory point."""

    trade_index: int
    timestamp: int
    trade_id: str
    symbol: str
    net_r: float
    cumulative_r: float
    peak_r: float
    drawdown_r: float


class ScoreBucketMetrics(BaseModel):
    """Performance metrics stratified by discrete signal score intervals."""

    bucket: str  # e.g. "60–64", "65–69", "70–74", "75–79", "80–84", "85–89", "90–100"
    trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    average_r: float = 0.0
    expectancy: float = 0.0
    profit_factor: float = 0.0
    total_r: float = 0.0


class SubgroupMetrics(BaseModel):
    """Categorical performance breakdown (e.g. Regime or Direction)."""

    group: str
    trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    average_r: float = 0.0
    expectancy: float = 0.0
    profit_factor: float = 0.0
    total_r: float = 0.0


class BacktestMetrics(BaseModel):
    """Aggregate quantitative backtesting report."""

    # Dataset & Evaluation Counts
    start_time: int
    end_time: int
    duration_days: float
    symbols: list[str]
    total_evaluations: int = 0
    signals_generated: int = 0
    signal_count: int = 0
    strong_signal_count: int = 0

    # Trade Execution Counts
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    breakeven_trades: int = 0
    win_rate: float = 0.0

    # Risk-Normalized Results
    average_r: float = 0.0
    median_r: float = 0.0
    total_r: float = 0.0
    expectancy: float = 0.0
    profit_factor: float = 0.0
    max_drawdown_r: float = 0.0
    average_drawdown_r: float = 0.0
    largest_win_r: float = 0.0
    largest_loss_r: float = 0.0
    average_holding_time_minutes: float = 0.0
    max_holding_time_minutes: float = 0.0
    max_losing_streak: int = 0

    # Financial & Cost Breakdown (in R units)
    gross_pnl_r: float = 0.0
    fees_r: float = 0.0
    funding_r: float = 0.0
    slippage_r: float = 0.0
    net_pnl_r: float = 0.0

    # Detailed Categorical Breakdown
    score_buckets: list[ScoreBucketMetrics] = Field(default_factory=list)
    regimes: list[SubgroupMetrics] = Field(default_factory=list)
    directions: list[SubgroupMetrics] = Field(default_factory=list)
    equity_curve: list[EquityPoint] = Field(default_factory=list)
