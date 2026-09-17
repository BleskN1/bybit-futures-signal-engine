"""Tests for historical kline pagination and deep bootstrap."""

from unittest.mock import patch

import pytest

from app.market_data.rest import BybitRestClient


@pytest.mark.asyncio
async def test_historical_klines_pagination():
    """Verifies that BybitRestClient paginates backwards to fetch total_candles without duplication."""
    client = BybitRestClient()

    # Generate synthetic response chunks of 200 candles each
    # Chunk 1: timestamps 801 to 1000
    # Chunk 2: timestamps 601 to 800
    # Chunk 3: timestamps 401 to 600
    def mock_get_klines(symbol, interval, limit=200, start_time=None, end_time=None):
        if end_time is None:
            max_ts = 1000
        else:
            max_ts = end_time

        bars = []
        for ts in range(max_ts - 199, max_ts + 1):
            if ts <= 0:
                continue
            bars.append({
                "timestamp": ts,
                "open": 100.0,
                "high": 105.0,
                "low": 95.0,
                "close": 102.0,
                "volume": 10.0,
                "turnover": 1000.0,
                "is_closed": True,
            })
        return bars

    with patch.object(client, "get_klines", side_effect=mock_get_klines):
        candles = await client.get_historical_klines_paginated(
            symbol="BTCUSDT",
            interval="5",
            total_candles=500,
        )

        assert len(candles) == 500
        # Check chronological ordering (strictly increasing timestamps)
        timestamps = [c["timestamp"] for c in candles]
        assert timestamps == sorted(timestamps)
        # Check no duplicates
        assert len(timestamps) == len(set(timestamps))
        # Check continuity
        assert timestamps[-1] == 1000
        assert timestamps[0] == 501
