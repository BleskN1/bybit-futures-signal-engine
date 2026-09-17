"""Market Data Provider abstraction separating Live and Historical backtest environments."""

from abc import ABC, abstractmethod
from collections import defaultdict, deque
from typing import Any

from app.utils.logging import setup_logger

logger = setup_logger("signal_engine.provider")


TIMEFRAME_DURATIONS_MS = {
    "1": 60 * 1000,
    "3": 3 * 60 * 1000,
    "5": 5 * 60 * 1000,
    "15": 15 * 60 * 1000,
    "30": 30 * 60 * 1000,
    "60": 60 * 60 * 1000,
    "120": 120 * 60 * 1000,
    "240": 240 * 60 * 1000,
    "D": 24 * 60 * 60 * 1000,
    "d": 24 * 60 * 60 * 1000,
    "W": 7 * 24 * 60 * 60 * 1000,
    "w": 7 * 24 * 60 * 60 * 1000,
}


class MarketDataProvider(ABC):
    """Abstract interface for accessing market and derivative data without lookahead bias."""

    @abstractmethod
    def get_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 200,
        as_of: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Retrieves closed candlestick bars strictly chronologically ordered (oldest -> newest).
        If as_of (UTC epoch ms) is provided, guarantees only data <= as_of is returned.
        """

    @abstractmethod
    def get_latest_price(self, symbol: str, as_of: int | None = None) -> float:
        """Returns latest known market price at or before as_of timestamp."""

    @abstractmethod
    def get_derivatives(self, symbol: str, as_of: int | None = None) -> dict[str, Any]:
        """Returns derivative snapshot (raw OI, funding rate, LS ratio) at or before as_of."""


class LiveMarketDataProvider(MarketDataProvider):
    """
    Live real-time provider maintaining in-memory bounded ring buffers for active symbols.
    Provides fast O(1) reads without disk I/O latency.
    """

    def __init__(self, max_buffer_size: int = 2500):
        self.max_buffer_size = max_buffer_size
        # Key: (symbol, timeframe) -> deque of closed candle dicts
        self._candle_buffers: dict[tuple[str, str], deque[dict[str, Any]]] = defaultdict(
            lambda: deque(maxlen=self.max_buffer_size)
        )
        # Key: symbol -> latest ticker info {last_price, bid1, ask1, open_interest, funding_rate, timestamp}
        self._tickers: dict[str, dict[str, Any]] = {}
        # Key: symbol -> deque of derivative history snapshots {timestamp, open_interest, funding_rate}
        self._derivatives_history: dict[str, deque[dict[str, Any]]] = defaultdict(
            lambda: deque(maxlen=500)
        )

    def update_candle(self, symbol: str, timeframe: str, candle: dict[str, Any]) -> bool:
        """
        Inserts or updates a candle.
        Only closed candles (is_closed == True) are appended to historical analysis buffer.
        Returns True if a new closed candle was finalized.
        """
        buf = self._candle_buffers[(symbol, timeframe)]
        if not candle.get("is_closed", False):
            return False

        ts = candle["timestamp"]
        # Check if candle with this timestamp already exists in buffer (update if so)
        if buf and buf[-1]["timestamp"] == ts:
            buf[-1] = candle
            return False
        elif buf and buf[-1]["timestamp"] > ts:
            # Out-of-order historical backfill: re-sort
            buf.append(candle)
            sorted_candles = sorted(buf, key=lambda c: c["timestamp"])
            self._candle_buffers[(symbol, timeframe)] = deque(sorted_candles, maxlen=self.max_buffer_size)
            return True
        else:
            buf.append(candle)
            return True

    def bootstrap_candles(self, symbol: str, timeframe: str, candles: list[dict[str, Any]]) -> None:
        """Loads initial historical candles (chronological order) into the buffer."""
        buf = self._candle_buffers[(symbol, timeframe)]
        buf.clear()
        for c in candles:
            if c.get("is_closed", True):
                buf.append(c)
        logger.debug(f"Loaded {len(buf)} bootstrap candles into buffer for {symbol} TF={timeframe}")

    # Compatibility alias
    load_bootstrap_candles = bootstrap_candles

    def update_ticker(self, symbol: str, ticker_data: dict[str, Any]) -> None:
        """Updates real-time ticker information with single-counted Open Interest standardization."""
        existing = self._tickers.get(symbol, {})
        last_price = float(ticker_data.get("lastPrice") or existing.get("last_price", 0.0))

        raw_oi = float(ticker_data.get("openInterest") or existing.get("raw_open_interest", 0.0))
        # Bybit tickers provide bilateral OI (raw_oi).
        # Align with historical methodology: if history is single-counted (~half of raw_oi), scale by 0.5
        if "single_open_interest" in ticker_data:
            oi = float(ticker_data["single_open_interest"])
        elif "open_interest" in ticker_data:
            oi = float(ticker_data["open_interest"])
        elif raw_oi > 0:
            hist = self._derivatives_history.get(symbol)
            if hist and len(hist) > 0:
                last_hist_oi = float(hist[-1].get("open_interest", 0.0))
                # If raw_oi is approximately double the historical single-counted OI:
                if last_hist_oi > 0 and raw_oi > (1.6 * last_hist_oi):
                    oi = raw_oi / 2.0
                else:
                    oi = raw_oi
            else:
                oi = raw_oi
        else:
            oi = existing.get("open_interest", 0.0)

        fr = float(ticker_data.get("fundingRate") or existing.get("funding_rate", 0.0))
        ts = int(ticker_data.get("timestamp") or (ticker_data.get("time") or 0))

        updated = {
            "last_price": last_price,
            "open_interest": oi,
            "single_open_interest": oi,
            "raw_open_interest": raw_oi,
            "funding_rate": fr,
            "timestamp": ts,
            "bid1": float(ticker_data.get("bid1Price") or existing.get("bid1", last_price)),
            "ask1": float(ticker_data.get("ask1Price") or existing.get("ask1", last_price)),
        }
        self._tickers[symbol] = updated

        if oi > 0 or fr != 0.0:
            self._derivatives_history[symbol].append({
                "timestamp": ts,
                "open_interest": oi,
                "single_open_interest": oi,
                "raw_open_interest": raw_oi,
                "funding_rate": fr,
            })

    def get_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 200,
        as_of: int | None = None,
    ) -> list[dict[str, Any]]:
        buf = self._candle_buffers[(symbol, timeframe)]
        if not buf:
            return []

        if as_of is None:
            candles = list(buf)
        else:
            dur = TIMEFRAME_DURATIONS_MS.get(timeframe) or (int(timeframe) * 60 * 1000 if timeframe.isdigit() else 300000)
            # Strictly prevent lookahead bias: only return candles whose full bar has closed at or before as_of
            candles = [
                c for c in buf
                if (c.get("close_time") or (c["timestamp"] + (dur if c["timestamp"] > dur else 0))) <= as_of
            ]

        return candles[-limit:]

    def get_latest_price(self, symbol: str, as_of: int | None = None) -> float:
        ticker = self._tickers.get(symbol)
        if ticker and ticker.get("last_price", 0.0) > 0:
            if as_of is None or ticker.get("timestamp", 0) <= as_of:
                return ticker["last_price"]

        # Fallback to the latest closed 5m candle close price
        candles_5m = self.get_candles(symbol, "5", limit=1, as_of=as_of)
        if candles_5m:
            return candles_5m[-1]["close"]
        return 0.0

    def get_derivatives(self, symbol: str, as_of: int | None = None) -> dict[str, Any]:
        ticker = self._tickers.get(symbol, {})
        history = list(self._derivatives_history.get(symbol, []))

        if as_of is not None:
            history = [h for h in history if h["timestamp"] <= as_of]

        latest_record = history[-1] if history else {}
        return {
            "open_interest": latest_record.get("open_interest", ticker.get("open_interest", 0.0)),
            "funding_rate": latest_record.get("funding_rate", ticker.get("funding_rate", 0.0)),
            "history": history,
        }
