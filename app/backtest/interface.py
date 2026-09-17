"""Backtesting engine interface and abstractions."""

from abc import ABC, abstractmethod
from typing import Any

from app.market_data.provider import MarketDataProvider


class BacktestEngine(ABC):
    """Abstract interface for historical backtesting and parameter evaluation."""

    @abstractmethod
    async def run(
        self,
        provider: MarketDataProvider,
        symbols: list[str],
        start_time: int,
        end_time: int,
    ) -> dict[str, Any]:
        """Runs historical backtest across symbols and returns performance report."""
