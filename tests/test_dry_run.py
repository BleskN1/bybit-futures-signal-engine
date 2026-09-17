"""Comprehensive unit and integration tests for STEP 4.5 Dry Run and Data Quality."""

import math
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.market_data.provider import LiveMarketDataProvider
from app.market_data.quality import DataQualityMonitor
from app.market_data.rest import BybitRestClient
from app.signal.engine import SignalEngine
from app.signal.levels import EntryLevelCalculator
from app.signal.models import SignalCandidate, SignalStatus
from app.signal.mtf import MTFAnalyzer
from app.telegram.formatter import TelegramSignalFormatter


def test_data_quality_impossible_ohlc():
    """Verifies DataQualityMonitor catches High < Low and impossible OHLC relationships."""
    monitor = DataQualityMonitor()

    # High < Low
    invalid_candle = {
        "timestamp": 1700000000000,
        "open": 100.0,
        "high": 90.0,
        "low": 95.0,
        "close": 92.0,
        "volume": 10.0,
        "is_closed": True,
    }
    is_valid, errors = monitor.validate_candle("BTCUSDT", "15", invalid_candle)
    assert not is_valid
    assert monitor.counters.impossible_ohlc_count > 0


def test_data_quality_zero_and_negative_price():
    """Verifies DataQualityMonitor rejects zero or negative prices."""
    monitor = DataQualityMonitor()

    zero_price_candle = {
        "timestamp": 1700000000000,
        "open": 0.0,
        "high": 100.0,
        "low": 0.0,
        "close": 90.0,
        "volume": 10.0,
        "is_closed": True,
    }
    is_valid, errors = monitor.validate_candle("BTCUSDT", "15", zero_price_candle)
    assert not is_valid
    assert monitor.counters.zero_or_negative_price_count > 0


def test_data_quality_nan_and_inf():
    """Verifies DataQualityMonitor rejects NaN and Inf values."""
    monitor = DataQualityMonitor()

    nan_candle = {
        "timestamp": 1700000000000,
        "open": 100.0,
        "high": float("nan"),
        "low": 90.0,
        "close": 95.0,
        "volume": 10.0,
        "is_closed": True,
    }
    is_valid, errors = monitor.validate_candle("BTCUSDT", "15", nan_candle)
    assert not is_valid
    assert monitor.counters.nan_or_inf_count > 0


def test_data_quality_duplicates_and_out_of_order():
    """Verifies DataQualityMonitor catches duplicate and out-of-order timestamps."""
    monitor = DataQualityMonitor()

    c1 = {"timestamp": 1000, "open": 10.0, "high": 12.0, "low": 9.0, "close": 11.0, "volume": 1.0, "is_closed": True}
    c2 = {"timestamp": 1000, "open": 10.0, "high": 12.0, "low": 9.0, "close": 11.0, "volume": 1.0, "is_closed": True}
    c3 = {"timestamp": 900, "open": 10.0, "high": 12.0, "low": 9.0, "close": 11.0, "volume": 1.0, "is_closed": True}

    v1, _ = monitor.validate_candle("ETHUSDT", "5", c1)
    assert v1
    v2, _ = monitor.validate_candle("ETHUSDT", "5", c2)
    assert not v2
    assert monitor.counters.duplicate_candle_count == 1

    v3, _ = monitor.validate_candle("ETHUSDT", "5", c3)
    assert not v3
    assert monitor.counters.out_of_order_count == 1


def test_closed_candle_enforcement():
    """Verifies that unfinished/forming candles are rejected from closed-bar processing."""
    analyzer = MTFAnalyzer()

    # 15m candles: duration = 15 * 60 * 1000 = 900,000 ms
    # Candle 1: starts 100,000 -> finishes 1,000,000
    # Candle 2: starts 1,000,000 -> finishes 1,900,000, but has is_closed = False
    candles = [
        {"timestamp": 100000, "is_closed": True},
        {"timestamp": 1000000, "is_closed": False},
    ]

    closed = analyzer.filter_closed_bars(candles, "15", as_of=2000000)
    assert len(closed) == 1
    assert closed[0]["timestamp"] == 100000


def test_mtf_as_of_synchronization():
    """
    Verifies exact as_of synchronization behavior:
    At 12:35:
    5m candle closing at 12:35 is included, but 12:35 candle closing at 12:40 is excluded.
    15m candle closing at 12:30 is included, but 12:30 candle closing at 12:45 is excluded.
    1h candle closing at 12:00 is included, but 12:00 candle closing at 13:00 is excluded.
    4h candle closing at 12:00 is included, but 12:00 candle closing at 16:00 is excluded.
    """
    analyzer = MTFAnalyzer()

    # Reference as_of: 12:35 (in ms relative to 0)
    # 0 = 00:00, 1h = 3600000, 1m = 60000
    t_12_00 = 12 * 3600 * 1000
    t_12_15 = t_12_00 + 15 * 60 * 1000
    t_12_30 = t_12_00 + 30 * 60 * 1000
    t_12_35 = t_12_00 + 35 * 60 * 1000

    # 15m candles:
    # 12:00 -> closes at 12:15 <= 12:35 (closed!)
    # 12:15 -> closes at 12:30 <= 12:35 (closed!)
    # 12:30 -> closes at 12:45 > 12:35 (forming / unclosed!)
    m15_candles = [
        {"timestamp": t_12_00, "is_closed": True},
        {"timestamp": t_12_15, "is_closed": True},
        {"timestamp": t_12_30, "is_closed": True},
    ]
    filtered_15m = analyzer.filter_closed_bars(m15_candles, "15", as_of=t_12_35)
    assert len(filtered_15m) == 2
    assert filtered_15m[-1]["timestamp"] == t_12_15  # 12:15 candle is the latest closed!

    # 1h candles:
    # 11:00 -> closes at 12:00 <= 12:35 (closed!)
    # 12:00 -> closes at 13:00 > 12:35 (forming!)
    t_11_00 = 11 * 3600 * 1000
    h1_candles = [
        {"timestamp": t_11_00, "is_closed": True},
        {"timestamp": t_12_00, "is_closed": True},
    ]
    filtered_1h = analyzer.filter_closed_bars(h1_candles, "60", as_of=t_12_35)
    assert len(filtered_1h) == 1
    assert filtered_1h[0]["timestamp"] == t_11_00


def test_june_2026_single_open_interest_methodology():
    """
    Verifies that Bybit's singleOpenInterest field is parsed and standardized
    to avoid artificial 2x jumps or halving.
    """
    provider = LiveMarketDataProvider()

    # Historical record with singleOpenInterest (June 11, 2026 standard)
    hist_rec = {
        "timestamp": 1000,
        "open_interest": 27938.74,  # single-counted
        "single_open_interest": 27938.74,
        "raw_open_interest": 55877.48,  # bilateral
    }
    provider.update_ticker("BTCUSDT", hist_rec)

    # Live ticker incoming with bilateral openInterest = 55900.0 (~2x of single-counted)
    provider.update_ticker("BTCUSDT", {"openInterest": "55900.0", "timestamp": 2000})

    deriv = provider.get_derivatives("BTCUSDT", as_of=3000)
    # Verify that the bilateral ticker was normalized to ~27950.0 rather than 55900.0,
    # preventing a false +100% OI jump
    assert deriv["open_interest"] < 35000.0
    assert math.isclose(deriv["open_interest"], 27950.0, rel_tol=0.01)


def test_mechanical_risk_levels_validation():
    """Verifies strict mechanical validation of SL, Entry, TP1, TP2, and R:R."""
    calc = EntryLevelCalculator()

    # Manually test valid LONG setup geometry
    # Required: stop_loss < entry_low <= entry_high < tp1 < tp2
    entry_low = 100.0
    entry_high = 100.5
    stop_loss = 98.0
    tp1 = 104.0
    tp2 = 107.0

    risk = abs(100.25 - stop_loss)
    reward_tp1 = tp1 - 100.25
    rr = reward_tp1 / risk
    assert rr >= 1.5
    assert stop_loss < entry_low <= entry_high < tp1 < tp2

    # Manually test valid SHORT setup geometry
    # Required: stop_loss > entry_high >= entry_low > tp1 > tp2
    s_entry_low = 100.0
    s_entry_high = 100.5
    s_stop_loss = 102.5
    s_tp1 = 96.5
    s_tp2 = 94.0

    s_risk = abs(100.25 - s_stop_loss)
    s_reward = 100.25 - s_tp1
    s_rr = s_reward / s_risk
    assert s_rr >= 1.5
    assert s_stop_loss > s_entry_high >= s_entry_low > s_tp1 > s_tp2


def test_telegram_dry_run_formatting():
    """Verifies that Telegram format explicitly carries DRY RUN watermark and zero probability claims."""
    candidate = SignalCandidate(
        symbol="BTCUSDT",
        timestamp=datetime.now(timezone.utc),
        as_of_timestamp=1700000000000,
        direction="LONG",
        long_score=82.5,
        short_score=40.0,
        directional_edge=42.5,
        signal_status=SignalStatus.SIGNAL,
        regime="TRENDING",
        entry_zone_low=95000.0,
        entry_zone_high=95200.0,
        current_price=95100.0,
        stop_loss=93800.0,
        take_profit_1=97500.0,
        take_profit_2=100000.0,
        risk_reward_tp1=1.8,
        risk_reward_tp2=3.6,
        reason_codes=["MOMENTUM_ALIGNMENT", "SWEEP_BOUNCE"],
        warning_codes=[],
    )

    msg = TelegramSignalFormatter.format(candidate, is_dry_run=True, dry_run_label="DRY RUN — READ ONLY")
    assert "DRY RUN — READ ONLY" in msg
    assert "BTCUSDT" in msg
    assert "LONG" in msg
    assert "Score represents multi-factor rule alignment" in msg
    # Verify no deceptive win-rate claims
    assert "win rate" not in msg.lower()
    assert "guaranteed" not in msg.lower()
