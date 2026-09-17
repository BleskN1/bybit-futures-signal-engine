"""Abstract base interface for cryptocurrency exchange adapters."""

from abc import ABC, abstractmethod
from typing import Any


class ExchangeAdapter(ABC):
    """Abstract interface to decouple trading logic from exchange-specific APIs."""

    @property
    @abstractmethod
    def exchange_name(self) -> str:
        """Name of the exchange."""

    @abstractmethod
    async def get_instruments_info(self, category: str = "linear") -> list[dict[str, Any]]:
        """Fetch all tradable instruments with pagination."""

    @abstractmethod
    async def get_tickers(self, category: str = "linear") -> list[dict[str, Any]]:
        """Fetch all 24h tickers."""

    @abstractmethod
    async def get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 200,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch historical kline/candlestick bars."""

    @abstractmethod
    async def get_open_interest(
        self,
        symbol: str,
        interval_time: str = "5min",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Fetch historical raw open interest."""

    @abstractmethod
    async def get_funding_history(
        self,
        symbol: str,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Fetch historical funding rates."""

    @abstractmethod
    async def get_long_short_ratio(
        self,
        symbol: str,
        period: str = "5min",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Fetch historical long/short account ratio."""
