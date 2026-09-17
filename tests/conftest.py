"""Pytest fixtures and mock data for Bybit Signal Engine tests."""

from typing import Any

import pytest


@pytest.fixture
def mock_instruments() -> list[dict[str, Any]]:
    return [
        {
            "symbol": "BTCUSDT",
            "status": "Trading",
            "contractType": "LinearPerpetual",
            "priceFilter": {"tickSize": "0.1"},
            "lotSizeFilter": {"qtyStep": "0.001"},
        },
        {
            "symbol": "ETHUSDT",
            "status": "Trading",
            "contractType": "LinearPerpetual",
            "priceFilter": {"tickSize": "0.01"},
            "lotSizeFilter": {"qtyStep": "0.01"},
        },
        {
            "symbol": "SOLUSDT",
            "status": "Trading",
            "contractType": "LinearPerpetual",
            "priceFilter": {"tickSize": "0.001"},
            "lotSizeFilter": {"qtyStep": "0.1"},
        },
        {
            "symbol": "SHIBUSDT",
            "status": "Trading",
            "contractType": "LinearPerpetual",
            "priceFilter": {"tickSize": "0.000001"},
            "lotSizeFilter": {"qtyStep": "100"},
        },
        {
            "symbol": "DEADUSDT",
            "status": "Closed",
            "contractType": "LinearPerpetual",
            "priceFilter": {"tickSize": "0.01"},
            "lotSizeFilter": {"qtyStep": "1"},
        },
    ]


@pytest.fixture
def mock_tickers() -> list[dict[str, Any]]:
    return [
        {
            "symbol": "BTCUSDT",
            "lastPrice": "65000.0",
            "turnover24h": "1500000000.0",
            "volume24h": "23000.0",
            "openInterest": "40000.0",
            "openInterestValue": "2600000000.0",
            "highPrice24h": "66000.0",
            "lowPrice24h": "64000.0",
            "bid1Price": "64999.5",
            "ask1Price": "65000.0",
            "fundingRate": "0.0001",
        },
        {
            "symbol": "ETHUSDT",
            "lastPrice": "3500.0",
            "turnover24h": "800000000.0",
            "volume24h": "228000.0",
            "openInterest": "250000.0",
            "openInterestValue": "875000000.0",
            "highPrice24h": "3550.0",
            "lowPrice24h": "3420.0",
            "bid1Price": "3499.8",
            "ask1Price": "3500.0",
            "fundingRate": "0.0001",
        },
        {
            "symbol": "SOLUSDT",
            "lastPrice": "150.0",
            "turnover24h": "400000000.0",
            "volume24h": "2660000.0",
            "openInterest": "1500000.0",
            "openInterestValue": "225000000.0",
            "highPrice24h": "155.0",
            "lowPrice24h": "145.0",
            "bid1Price": "149.95",
            "ask1Price": "150.0",
            "fundingRate": "0.00015",
        },
        {
            "symbol": "SHIBUSDT",
            "lastPrice": "0.00002",
            "turnover24h": "500000.0",  # Low turnover - should be filtered
            "volume24h": "25000000000.0",
            "openInterest": "1000000000.0",
            "openInterestValue": "20000.0",
            "highPrice24h": "0.000021",
            "lowPrice24h": "0.000019",
            "bid1Price": "0.0000199",
            "ask1Price": "0.0000201",
            "fundingRate": "0.0001",
        },
    ]
