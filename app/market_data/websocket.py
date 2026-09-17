"""Bybit V5 Public Linear WebSocket Client with automatic reconnection, heartbeats, and batching."""

import asyncio
import json
import random
from collections.abc import Callable
from typing import Any

import websockets
from websockets.exceptions import ConnectionClosed

from app.utils.logging import setup_logger

logger = setup_logger("signal_engine.websocket")


class BybitWsClient:
    """Production-grade Bybit V5 WebSocket client for Linear USDT Perpetuals."""

    def __init__(
        self,
        ws_url: str = "wss://stream.bybit.com/v5/public/linear",
        ping_interval: float = 20.0,
    ):
        self.ws_url = ws_url
        self.ping_interval = ping_interval
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._subscribed_topics: set[str] = set()
        self._is_running = False
        self._receive_task: asyncio.Task | None = None
        self._ping_task: asyncio.Task | None = None

        # Registered Event Handlers: Callable[[dict], Coroutine]
        self._kline_handlers: list[Callable[[str, str, dict[str, Any]], Any]] = []
        self._ticker_handlers: list[Callable[[str, dict[str, Any]], Any]] = []
        self._liquidation_handlers: list[Callable[[str, dict[str, Any]], Any]] = []

    def on_kline(self, handler: Callable[[str, str, dict[str, Any]], Any]) -> None:
        """Register handler for kline updates: handler(symbol, interval, candle_dict)."""
        self._kline_handlers.append(handler)

    def on_ticker(self, handler: Callable[[str, dict[str, Any]], Any]) -> None:
        """Register handler for ticker updates: handler(symbol, ticker_dict)."""
        self._ticker_handlers.append(handler)

    def on_liquidation(self, handler: Callable[[str, dict[str, Any]], Any]) -> None:
        """Register handler for public liquidations: handler(symbol, liq_dict)."""
        self._liquidation_handlers.append(handler)

    async def start(self) -> None:
        """Starts the WebSocket connection and background loops."""
        self._is_running = True
        self._receive_task = asyncio.create_task(self._connection_loop(), name="bybit_ws_loop")

    async def stop(self) -> None:
        """Gracefully stops the WebSocket client."""
        logger.info("Stopping Bybit WebSocket client...")
        self._is_running = False
        if self._ping_task and not self._ping_task.done():
            self._ping_task.cancel()
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
        if self._ws and not self._ws.closed:
            await self._ws.close()
        logger.info("Bybit WebSocket client successfully stopped.")

    async def subscribe(self, topics: list[str]) -> None:
        """Subscribes to topics in batches of 10 to respect Bybit limits."""
        for topic in topics:
            self._subscribed_topics.add(topic)

        if self._ws and self._ws.open:
            await self._send_subscriptions(topics)

    async def _send_subscriptions(self, topics: list[str]) -> None:
        """Sends subscription requests chunked by 10."""
        chunk_size = 10
        for i in range(0, len(topics), chunk_size):
            chunk = topics[i : i + chunk_size]
            payload = {"op": "subscribe", "args": chunk}
            try:
                if self._ws and self._ws.open:
                    await self._ws.send(json.dumps(payload))
                    logger.debug(f"Subscribed to topics chunk: {chunk}")
                    await asyncio.sleep(0.05)
            except Exception as e:
                logger.error(f"Failed to send subscription chunk {chunk}: {e}")

    async def _connection_loop(self) -> None:
        """Manages the persistent connection lifecycle with exponential backoff on disconnect."""
        backoff = 1.0
        max_backoff = 30.0

        while self._is_running:
            try:
                logger.info(f"Connecting to Bybit Public WebSocket: {self.ws_url}")
                async with websockets.connect(
                    self.ws_url,
                    ping_interval=None,  # We manage manual ping-pong as per Bybit V5 spec
                    close_timeout=5,
                ) as ws:
                    self._ws = ws
                    backoff = 1.0  # Reset backoff upon successful connection
                    logger.info("Bybit WebSocket connected successfully.")

                    # Start heartbeat task
                    self._ping_task = asyncio.create_task(self._ping_loop(), name="bybit_ws_ping")

                    # Resubscribe all active topics
                    if self._subscribed_topics:
                        logger.info(f"Resubscribing to {len(self._subscribed_topics)} topics...")
                        await self._send_subscriptions(list(self._subscribed_topics))

                    # Process incoming messages
                    async for message in ws:
                        if not self._is_running:
                            break
                        await self._handle_message(message)

            except (ConnectionClosed, asyncio.TimeoutError, OSError) as exc:
                if not self._is_running:
                    break
                jitter = random.uniform(0.8, 1.2)
                wait_time = min(backoff * jitter, max_backoff)
                logger.warning(
                    f"WebSocket disconnected ({type(exc).__name__}: {exc}). "
                    f"Reconnecting in {wait_time:.1f}s..."
                )
                await asyncio.sleep(wait_time)
                backoff = min(backoff * 1.5, max_backoff)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Unexpected WebSocket error: {exc}", exc_info=True)
                await asyncio.sleep(2.0)

    async def _ping_loop(self) -> None:
        """Sends Bybit V5 heartbeat ping every 20 seconds."""
        try:
            while self._is_running and self._ws and self._ws.open:
                await asyncio.sleep(self.ping_interval)
                ping_payload = {"op": "ping"}
                await self._ws.send(json.dumps(ping_payload))
                logger.debug("Sent WebSocket heartbeat ping.")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning(f"Error in WebSocket heartbeat loop: {e}")

    async def _handle_message(self, raw_message: str) -> None:
        """Parses, validates, and dispatches incoming WebSocket frames."""
        try:
            msg = json.loads(raw_message)
        except json.JSONDecodeError:
            logger.error(f"Malformed JSON received: {raw_message[:200]}")
            return

        # Handle system responses (pong, subscribe ack)
        if "op" in msg:
            op = msg.get("op")
            if op == "pong":
                logger.debug("Received WebSocket pong from Bybit.")
                return
            if op == "subscribe":
                success = msg.get("success", False)
                ret_msg = msg.get("ret_msg", "")
                if not success:
                    logger.error(f"Bybit WebSocket subscription rejected: {ret_msg} (args: {msg.get('req_id')})")
                return

        topic: str = msg.get("topic", "")
        data = msg.get("data")
        if not topic or data is None:
            return

        # 1. Kline stream: kline.{interval}.{symbol}
        if topic.startswith("kline."):
            parts = topic.split(".")
            if len(parts) >= 3:
                interval = parts[1]
                symbol = parts[2]
                candles = data if isinstance(data, list) else [data]
                for c in candles:
                    # Bybit V5 kline payload:
                    # {"start": 1672324800000, "end": 1672325099999, "interval": "5",
                    #  "open": "...", "close": "...", "high": "...", "low": "...",
                    #  "volume": "...", "turnover": "...", "confirm": true, "timestamp": ...}
                    candle_dict = {
                        "timestamp": int(c.get("start", 0)),
                        "open": float(c.get("open", 0.0)),
                        "high": float(c.get("high", 0.0)),
                        "low": float(c.get("low", 0.0)),
                        "close": float(c.get("close", 0.0)),
                        "volume": float(c.get("volume", 0.0)),
                        "turnover": float(c.get("turnover", 0.0)),
                        "is_closed": bool(c.get("confirm", False)),  # True = closed bar
                    }
                    for handler in self._kline_handlers:
                        try:
                            res = handler(symbol, interval, candle_dict)
                            if asyncio.iscoroutine(res):
                                asyncio.create_task(res)
                        except Exception as e:
                            logger.error(f"Error in kline handler for {symbol}: {e}")

        # 2. Tickers stream: tickers.{symbol}
        elif topic.startswith("tickers."):
            symbol = topic.split(".")[1]
            ticker_data = data if isinstance(data, dict) else (data[0] if data else {})
            for handler in self._ticker_handlers:
                try:
                    res = handler(symbol, ticker_data)
                    if asyncio.iscoroutine(res):
                        asyncio.create_task(res)
                except Exception as e:
                    logger.error(f"Error in ticker handler for {symbol}: {e}")

        # 3. Liquidation stream: allLiquidation.{symbol}
        elif topic.startswith("allLiquidation."):
            symbol = topic.split(".")[1]
            liquidations = data if isinstance(data, list) else [data]
            for liq in liquidations:
                for handler in self._liquidation_handlers:
                    try:
                        res = handler(symbol, liq)
                        if asyncio.iscoroutine(res):
                            asyncio.create_task(res)
                    except Exception as e:
                        logger.error(f"Error in liquidation handler for {symbol}: {e}")
