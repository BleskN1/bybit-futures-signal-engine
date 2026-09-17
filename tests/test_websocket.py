"""Tests for Bybit WebSocket message parsing, event dispatching, and topic batching."""

import json

import pytest

from app.market_data.websocket import BybitWsClient


@pytest.mark.asyncio
async def test_websocket_kline_dispatch():
    """Verifies that BybitWsClient correctly parses Bybit V5 kline frames."""
    ws_client = BybitWsClient()

    received_events = []

    def kline_callback(symbol: str, interval: str, candle: dict):
        received_events.append((symbol, interval, candle))

    ws_client.on_kline(kline_callback)

    # Synthetic Bybit V5 closed kline message
    payload = {
        "topic": "kline.5.BTCUSDT",
        "data": [
            {
                "start": 1672324800000,
                "end": 1672325099999,
                "interval": "5",
                "open": "64000.5",
                "close": "64250.0",
                "high": "64300.0",
                "low": "63980.0",
                "volume": "142.5",
                "turnover": "9148000.0",
                "confirm": True,
                "timestamp": 1672325100000,
            }
        ],
    }

    await ws_client._handle_message(json.dumps(payload))

    assert len(received_events) == 1
    sym, tf, candle = received_events[0]
    assert sym == "BTCUSDT"
    assert tf == "5"
    assert candle["timestamp"] == 1672324800000
    assert candle["open"] == 64000.5
    assert candle["close"] == 64250.0
    assert candle["is_closed"] is True


@pytest.mark.asyncio
async def test_websocket_liquidation_dispatch():
    """Verifies parsing of Bybit V5 allLiquidation topics."""
    ws_client = BybitWsClient()

    liquidations = []

    def liq_callback(symbol: str, data: dict):
        liquidations.append((symbol, data))

    ws_client.on_liquidation(liq_callback)

    payload = {
        "topic": "allLiquidation.BTCUSDT",
        "data": [
            {
                "symbol": "BTCUSDT",
                "side": "Buy",
                "size": "2.5",
                "price": "64500.0",
                "updatedTime": 1672325100000,
            }
        ],
    }

    await ws_client._handle_message(json.dumps(payload))
    assert len(liquidations) == 1
    assert liquidations[0][0] == "BTCUSDT"
    assert liquidations[0][1]["side"] == "Buy"
