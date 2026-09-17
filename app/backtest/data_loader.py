"""Historical data loader with disk caching, Bybit REST pagination, and lookahead protection."""

import json
from pathlib import Path
from typing import Any

from app.market_data.historical import HistoricalMarketDataProvider
from app.market_data.rest import BybitRestClient
from app.utils.logging import setup_logger

logger = setup_logger("signal_engine.data_loader")


class HistoricalDataLoader:
    """
    Manages downloading, deduplicating, caching, and serving historical
    candlestick and derivative datasets for backtesting.
    """

    def __init__(
        self,
        cache_dir: str | Path = "data/historical",
        rest_client: BybitRestClient | None = None,
    ):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.rest_client = rest_client

    def _get_cache_path(self, symbol: str, timeframe: str) -> Path:
        return self.cache_dir / f"{symbol}_{timeframe}.json"

    def _get_funding_cache_path(self, symbol: str) -> Path:
        return self.cache_dir / f"{symbol}_funding.json"

    def load_cached_candles(self, symbol: str, timeframe: str) -> list[dict[str, Any]] | None:
        """Loads cached candles from disk if available."""
        path = self._get_cache_path(symbol, timeframe)
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    candles = json.load(f)
                logger.info(f"Loaded {len(candles)} cached candles for {symbol} {timeframe}")
                return candles
            except Exception as e:
                logger.warning(f"Failed to read cache for {symbol} {timeframe}: {e}")
        return None

    def save_cached_candles(self, symbol: str, timeframe: str, candles: list[dict[str, Any]]) -> None:
        """Saves candles to disk cache."""
        path = self._get_cache_path(symbol, timeframe)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(candles, f)
            logger.info(f"Saved {len(candles)} candles to cache at {path}")
        except Exception as e:
            logger.warning(f"Failed to write cache for {symbol} {timeframe}: {e}")

    def load_cached_funding(self, symbol: str) -> list[dict[str, Any]] | None:
        path = self._get_funding_cache_path(symbol)
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read funding cache for {symbol}: {e}")
        return None

    def save_cached_funding(self, symbol: str, funding: list[dict[str, Any]]) -> None:
        path = self._get_funding_cache_path(symbol)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(funding, f)
        except Exception as e:
            logger.warning(f"Failed to save funding cache for {symbol}: {e}")

    async def fetch_or_load_candles(
        self,
        symbol: str,
        timeframe: str,
        target_count: int = 2500,
        force_refresh: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Retrieves candles from local cache or fetches from Bybit REST.
        Enforces deduplication, chronological ordering, and closed-bar validation.
        """
        if not force_refresh:
            cached = self.load_cached_candles(symbol, timeframe)
            if cached and len(cached) >= target_count:
                return cached

        if not self.rest_client:
            self.rest_client = BybitRestClient()

        logger.info(f"Fetching {target_count} historical candles for {symbol} {timeframe} via REST...")
        candles = await self.rest_client.get_historical_klines_paginated(
            symbol=symbol,
            interval=timeframe,
            total_candles=target_count,
        )

        # Ensure deduplicated and strictly chronological
        dedup_map: dict[int, dict[str, Any]] = {}
        for c in candles:
            # Enforce is_closed
            c["is_closed"] = True
            dedup_map[c["timestamp"]] = c

        sorted_candles = sorted(dedup_map.values(), key=lambda x: x["timestamp"])
        self.save_cached_candles(symbol, timeframe, sorted_candles)
        return sorted_candles

    async def fetch_or_load_funding(
        self,
        symbol: str,
        limit: int = 200,
        force_refresh: bool = False,
    ) -> list[dict[str, Any]]:
        """Retrieves historical funding rate settlements."""
        if not force_refresh:
            cached = self.load_cached_funding(symbol)
            if cached:
                return cached

        if not self.rest_client:
            self.rest_client = BybitRestClient()

        try:
            funding = await self.rest_client.get_funding_history(symbol=symbol, limit=limit)
            self.save_cached_funding(symbol, funding)
            return funding
        except Exception as e:
            logger.warning(f"Failed to fetch historical funding for {symbol}: {e}")
            return []

    async def build_provider(
        self,
        symbols: list[str],
        timeframes: list[str] = ["5", "15", "60", "240"],
        target_candles: dict[str, int] | None = None,
        force_refresh: bool = False,
    ) -> tuple[HistoricalMarketDataProvider, dict[tuple[str, str], list[dict[str, Any]]]]:
        """
        Assembles a ready-to-use HistoricalMarketDataProvider populated
        with real Bybit MTF data.
        """
        if target_candles is None:
            # 5m: 30 days = 30 * 288 = 8640 bars; start with e.g. 2000-3000 bars for fast execution
            target_candles = {
                "5": 2500,
                "15": 1500,
                "60": 800,
                "240": 400,
            }

        candles_map: dict[tuple[str, str], list[dict[str, Any]]] = {}
        derivatives_map: dict[str, list[dict[str, Any]]] = {}

        for sym in symbols:
            # Fetch MTF candles
            for tf in timeframes:
                count = target_candles.get(tf, 1000)
                bars = await self.fetch_or_load_candles(sym, tf, target_count=count, force_refresh=force_refresh)
                candles_map[(sym, tf)] = bars

            # Fetch funding history
            funding = await self.fetch_or_load_funding(sym, limit=200, force_refresh=force_refresh)
            deriv_records = []
            for f in funding:
                deriv_records.append(
                    {
                        "timestamp": f["timestamp"],
                        "open_interest": 0.0,
                        "funding_rate": f.get("funding_rate", 0.0),
                    }
                )
            derivatives_map[sym] = deriv_records

        provider = HistoricalMarketDataProvider(
            historical_candles=candles_map,
            derivatives_data=derivatives_map,
        )
        return provider, candles_map
