"""Database repository providing async operations for storing and querying market data and signals."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import desc, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.database.models import (
    Base,
    CandleModel,
    DerivativeModel,
    FeatureModel,
    SignalFeatureModel,
    SignalModel,
    SignalPerformanceModel,
    SymbolModel,
)
from app.utils.logging import setup_logger

logger = setup_logger("signal_engine.database")


class DatabaseRepository:
    """Async database repository interface."""

    def __init__(self, db_url: str | None = None):
        target_url = db_url or settings.DATABASE_URL
        # Ensure parent directory exists for SQLite
        if target_url.startswith("sqlite"):
            db_path = target_url.split("///")[-1]
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        self.engine = create_async_engine(target_url, echo=False)
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    async def init_db(self) -> None:
        """Initializes database tables."""
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database schema initialized successfully.")

    async def save_symbols(self, symbols: list[dict[str, Any]]) -> None:
        """Upserts active universe symbols."""
        async with self.session_factory() as session:
            for item in symbols:
                stmt = sqlite_insert(SymbolModel).values(
                    symbol=item["symbol"],
                    status="Trading",
                    volume_24h=item.get("volume_24h", 0.0),
                    turnover_24h=item.get("turnover_24h", 0.0),
                    open_interest=item.get("open_interest_value", 0.0),
                    volatility=item.get("volatility_pct", 0.0),
                    rank=item.get("rank"),
                    is_active=True,
                    updated_at=datetime.now(timezone.utc),
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["symbol"],
                    set_={
                        "volume_24h": item.get("volume_24h", 0.0),
                        "turnover_24h": item.get("turnover_24h", 0.0),
                        "open_interest": item.get("open_interest_value", 0.0),
                        "volatility": item.get("volatility_pct", 0.0),
                        "rank": item.get("rank"),
                        "updated_at": datetime.now(timezone.utc),
                    },
                )
                await session.execute(stmt)
            await session.commit()

    async def save_candles(self, symbol: str, timeframe: str, candles: list[dict[str, Any]]) -> None:
        """Upserts closed candlestick bars."""
        if not candles:
            return
        async with self.session_factory() as session:
            for c in candles:
                stmt = sqlite_insert(CandleModel).values(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=c["timestamp"],
                    open=c["open"],
                    high=c["high"],
                    low=c["low"],
                    close=c["close"],
                    volume=c["volume"],
                    turnover=c.get("turnover", 0.0),
                    is_closed=c.get("is_closed", True),
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["symbol", "timeframe", "timestamp"],
                    set_={
                        "open": c["open"],
                        "high": c["high"],
                        "low": c["low"],
                        "close": c["close"],
                        "volume": c["volume"],
                        "turnover": c.get("turnover", 0.0),
                        "is_closed": c.get("is_closed", True),
                    },
                )
                await session.execute(stmt)
            await session.commit()

    async def save_derivative(self, symbol: str, timestamp: int, open_interest: float, funding_rate: float | None = None) -> None:
        """Saves a raw derivative metric entry."""
        async with self.session_factory() as session:
            model = DerivativeModel(
                symbol=symbol,
                timestamp=timestamp,
                open_interest=open_interest,
                funding_rate=funding_rate,
            )
            session.add(model)
            await session.commit()

    async def save_features(self, symbol: str, timeframe: str, timestamp: int, features: dict[str, float]) -> None:
        """Upserts calculated features snapshot."""
        async with self.session_factory() as session:
            for name, val in features.items():
                if val is None or not isinstance(val, (int, float)):
                    continue
                stmt = sqlite_insert(FeatureModel).values(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=timestamp,
                    feature_name=name,
                    feature_value=float(val),
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["symbol", "timeframe", "timestamp", "feature_name"],
                    set_={"feature_value": float(val)},
                )
                await session.execute(stmt)
            await session.commit()

    async def save_signal(self, signal_dict: dict[str, Any], feature_breakdown: list[dict[str, Any]] | None = None) -> None:
        """Saves a qualified signal and initializes its performance tracking."""
        async with self.session_factory() as session:
            sig_model = SignalModel(
                id=signal_dict["id"],
                symbol=signal_dict["symbol"],
                direction=signal_dict["direction"],
                timestamp=signal_dict["timestamp"],
                score=signal_dict["score"],
                market_regime=signal_dict["market_regime"],
                current_price=signal_dict["current_price"],
                entry_min=signal_dict["entry_min"],
                entry_max=signal_dict["entry_max"],
                stop_loss=signal_dict["stop_loss"],
                tp1=signal_dict["tp1"],
                tp2=signal_dict["tp2"],
                risk_reward=signal_dict["risk_reward"],
                status=signal_dict.get("status", "SIGNAL"),
                telegram_sent=signal_dict.get("telegram_sent", False),
            )
            session.add(sig_model)

            # Performance tracker entry
            perf_model = SignalPerformanceModel(
                signal_id=signal_dict["id"],
                outcome="PENDING",
            )
            session.add(perf_model)

            # Feature breakdown attribution
            if feature_breakdown:
                for f in feature_breakdown:
                    session.add(
                        SignalFeatureModel(
                            signal_id=signal_dict["id"],
                            feature_name=f["feature_name"],
                            feature_value=f.get("feature_value"),
                            contribution=f["contribution"],
                            details=f.get("details"),
                        )
                    )

            await session.commit()

    async def get_active_signals(self) -> list[SignalModel]:
        """Retrieves signals currently in PENDING/SIGNAL status for tracking."""
        async with self.session_factory() as session:
            query = (
                select(SignalModel)
                .join(SignalPerformanceModel)
                .where(SignalPerformanceModel.outcome == "PENDING")
            )
            result = await session.execute(query)
            return list(result.scalars().all())

    async def update_signal_performance(
        self,
        signal_id: str,
        outcome: str,
        mfe_pct: float,
        mae_pct: float,
        realized_r: float,
        ambiguous_hit: bool = False,
        closed_at: int | None = None,
    ) -> None:
        """Updates performance tracking outcome for a signal."""
        async with self.session_factory() as session:
            stmt = (
                update(SignalPerformanceModel)
                .where(SignalPerformanceModel.signal_id == signal_id)
                .values(
                    outcome=outcome,
                    mfe_pct=mfe_pct,
                    mae_pct=mae_pct,
                    realized_r=realized_r,
                    ambiguous_hit=ambiguous_hit,
                    closed_at=closed_at,
                    updated_at=datetime.now(timezone.utc),
                )
            )
            await session.execute(stmt)

            # Also update signal status
            sig_stmt = (
                update(SignalModel)
                .where(SignalModel.id == signal_id)
                .values(status=outcome)
            )
            await session.execute(sig_stmt)
            await session.commit()

    async def get_recent_signal(self, symbol: str, direction: str, within_ms: int) -> SignalModel | None:
        """Checks if an identical signal was generated within the cooldown window."""
        async with self.session_factory() as session:
            query = (
                select(SignalModel)
                .where(
                    SignalModel.symbol == symbol,
                    SignalModel.direction == direction,
                    SignalModel.timestamp >= within_ms,
                )
                .order_by(desc(SignalModel.timestamp))
                .limit(1)
            )
            result = await session.execute(query)
            return result.scalar_one_or_none()
