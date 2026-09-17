"""Dynamic Universe Ranking and Selection for USDT Perpetual Contracts."""

from typing import Any

from app.market_data.rest import BybitRestClient
from app.utils.logging import setup_logger

logger = setup_logger("signal_engine.ranking")


class UniverseSelector:
    """Selects and ranks top USDT perpetual pairs using a multi-factor liquidity & quality model."""

    def __init__(self, rest_client: BybitRestClient, ranking_config: dict[str, Any] | None = None):
        self.rest_client = rest_client
        cfg = ranking_config or {}
        self.weights = cfg.get("weights", {
            "turnover_24h": 0.35,
            "open_interest": 0.25,
            "volume_24h": 0.15,
            "volatility": 0.10,
            "trades_activity": 0.10,
            "spread_penalty": 0.05,
        })
        self.filters = cfg.get("filters", {
            "min_turnover_24h_usdt": 10000000.0,
            "min_open_interest_usdt": 2000000.0,
            "max_bid_ask_spread_pct": 0.0015,
            "quote_coin": "USDT",
            "contract_status": "Trading",
        })

    async def select_top_symbols(self, top_n: int = 20) -> list[dict[str, Any]]:
        """
        Executes multi-factor ranking across all linear Bybit instruments and returns TOP_N candidates.
        """
        instruments = await self.rest_client.get_instruments_info(category="linear")
        tickers = await self.rest_client.get_tickers(category="linear")

        # Map tickers by symbol
        ticker_map: dict[str, dict[str, Any]] = {t.get("symbol", ""): t for t in tickers}

        quote_coin = self.filters.get("quote_coin", "USDT")
        status_req = self.filters.get("contract_status", "Trading")

        candidates: list[dict[str, Any]] = []

        for inst in instruments:
            symbol = inst.get("symbol", "")
            if not symbol.endswith(quote_coin):
                continue
            if inst.get("status") != status_req:
                continue
            if inst.get("contractType") != "LinearPerpetual":
                continue

            ticker = ticker_map.get(symbol)
            if not ticker:
                continue

            try:
                turnover_24h = float(ticker.get("turnover24h", 0.0) or 0.0)
                volume_24h = float(ticker.get("volume24h", 0.0) or 0.0)
                last_price = float(ticker.get("lastPrice", 0.0) or 0.0)
                high_24h = float(ticker.get("highPrice24h", 0.0) or 0.0)
                low_24h = float(ticker.get("lowPrice24h", 0.0) or 0.0)
                open_interest = float(ticker.get("openInterest", 0.0) or 0.0)
                open_interest_value = float(ticker.get("openInterestValue", 0.0) or (open_interest * last_price))

                bid1 = float(ticker.get("bid1Price", 0.0) or 0.0)
                ask1 = float(ticker.get("ask1Price", 0.0) or 0.0)
            except (ValueError, TypeError):
                continue

            if last_price <= 0:
                continue

            # Bid/ask spread calculation
            spread_pct = (ask1 - bid1) / last_price if (ask1 > 0 and bid1 > 0) else 0.0005

            # Apply hard filtering gates
            min_turnover = float(self.filters.get("min_turnover_24h_usdt", 10000000.0))
            if turnover_24h < min_turnover:
                continue

            min_oi = float(self.filters.get("min_open_interest_usdt", 2000000.0))
            if open_interest_value < min_oi:
                continue

            max_spread = float(self.filters.get("max_bid_ask_spread_pct", 0.0015))
            if spread_pct > max_spread:
                continue

            # Volatility: 24h price range percentage
            volatility_pct = (high_24h - low_24h) / max(low_24h, 0.00001)

            # Activity proxy: turnover vs price volume ratio
            trades_activity = turnover_24h / max(last_price * volume_24h, 1.0)

            candidates.append({
                "symbol": symbol,
                "last_price": last_price,
                "turnover_24h": turnover_24h,
                "volume_24h": volume_24h,
                "open_interest_value": open_interest_value,
                "volatility_pct": volatility_pct,
                "spread_pct": spread_pct,
                "trades_activity": trades_activity,
                "tick_size": inst.get("priceFilter", {}).get("tickSize", "0.01"),
                "lot_size": inst.get("lotSizeFilter", {}).get("qtyStep", "0.001"),
            })

        if not candidates:
            logger.warning("No instruments passed strict filters! Falling back to raw turnover ranking.")
            # Fallback with relaxed filters
            for inst in instruments:
                symbol = inst.get("symbol", "")
                if symbol.endswith("USDT") and inst.get("status") == "Trading":
                    ticker = ticker_map.get(symbol, {})
                    turnover = float(ticker.get("turnover24h", 0) or 0)
                    if turnover > 1000000:
                        candidates.append({
                            "symbol": symbol,
                            "last_price": float(ticker.get("lastPrice", 0) or 1.0),
                            "turnover_24h": turnover,
                            "volume_24h": float(ticker.get("volume24h", 0) or 0),
                            "open_interest_value": float(ticker.get("openInterestValue", 0) or 0),
                            "volatility_pct": 0.05,
                            "spread_pct": 0.0005,
                            "trades_activity": 1.0,
                            "tick_size": "0.01",
                            "lot_size": "0.001",
                        })

        # Min-Max Normalization helper
        def normalize(values: list[float]) -> list[float]:
            min_v = min(values)
            max_v = max(values)
            diff = max_v - min_v
            if diff <= 0:
                return [1.0] * len(values)
            return [(v - min_v) / diff for v in values]

        turnovers = [c["turnover_24h"] for c in candidates]
        volumes = [c["volume_24h"] for c in candidates]
        ois = [c["open_interest_value"] for c in candidates]
        volatilities = [c["volatility_pct"] for c in candidates]
        activities = [c["trades_activity"] for c in candidates]
        spreads = [c["spread_pct"] for c in candidates]

        norm_turnover = normalize(turnovers)
        norm_volume = normalize(volumes)
        norm_oi = normalize(ois)
        norm_volatility = normalize(volatilities)
        norm_activity = normalize(activities)
        norm_spread = normalize(spreads)

        w_turnover = float(self.weights.get("turnover_24h", 0.35))
        w_oi = float(self.weights.get("open_interest", 0.25))
        w_volume = float(self.weights.get("volume_24h", 0.15))
        w_volatility = float(self.weights.get("volatility", 0.10))
        w_activity = float(self.weights.get("trades_activity", 0.10))
        w_spread = float(self.weights.get("spread_penalty", 0.05))

        for idx, item in enumerate(candidates):
            score = (
                w_turnover * norm_turnover[idx]
                + w_oi * norm_oi[idx]
                + w_volume * norm_volume[idx]
                + w_volatility * norm_volatility[idx]
                + w_activity * norm_activity[idx]
                - w_spread * norm_spread[idx]
            )
            item["ranking_score"] = round(score * 100, 2)

        # Sort descending by composite ranking score
        candidates.sort(key=lambda x: x["ranking_score"], reverse=True)
        top_candidates = candidates[:top_n]

        for rank, c in enumerate(top_candidates, 1):
            c["rank"] = rank

        logger.info(
            f"Successfully ranked {len(candidates)} pairs. Selected TOP {len(top_candidates)}: "
            f"{[c['symbol'] for c in top_candidates[:8]]}..."
        )
        return top_candidates
