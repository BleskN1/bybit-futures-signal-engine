"""Market Data Quality Monitor and Validator for Bybit V5 Streams and REST feeds."""

import math
from dataclasses import dataclass, field
from typing import Any

from app.utils.logging import setup_logger

logger = setup_logger("signal_engine.data_quality")


@dataclass
class DataQualityCounters:
    """Quantitative counters for market data anomalies and validation failures."""

    total_candles_checked: int = 0
    valid_candles: int = 0
    impossible_ohlc_count: int = 0
    zero_or_negative_price_count: int = 0
    negative_volume_count: int = 0
    zero_volume_count: int = 0
    nan_or_inf_count: int = 0
    duplicate_candle_count: int = 0
    out_of_order_count: int = 0
    timestamp_gap_count: int = 0
    unconfirmed_candle_leak_count: int = 0
    stale_derivatives_count: int = 0
    total_derivatives_checked: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "total_candles_checked": self.total_candles_checked,
            "valid_candles": self.valid_candles,
            "impossible_ohlc_count": self.impossible_ohlc_count,
            "zero_or_negative_price_count": self.zero_or_negative_price_count,
            "negative_volume_count": self.negative_volume_count,
            "zero_volume_count": self.zero_volume_count,
            "nan_or_inf_count": self.nan_or_inf_count,
            "duplicate_candle_count": self.duplicate_candle_count,
            "out_of_order_count": self.out_of_order_count,
            "timestamp_gap_count": self.timestamp_gap_count,
            "unconfirmed_candle_leak_count": self.unconfirmed_candle_leak_count,
            "stale_derivatives_count": self.stale_derivatives_count,
            "total_derivatives_checked": self.total_derivatives_checked,
        }


class DataQualityMonitor:
    """
    Validates candle and derivative payloads against corruption, mathematical impossibility,
    and temporal anomalies.
    """

    def __init__(self):
        self.counters = DataQualityCounters()
        # Key: (symbol, timeframe) -> last seen timestamp
        self._last_timestamps: dict[tuple[str, str], int] = {}
        # Key: (symbol, timeframe) -> set of seen timestamps (capped to 5000)
        self._seen_timestamps: dict[tuple[str, str], set[int]] = {}

    def validate_candle(
        self,
        symbol: str,
        timeframe: str,
        candle: dict[str, Any],
        expected_duration_ms: int | None = None,
    ) -> tuple[bool, list[str]]:
        """
        Validates a single candle dictionary.
        Returns (is_valid, list_of_error_reasons).
        """
        self.counters.total_candles_checked += 1
        errors: list[str] = []

        ts = candle.get("timestamp")
        open_p = candle.get("open")
        high_p = candle.get("high")
        low_p = candle.get("low")
        close_p = candle.get("close")
        vol = candle.get("volume", 0.0)
        is_closed = candle.get("is_closed", True)

        # 1. Check for None, NaN, or Inf
        for name, val in [("open", open_p), ("high", high_p), ("low", low_p), ("close", close_p), ("volume", vol)]:
            if val is None or math.isnan(val) or math.isinf(val):
                errors.append(f"{name} is NaN or Infinite ({val})")
                self.counters.nan_or_inf_count += 1

        if errors:
            logger.warning(f"Data quality error [{symbol} TF={timeframe}]: {', '.join(errors)}")
            return False, errors

        # 2. Check for zero or negative prices
        if any(p <= 0.0 for p in [open_p, high_p, low_p, close_p]):
            errors.append(f"Zero or negative price: O={open_p}, H={high_p}, L={low_p}, C={close_p}")
            self.counters.zero_or_negative_price_count += 1

        # 3. Check for negative or zero volume
        if vol < 0.0:
            errors.append(f"Negative volume: {vol}")
            self.counters.negative_volume_count += 1
        elif vol == 0.0:
            self.counters.zero_volume_count += 1

        # 4. Check impossible OHLC relationships:
        # High must be >= max(Open, Close) and Low must be <= min(Open, Close)
        if high_p < low_p:
            errors.append(f"Impossible OHLC: High ({high_p}) < Low ({low_p})")
            self.counters.impossible_ohlc_count += 1
        if high_p < max(open_p, close_p):
            errors.append(f"Impossible OHLC: High ({high_p}) < max(Open, Close) ({max(open_p, close_p)})")
            self.counters.impossible_ohlc_count += 1
        if low_p > min(open_p, close_p):
            errors.append(f"Impossible OHLC: Low ({low_p}) > min(Open, Close) ({min(open_p, close_p)})")
            self.counters.impossible_ohlc_count += 1

        # 5. Timestamp validation
        if ts is None or ts <= 0:
            errors.append(f"Invalid timestamp: {ts}")
        else:
            key = (symbol, timeframe)
            if key not in self._seen_timestamps:
                self._seen_timestamps[key] = set()

            if ts in self._seen_timestamps[key]:
                errors.append(f"Duplicate candle timestamp {ts}")
                self.counters.duplicate_candle_count += 1
            else:
                self._seen_timestamps[key].add(ts)
                if len(self._seen_timestamps[key]) > 5000:
                    # Keep size bounded
                    min_ts = min(self._seen_timestamps[key])
                    self._seen_timestamps[key].remove(min_ts)

            last_ts = self._last_timestamps.get(key)
            if last_ts is not None:
                if ts < last_ts:
                    errors.append(f"Out of order candle: {ts} < previous {last_ts}")
                    self.counters.out_of_order_count += 1
                elif expected_duration_ms and expected_duration_ms > 0:
                    gap = ts - last_ts
                    if gap > (expected_duration_ms * 1.5):
                        self.counters.timestamp_gap_count += 1

            self._last_timestamps[key] = ts

        # 6. Check unconfirmed candle flag
        if not is_closed:
            errors.append("Unclosed candle rejected from closed-bar pipeline")
            self.counters.unconfirmed_candle_leak_count += 1

        if errors:
            logger.warning(f"Data quality error [{symbol} TF={timeframe}]: {', '.join(errors)}")
            return False, errors

        self.counters.valid_candles += 1
        return True, []

    def validate_derivatives(
        self,
        symbol: str,
        derivatives_data: dict[str, Any],
        as_of: int,
        max_age_ms: int = 3600 * 1000,
    ) -> tuple[bool, list[str]]:
        """Validates derivative metrics (open interest, funding rate, age)."""
        self.counters.total_derivatives_checked += 1
        errors: list[str] = []

        history = derivatives_data.get("history", [])
        oi = float(derivatives_data.get("open_interest") or 0.0)
        fr = derivatives_data.get("funding_rate")

        if oi <= 0.0:
            errors.append(f"Non-positive open interest: {oi}")

        if fr is not None and (math.isnan(fr) or math.isinf(fr)):
            errors.append(f"Funding rate is NaN or Inf: {fr}")
            self.counters.nan_or_inf_count += 1

        latest_ts = history[-1]["timestamp"] if history else as_of
        age = as_of - latest_ts
        if age > max_age_ms:
            errors.append(f"Stale derivative data: age={age / 1000:.0f}s > max {max_age_ms / 1000:.0f}s")
            self.counters.stale_derivatives_count += 1

        if errors:
            logger.warning(f"Derivatives quality warning [{symbol}]: {', '.join(errors)}")
            return False, errors

        return True, []
