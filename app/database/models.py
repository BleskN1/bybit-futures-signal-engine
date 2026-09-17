"""SQLAlchemy models for persistent market data, signals, and paper tracking."""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class SymbolModel(Base):
    """Monitored trading instruments."""

    __tablename__ = "symbols"

    symbol = Column(String(32), primary_key=True)
    status = Column(String(16), nullable=False, default="Trading")
    volume_24h = Column(Float, nullable=True, default=0.0)
    turnover_24h = Column(Float, nullable=True, default=0.0)
    open_interest = Column(Float, nullable=True, default=0.0)
    volatility = Column(Float, nullable=True, default=0.0)
    rank = Column(Integer, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class CandleModel(Base):
    """Multi-timeframe candlestick bars."""

    __tablename__ = "candles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(32), nullable=False, index=True)
    timeframe = Column(String(8), nullable=False, index=True)  # 5, 15, 60, 240
    timestamp = Column(Integer, nullable=False, index=True)     # Epoch ms
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)
    turnover = Column(Float, nullable=True, default=0.0)
    is_closed = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint("symbol", "timeframe", "timestamp", name="uq_candle_bar"),
        Index("idx_candles_lookup", "symbol", "timeframe", "timestamp"),
    )


class DerivativeModel(Base):
    """Historical derivative metrics (raw open interest, funding, LS ratio)."""

    __tablename__ = "derivatives"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(32), nullable=False, index=True)
    timestamp = Column(Integer, nullable=False, index=True)     # Epoch ms
    open_interest = Column(Float, nullable=False)               # Raw Open Interest value
    funding_rate = Column(Float, nullable=True)
    long_short_ratio = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_derivatives_lookup", "symbol", "timestamp"),
    )


class FeatureModel(Base):
    """Calculated technical & price action features for statistical analysis & ML."""

    __tablename__ = "features"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(32), nullable=False, index=True)
    timeframe = Column(String(8), nullable=False, index=True)
    timestamp = Column(Integer, nullable=False, index=True)
    feature_name = Column(String(64), nullable=False)
    feature_value = Column(Float, nullable=False)

    __table_args__ = (
        UniqueConstraint("symbol", "timeframe", "timestamp", "feature_name", name="uq_feature_entry"),
        Index("idx_features_lookup", "symbol", "timeframe", "timestamp"),
    )


class SignalModel(Base):
    """Generated signals meeting score >= 75 and quality filters."""

    __tablename__ = "signals"

    id = Column(String(64), primary_key=True)  # Fingerprint hash or UUID
    symbol = Column(String(32), nullable=False, index=True)
    direction = Column(String(8), nullable=False)  # 'LONG' | 'SHORT'
    timestamp = Column(Integer, nullable=False, index=True)  # Epoch ms
    score = Column(Float, nullable=False)                    # Signal Score (0 - 100)
    market_regime = Column(String(32), nullable=False)
    current_price = Column(Float, nullable=False)
    entry_min = Column(Float, nullable=False)
    entry_max = Column(Float, nullable=False)
    stop_loss = Column(Float, nullable=False)
    tp1 = Column(Float, nullable=False)
    tp2 = Column(Float, nullable=False)
    risk_reward = Column(Float, nullable=False)
    status = Column(String(16), nullable=False, default="SIGNAL")  # SIGNAL, TP1, TP2, STOP, EXPIRED, INVALIDATED
    telegram_sent = Column(Boolean, nullable=False, default=False)
    telegram_message_id = Column(String(64), nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    features = relationship("SignalFeatureModel", back_populates="signal", cascade="all, delete-orphan")
    performance = relationship("SignalPerformanceModel", back_populates="signal", uselist=False, cascade="all, delete-orphan")


class SignalFeatureModel(Base):
    """Breakdown of feature contributions to a signal score."""

    __tablename__ = "signal_features"

    id = Column(Integer, primary_key=True, autoincrement=True)
    signal_id = Column(String(64), ForeignKey("signals.id", ondelete="CASCADE"), nullable=False, index=True)
    feature_name = Column(String(64), nullable=False)
    feature_value = Column(Float, nullable=True)
    contribution = Column(Float, nullable=False)
    details = Column(Text, nullable=True)

    signal = relationship("SignalModel", back_populates="features")


class SignalPerformanceModel(Base):
    """Paper execution tracking for backtesting without lookahead bias."""

    __tablename__ = "signal_performance"

    signal_id = Column(String(64), ForeignKey("signals.id", ondelete="CASCADE"), primary_key=True)
    outcome = Column(String(16), nullable=False, default="PENDING")  # PENDING, TP1_HIT, TP2_HIT, SL_HIT, EXPIRED
    mfe_pct = Column(Float, nullable=False, default=0.0)  # Max Favorable Excursion %
    mae_pct = Column(Float, nullable=False, default=0.0)  # Max Adverse Excursion %
    realized_r = Column(Float, nullable=False, default=0.0)
    entry_filled_at = Column(Integer, nullable=True)
    tp1_hit_at = Column(Integer, nullable=True)
    tp2_hit_at = Column(Integer, nullable=True)
    sl_hit_at = Column(Integer, nullable=True)
    closed_at = Column(Integer, nullable=True)
    ambiguous_hit = Column(Boolean, nullable=False, default=False)
    duration_seconds = Column(Integer, nullable=True)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    signal = relationship("SignalModel", back_populates="performance")
