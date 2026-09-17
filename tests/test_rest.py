"""Tests for BybitRestClient error handling, rate limiting retry, and endpoint parsing."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.market_data.rest import BybitRestClient


@pytest.mark.asyncio
async def test_rest_client_retcode_error_handling():
    """Verifies that non-zero retCode raises ValueError with message."""
    client = BybitRestClient()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "retCode": 10001,
        "retMsg": "Params error",
        "result": {},
    }

    mock_http_client = AsyncMock()
    mock_http_client.get.return_value = mock_response

    with patch.object(client, "get_client", return_value=mock_http_client):
        with pytest.raises(ValueError) as exc_info:
            await client._get("/v5/market/tickers")
        assert "10001" in str(exc_info.value)
        assert "Params error" in str(exc_info.value)


@pytest.mark.asyncio
async def test_rest_client_open_interest_parsing():
    """Verifies parsing and chronological ordering of open interest records."""
    client = BybitRestClient()

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "retCode": 0,
        "retMsg": "OK",
        "result": {
            "list": [
                {"openInterest": "25000.5", "timestamp": "1672324900000"},
                {"openInterest": "24950.0", "timestamp": "1672324800000"},
            ]
        },
    }

    mock_http_client = AsyncMock()
    mock_http_client.get.return_value = mock_response

    with patch.object(client, "get_client", return_value=mock_http_client):
        records = await client.get_open_interest("BTCUSDT", interval_time="5min")
        assert len(records) == 2
        # Oldest first: 1672324800000 before 1672324900000
        assert records[0]["timestamp"] == 1672324800000
        assert records[0]["open_interest"] == 24950.0
        assert records[1]["timestamp"] == 1672324900000
        assert records[1]["open_interest"] == 25000.5
