"""Bybit V5 Exchange Adapter implementation."""

from typing import Any

from app.exchange.base import ExchangeAdapter
from app.market_data.rest import BybitRestClient


class BybitAdapter(ExchangeAdapter):
    """Bybit V5 implementation of ExchangeAdapter."""

    def __init__(self, rest_client: BybitRestClient):
        self.rest_client = rest_client

    @property
    def exchange_name(self) -> str:
        return "bybit"

    async def get_instruments_info(self, category: str = "linear") -> list[dict[str, Any]]:
        return await self.rest_client.get_instruments_info(category=category)

    async def get_tickers(self, category: str = "linear") -> list[dict[str, Any]]:
        return await self.rest_client.get_tickers(category=category)

    async def get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 200,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> list[dict[str, Any]]:
        return await self.rest_client.get_klines(
            symbol=symbol,
            interval=interval,
            limit=limit,
            start_time=start_time,
            end_time=end_time,
        )

    async def get_open_interest(
        self,
        symbol: str,
        interval_time: str = "5min",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        return await self.rest_client.get_open_interest(
            symbol=symbol,
            interval_time=interval_time,
            limit=limit,
        )

    async def get_funding_history(
        self,
        symbol: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        return await self.rest_client.get_funding_history(symbol=symbol, limit=limit)

    async def get_long_short_ratio(
        self,
        symbol: str,
        period: str = "5min",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        return await self.rest_client.get_long_short_ratio(symbol=symbol, period=period, limit=limit)
