"""Tests for Multi-Factor Dynamic Universe Ranking."""

from unittest.mock import AsyncMock

import pytest

from app.market_data.ranking import UniverseSelector


@pytest.mark.asyncio
async def test_universe_ranking_and_filters(mock_instruments, mock_tickers):
    """Verifies filtering of inactive/illiquid pairs and multi-factor ranking order."""
    mock_client = AsyncMock()
    mock_client.get_instruments_info.return_value = mock_instruments
    mock_client.get_tickers.return_value = mock_tickers

    config = {
        "weights": {
            "turnover_24h": 0.35,
            "open_interest": 0.25,
            "volume_24h": 0.15,
            "volatility": 0.10,
            "trades_activity": 0.10,
            "spread_penalty": 0.05,
        },
        "filters": {
            "min_turnover_24h_usdt": 10000000.0,
            "min_open_interest_usdt": 2000000.0,
            "max_bid_ask_spread_pct": 0.0015,
            "quote_coin": "USDT",
            "contract_status": "Trading",
        },
    }

    selector = UniverseSelector(mock_client, config)
    top_symbols = await selector.select_top_symbols(top_n=2)

    # DEADUSDT must be excluded (status != Trading)
    # SHIBUSDT must be excluded (turnover < 10M, OI < 2M)
    # Remaining candidates: BTCUSDT, ETHUSDT, SOLUSDT
    symbols = [item["symbol"] for item in top_symbols]
    assert len(top_symbols) == 2
    assert "DEADUSDT" not in symbols
    assert "SHIBUSDT" not in symbols
    assert "BTCUSDT" in symbols
    # BTCUSDT should be rank 1 due to highest turnover and open interest
    assert top_symbols[0]["symbol"] == "BTCUSDT"
    assert top_symbols[0]["rank"] == 1
    assert top_symbols[0]["ranking_score"] >= top_symbols[1]["ranking_score"]
