"""Tests for DatabaseRepository schema, upsert, and performance tracking."""

import pytest
import pytest_asyncio

from app.database.repository import DatabaseRepository


@pytest_asyncio.fixture
async def test_db():
    repo = DatabaseRepository("sqlite+aiosqlite:///:memory:")
    await repo.init_db()
    return repo


@pytest.mark.asyncio
async def test_database_crud_operations(test_db):
    """Verifies database tables creation, saving candles, raw derivatives, and signal lifecycle."""
    # 1. Save symbols
    await test_db.save_symbols([
        {
            "symbol": "BTCUSDT",
            "volume_24h": 1000.0,
            "turnover_24h": 65000000.0,
            "open_interest_value": 25000000.0,
            "volatility_pct": 0.04,
            "rank": 1,
        }
    ])

    # 2. Save candles
    candles = [
        {"timestamp": 1000, "open": 65000, "high": 65200, "low": 64900, "close": 65100, "volume": 10.5, "is_closed": True},
        {"timestamp": 2000, "open": 65100, "high": 65300, "low": 65000, "close": 65250, "volume": 12.0, "is_closed": True},
    ]
    await test_db.save_candles("BTCUSDT", "5", candles)

    # 3. Save raw derivative
    await test_db.save_derivative("BTCUSDT", 2000, open_interest=45000.5, funding_rate=0.0001)

    # 4. Save signal with score >= 75
    signal = {
        "id": "sig-btc-long-1",
        "symbol": "BTCUSDT",
        "direction": "LONG",
        "timestamp": 2000,
        "score": 82.5,
        "market_regime": "TRENDING_UP",
        "current_price": 65250.0,
        "entry_min": 65200.0,
        "entry_max": 65250.0,
        "stop_loss": 64800.0,
        "tp1": 65700.0,
        "tp2": 66150.0,
        "risk_reward": 2.0,
    }
    feature_breakdown = [
        {"feature_name": "htf_trend", "feature_value": 1.0, "contribution": 14.0, "details": "4H EMA Bullish"},
        {"feature_name": "derivatives", "feature_value": 0.02, "contribution": 13.0, "details": "OI Rising with Price"},
    ]
    await test_db.save_signal(signal, feature_breakdown)

    active_signals = await test_db.get_active_signals()
    assert len(active_signals) == 1
    assert active_signals[0].id == "sig-btc-long-1"
    assert active_signals[0].score == 82.5

    # 5. Update performance outcome (paper tracking)
    await test_db.update_signal_performance(
        signal_id="sig-btc-long-1",
        outcome="TP1_HIT",
        mfe_pct=0.8,
        mae_pct=-0.1,
        realized_r=1.0,
        closed_at=3500,
    )

    remaining_active = await test_db.get_active_signals()
    assert len(remaining_active) == 0
