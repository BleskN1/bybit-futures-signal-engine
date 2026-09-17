"""Deterministic Hard Filter Pipeline for Signal Qualification."""

from dataclasses import dataclass
from typing import Any

from app.analysis.models import MarketRegime
from app.signal import explanation as exp
from app.signal.models import SignalCandidate, SignalStatus
from app.signal.mtf import MTFContext


@dataclass
class FilterResult:
    passed: bool
    filter_name: str
    rejection_reason: str | None = None


class SignalFilterPipeline:
    """
    Executes sequential gate filters to prevent false positives, low-quality setups,
    and lookahead/stale data leaks.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        cfg = config or {}
        scoring_cfg = cfg.get("scoring", cfg)

        thresholds = scoring_cfg.get("thresholds", {})
        self.signal_min_score = float(thresholds.get("signal", thresholds.get("signal_min", 75.0)))
        self.watch_min_score = float(thresholds.get("watch", thresholds.get("watch_min", 60.0)))
        self.min_directional_edge = float(
            scoring_cfg.get("min_directional_edge", thresholds.get("min_directional_edge", 5.0))
        )

        risk_cfg = scoring_cfg.get("risk", {})
        self.min_rr_tp1 = float(risk_cfg.get("min_rr_tp1", 1.5))

        regime_cfg = scoring_cfg.get("regime", {})
        self.allow_choppy = regime_cfg.get("allow_choppy", False)

        cooldown_cfg = scoring_cfg.get("cooldown", {})
        self.cooldown_ms = int(cooldown_cfg.get("minutes", 20)) * 60 * 1000

        # In-memory tracking for cooldowns: (symbol, direction) -> last_signal_timestamp_ms
        self._last_signal_time: dict[tuple[str, str], int] = {}

    def check_readiness(self, mtf: MTFContext) -> FilterResult:
        """Filter 1: Verifies all timeframes are warmed up and valid."""
        if not mtf.is_ready:
            return FilterResult(
                passed=False,
                filter_name="DataReadiness",
                rejection_reason="Insufficient warmup bars or incomplete indicators across timeframes",
            )
        return FilterResult(passed=True, filter_name="DataReadiness")

    def check_directional_edge(self, directional_edge: float) -> FilterResult:
        """Filter 2: Ensures clear divergence between LONG and SHORT scores."""
        if directional_edge < self.min_directional_edge:
            return FilterResult(
                passed=False,
                filter_name="DirectionalEdge",
                rejection_reason=f"Directional edge {directional_edge:.1f} is below minimum {self.min_directional_edge:.1f}",
            )
        return FilterResult(passed=True, filter_name="DirectionalEdge")

    def check_score_threshold(self, score: float, allow_watch: bool = False) -> FilterResult:
        """Filter 3: Requires minimum score qualification."""
        threshold = self.watch_min_score if allow_watch else self.signal_min_score
        if score < threshold:
            return FilterResult(
                passed=False,
                filter_name="ScoreThreshold",
                rejection_reason=f"Score {score:.1f} is below qualification threshold {threshold:.1f}",
            )
        return FilterResult(passed=True, filter_name="ScoreThreshold")

    def check_market_regime(self, mtf: MTFContext) -> FilterResult:
        """Filter 4: Suppresses setups during choppy / directionless compression."""
        regime = mtf.m15.structure.regime if mtf.m15.structure else MarketRegime.NORMAL
        if regime == MarketRegime.CONSOLIDATION and not self.allow_choppy:
            # Check if BB bandwidth indicates severe chop
            bw = mtf.m15.indicators.bb_bandwidth if mtf.m15.indicators else 0.05
            if bw is not None and bw < 0.02:
                return FilterResult(
                    passed=False,
                    filter_name="MarketRegime",
                    rejection_reason="Market is in dead consolidation / low-volatility chop",
                )
        return FilterResult(passed=True, filter_name="MarketRegime")

    def check_risk_reward(self, rr_tp1: float) -> FilterResult:
        """Filter 5: Enforces positive expectancy risk-reward ratio."""
        if rr_tp1 < self.min_rr_tp1:
            return FilterResult(
                passed=False,
                filter_name="RiskReward",
                rejection_reason=f"Risk/Reward TP1 {rr_tp1:.2f} is below minimum {self.min_rr_tp1:.2f}",
            )
        return FilterResult(passed=True, filter_name="RiskReward")

    def check_cooldown(self, symbol: str, direction: str, as_of: int) -> FilterResult:
        """Filter 6: Enforces anti-spam cooldown window per symbol and direction."""
        last_time = self._last_signal_time.get((symbol, direction))
        if last_time is not None:
            elapsed = as_of - last_time
            if elapsed < self.cooldown_ms:
                remaining_min = (self.cooldown_ms - elapsed) / 60000.0
                return FilterResult(
                    passed=False,
                    filter_name="Cooldown",
                    rejection_reason=f"Signal in cooldown ({remaining_min:.1f}m remaining)",
                )
        return FilterResult(passed=True, filter_name="Cooldown")

    def register_signal(self, candidate: SignalCandidate) -> None:
        """Registers qualified signal in cooldown tracker."""
        if candidate.signal_status in [SignalStatus.SIGNAL, SignalStatus.STRONG_SIGNAL]:
            self._last_signal_time[(candidate.symbol, candidate.direction)] = candidate.as_of_timestamp

    def reset_cooldown(self, symbol: str | None = None) -> None:
        """Resets cooldown tracker (useful for testing and new session starts)."""
        if symbol:
            keys = [k for k in self._last_signal_time if k[0] == symbol]
            for k in keys:
                del self._last_signal_time[k]
        else:
            self._last_signal_time.clear()
