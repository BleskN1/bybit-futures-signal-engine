"""Bybit V5 REST API Client with pagination, rate limiting, and exponential retry."""

import asyncio
from typing import Any

import httpx

from app.utils.logging import setup_logger
from app.utils.rate_limiter import AsyncTokenBucketRateLimiter
from app.utils.retry import async_retry

logger = setup_logger("signal_engine.rest")


class BybitRestClient:
    """Async Bybit V5 REST Client supporting linear USDT perpetuals."""

    def __init__(
        self,
        base_url: str = "https://api.bybit.com",
        api_key: str = "",
        api_secret: str = "",
        requests_per_second: float = 10.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.api_secret = api_secret
        self.rate_limiter = AsyncTokenBucketRateLimiter(rate=requests_per_second, capacity=requests_per_second * 2)
        self._client: httpx.AsyncClient | None = None

    async def get_client(self) -> httpx.AsyncClient:
        """Returns or creates the underlying httpx.AsyncClient."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(10.0, connect=5.0),
                headers={"Content-Type": "application/json", "User-Agent": "BybitSignalEngine/1.0"},
            )
        return self._client

    async def close(self) -> None:
        """Closes the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    @async_retry(max_retries=4, initial_delay=0.5, backoff_factor=2.0)
    async def _get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Internal GET request wrapper with token bucket rate limiting and error validation."""
        await self.rate_limiter.acquire()
        client = await self.get_client()

        response = await client.get(endpoint, params=params)
        if response.status_code == 429:
            retry_after = float(response.headers.get("Retry-After", "2.0"))
            logger.warning(f"Rate limited (HTTP 429) on {endpoint}. Sleeping {retry_after}s...")
            await asyncio.sleep(retry_after)
            response.raise_for_status()

        response.raise_for_status()
        data = response.json()

        ret_code = data.get("retCode", 0)
        if ret_code != 0:
            err_msg = data.get("retMsg", "Unknown Bybit API Error")
            # Handle rate limit retCode 10006
            if ret_code == 10006:
                logger.warning(f"Bybit IP rate limit hit ({err_msg}). Backing off...")
                await asyncio.sleep(3.0)
            raise ValueError(f"Bybit API error code {ret_code}: {err_msg}")

        return data.get("result", {})

    async def get_instruments_info(self, category: str = "linear") -> list[dict[str, Any]]:
        """
        Retrieves all linear instruments with automatic cursor pagination.
        Filters will later be applied in the universe ranking selector.
        """
        all_instruments: list[dict[str, Any]] = []
        cursor: str | None = None

        while True:
            params: dict[str, Any] = {"category": category, "limit": 1000, "status": "Trading"}
            if cursor:
                params["cursor"] = cursor

            result = await self._get("/v5/market/instruments-info", params=params)
            instruments = result.get("list", [])
            all_instruments.extend(instruments)

            cursor = result.get("nextPageCursor")
            if not cursor or not instruments:
                break

        logger.info(f"Fetched total {len(all_instruments)} active instruments for category '{category}'")
        return all_instruments

    async def get_tickers(self, category: str = "linear") -> list[dict[str, Any]]:
        """Retrieves 24h ticker snapshots for all symbols in the category."""
        result = await self._get("/v5/market/tickers", params={"category": category})
        tickers = result.get("list", [])
        return tickers

    async def get_klines(
        self,
        symbol: str,
        interval: str,
        limit: int = 200,
        start_time: int | None = None,
        end_time: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Fetches up to 200 kline bars for a single request.
        Bybit V5 returns bars ordered from newest to oldest:
        [startTime, openPrice, highPrice, lowPrice, closePrice, volume, turnover]
        """
        params: dict[str, Any] = {
            "category": "linear",
            "symbol": symbol,
            "interval": interval,
            "limit": min(limit, 200),
        }
        if start_time is not None:
            params["start"] = start_time
        if end_time is not None:
            params["end"] = end_time

        result = await self._get("/v5/market/kline", params=params)
        raw_list = result.get("list", [])

        # Parse into standardized dict format
        parsed_bars: list[dict[str, Any]] = []
        for bar in raw_list:
            # bar: [startTime, openPrice, highPrice, lowPrice, closePrice, volume, turnover]
            parsed_bars.append(
                {
                    "timestamp": int(bar[0]),
                    "open": float(bar[1]),
                    "high": float(bar[2]),
                    "low": float(bar[3]),
                    "close": float(bar[4]),
                    "volume": float(bar[5]),
                    "turnover": float(bar[6]),
                    "is_closed": True,
                }
            )

        # Reverse to chronological order (oldest -> newest)
        parsed_bars.sort(key=lambda x: x["timestamp"])
        return parsed_bars

    async def get_historical_klines_paginated(
        self,
        symbol: str,
        interval: str,
        total_candles: int = 2000,
    ) -> list[dict[str, Any]]:
        """
        Paginates backwards in time to fetch the required number of historical closed candles.
        Guarantees minimum lookback depth (e.g. 2000 bars) without look-ahead bias.
        """
        collected_bars: dict[int, dict[str, Any]] = {}
        batch_size = 200
        end_time: int | None = None
        max_pages = (total_candles // batch_size) + 5

        for page in range(max_pages):
            if len(collected_bars) >= total_candles:
                break

            bars = await self.get_klines(
                symbol=symbol,
                interval=interval,
                limit=batch_size,
                end_time=end_time,
            )

            if not bars:
                break

            new_added = 0
            for bar in bars:
                if bar["timestamp"] not in collected_bars:
                    collected_bars[bar["timestamp"]] = bar
                    new_added += 1

            if new_added == 0:
                # No more older data available from exchange
                break

            # Set end_time for the next page to the earliest timestamp minus 1 ms
            earliest_ts = min(collected_bars.keys())
            end_time = earliest_ts - 1

            # Brief pause to respect rate limits gracefully during deep bootstrap
            await asyncio.sleep(0.05)

        sorted_bars = sorted(collected_bars.values(), key=lambda x: x["timestamp"])
        logger.info(
            f"Bootstrapped {len(sorted_bars)} candles for {symbol} TF={interval} "
            f"(target: {total_candles}, oldest: {sorted_bars[0]['timestamp'] if sorted_bars else 'N/A'})"
        )
        return sorted_bars[-total_candles:]

    async def get_open_interest(
        self,
        symbol: str,
        interval_time: str = "5min",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Fetches historical raw Open Interest records.
        """
        params = {
            "category": "linear",
            "symbol": symbol,
            "intervalTime": interval_time,
            "limit": min(limit, 200),
        }
        result = await self._get("/v5/market/open-interest", params=params)
        raw_list = result.get("list", [])
        records = []
        for item in raw_list:
            raw_oi = float(item["openInterest"])
            # Bybit V5 OI Methodology:
            # Effective June 11, 2026, Bybit reports single-counted Open Interest via 'singleOpenInterest'.
            # 'openInterest' remains bilateral (double-counted: buyer + seller contracts).
            # If singleOpenInterest is provided by the endpoint, standardize on single-counted OI.
            if "singleOpenInterest" in item and item["singleOpenInterest"] is not None:
                single_oi = float(item["singleOpenInterest"])
            else:
                single_oi = raw_oi

            records.append(
                {
                    "timestamp": int(item["timestamp"]),
                    "open_interest": single_oi,
                    "single_open_interest": single_oi,
                    "bilateral_open_interest": raw_oi,
                }
            )
        records.sort(key=lambda x: x["timestamp"])
        return records

    async def get_funding_history(self, symbol: str, limit: int = 50) -> list[dict[str, Any]]:
        """Fetches historical funding rate settlements."""
        params = {
            "category": "linear",
            "symbol": symbol,
            "limit": min(limit, 200),
        }
        result = await self._get("/v5/market/funding/history", params=params)
        raw_list = result.get("list", [])
        records = []
        for item in raw_list:
            records.append(
                {
                    "timestamp": int(item["fundingRateTimestamp"]),
                    "funding_rate": float(item["fundingRate"]),
                }
            )
        records.sort(key=lambda x: x["timestamp"])
        return records

    async def get_long_short_ratio(
        self,
        symbol: str,
        period: str = "5min",
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Fetches historical account long/short ratio if available for the symbol."""
        params = {
            "category": "linear",
            "symbol": symbol,
            "period": period,
            "limit": min(limit, 200),
        }
        try:
            result = await self._get("/v5/market/account-ratio", params=params)
            raw_list = result.get("list", [])
            records = []
            for item in raw_list:
                records.append(
                    {
                        "timestamp": int(item["timestamp"]),
                        "buy_ratio": float(item["buyRatio"]),
                        "sell_ratio": float(item["sellRatio"]),
                        "long_short_ratio": float(item["buyRatio"]) / max(float(item["sellRatio"]), 0.0001),
                    }
                )
            records.sort(key=lambda x: x["timestamp"])
            return records
        except Exception as e:
            logger.debug(f"Long/short ratio not available for {symbol}: {e}")
            return []
