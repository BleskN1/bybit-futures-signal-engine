"""Historical Market Data Provider for backtesting and historical replay."""

from typing import Any

from app.market_data.provider import MarketDataProvider, TIMEFRAME_DURATIONS_MS


class HistoricalMarketDataProvider(MarketDataProvider):
    """
    Historical provider loading immutable datasets for backtesting without lookahead bias.
    """

    def __init__(
        self,
        historical_candles: dict[tuple[str, str], list[dict[str, Any]]],
        derivatives_data: dict[str, list[dict[str, Any]]] | None = None,
    ):
        """
        Args:
            historical_candles: Map of (symbol, timeframe) -> sorted list of candle dicts.
            derivatives_data: Map of symbol -> sorted list of derivative snapshots.
        """
        self._candles = {k: sorted(v, key=lambda x: x["timestamp"]) for k, v in historical_candles.items()}
        self._derivatives = {
            k: sorted(v, key=lambda x: x["timestamp"]) for k, v in (derivatives_data or {}).items()
        }

    def get_candles(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 200,
        as_of: int | None = None,
    ) -> list[dict[str, Any]]:
        all_bars = self._candles.get((symbol, timeframe), [])
        if as_of is not None:
            dur = TIMEFRAME_DURATIONS_MS.get(timeframe) or (int(timeframe) * 60 * 1000 if timeframe.isdigit() else 300000)
            # Strictly filtering bars not yet closed at as_of
            valid_bars = [
                b for b in all_bars
                if (b.get("close_time") or (b["timestamp"] + (dur if b["timestamp"] > dur else 0))) <= as_of
            ]
        else:
            valid_bars = all_bars

        return valid_bars[-limit:]

    def get_latest_price(self, symbol: str, as_of: int | None = None) -> float:
        bars = self.get_candles(symbol, "5", limit=1, as_of=as_of)
        if bars:
            return bars[-1]["close"]
        return 0.0

    def get_derivatives(self, symbol: str, as_of: int | None = None) -> dict[str, Any]:
        records = self._derivatives.get(symbol, [])
        if as_of is not None:
            records = [r for r in records if r["timestamp"] <= as_of]

        if not records:
            return {"open_interest": 0.0, "funding_rate": 0.0, "history": []}

        latest = records[-1]
        return {
            "open_interest": latest.get("open_interest", 0.0),
            "funding_rate": latest.get("funding_rate", 0.0),
            "history": records,
        }
