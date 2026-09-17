"""Signal Scorer synthesizing component factor evaluations into an overarching signal decision."""

from typing import Any, Literal

from app.signal.models import ComponentScore, SignalStatus
from app.signal.mtf import MTFContext


class SignalScorer:
    """
    Combines deterministic component scores using configurable weights.
    Maintains complete mathematical independence between LONG and SHORT scores.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        cfg = config or {}
        scoring_cfg = cfg.get("scoring", cfg)

        # Normalize weights
        raw_weights = scoring_cfg.get("weights", {
            "htf_trend": 0.15,
            "market_structure": 0.15,
            "liquidity": 0.15,
            "momentum": 0.10,
            "volume": 0.10,
            "volatility": 0.05,
            "derivatives": 0.15,
            "price_action": 0.15,
        })
        total_w = sum(raw_weights.values())
        if total_w > 0:
            self.weights = {k: v / total_w for k, v in raw_weights.items()}
        else:
            self.weights = raw_weights

        thresholds = scoring_cfg.get("thresholds", {})
        self.watch_threshold = float(thresholds.get("watch", thresholds.get("watch_min", 60.0)))
        self.signal_threshold = float(thresholds.get("signal", thresholds.get("signal_min", 75.0)))
        self.strong_threshold = float(thresholds.get("strong_signal", thresholds.get("strong_signal_min", 85.0)))
        self.min_directional_edge = float(
            scoring_cfg.get("min_directional_edge", thresholds.get("min_directional_edge", 5.0))
        )

        regime_cfg = scoring_cfg.get("regime", {})
        self.allow_choppy = regime_cfg.get("allow_choppy", False)
        self.allow_counter_trend = regime_cfg.get("allow_counter_trend", True)
        self.counter_trend_max_score = float(regime_cfg.get("counter_trend_max_score", 75.0))

    def evaluate(
        self,
        component_scores: dict[str, ComponentScore],
        mtf: MTFContext,
    ) -> tuple[Literal["LONG", "SHORT"], float, float, float, SignalStatus, list[str]]:
        """
        Calculates total LONG and SHORT scores independently and assigns signal status.

        Returns:
            (primary_direction, long_score, short_score, directional_edge, status, aggregated_penalties)
        """
        long_weighted_sum = 0.0
        short_weighted_sum = 0.0
        all_penalties: list[str] = list(mtf.penalties)

        for name, comp in component_scores.items():
            w = self.weights.get(name, comp.weight)
            long_weighted_sum += comp.long_score * w
            short_weighted_sum += comp.short_score * w
            all_penalties.extend(comp.penalties)

        long_score = min(max(long_weighted_sum, 0.0), 100.0)
        short_score = min(max(short_weighted_sum, 0.0), 100.0)

        directional_edge = abs(long_score - short_score)
        direction: Literal["LONG", "SHORT"] = "LONG" if long_score >= short_score else "SHORT"
        primary_score = long_score if direction == "LONG" else short_score

        # Counter-trend haircut / cap
        if mtf.is_counter_trend:
            if not self.allow_counter_trend:
                primary_score = min(primary_score, self.watch_threshold - 1.0)
            else:
                primary_score = min(primary_score, self.counter_trend_max_score)

            if direction == "LONG":
                long_score = primary_score
            else:
                short_score = primary_score

        # Status categorization
        if primary_score >= self.strong_threshold:
            status = SignalStatus.STRONG_SIGNAL
        elif primary_score >= self.signal_threshold:
            status = SignalStatus.SIGNAL
        elif primary_score >= self.watch_threshold:
            status = SignalStatus.WATCH
        else:
            status = SignalStatus.IGNORE

        return (
            direction,
            round(long_score, 2),
            round(short_score, 2),
            round(directional_edge, 2),
            status,
            list(set(all_penalties)),
        )
