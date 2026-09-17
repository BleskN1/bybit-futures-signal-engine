"""Signal Scoring Engine orchestrating MTF features, component scoring, levels, and alerts."""

from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.database.repository import DatabaseRepository
from app.market_data.provider import MarketDataProvider
from app.signal import explanation as exp
from app.signal.components import (
    DerivativesScorer,
    HTFTrendScorer,
    LiquidityScorer,
    MarketStructureScorer,
    MomentumScorer,
    PriceActionScorer,
    VolatilityScorer,
    VolumeScorer,
)
from app.signal.filters import SignalFilterPipeline
from app.signal.levels import EntryLevelCalculator
from app.signal.models import DiagnosticEvaluation, SignalCandidate, SignalStatus
from app.signal.mtf import MTFAnalyzer
from app.signal.scorer import SignalScorer
from app.telegram.bot import TelegramNotifier
from app.utils.logging import setup_logger

logger = setup_logger("signal_engine.core")


class SignalEngine:
    """
    Deterministic Multi-Factor Signal Scoring Engine for Bybit USDT Perpetuals.
    - Zero ML / neural nets (strict rule-based heuristics)
    - Independent LONG and SHORT scoring (0 - 100)
    - Strict zero lookahead bias protection
    - Operates identically on Live, Historical backtesting, and Replay
    """

    def __init__(
        self,
        provider: MarketDataProvider,
        db_repo: DatabaseRepository | None = None,
        telegram: TelegramNotifier | None = None,
        config: dict[str, Any] | None = None,
    ):
        self.provider = provider
        self.db_repo = db_repo
        self.telegram = telegram

        if config is None:
            config = settings.load_scoring_config()
        self.config = config
        scoring_cfg = self.config.get("scoring", self.config)

        # 1. MTF Analyzer
        ind_cfg = settings.load_indicators_config()
        warmup_bars = ind_cfg.get("indicators", {}).get("warmup_bars", 200)
        self.mtf_analyzer = MTFAnalyzer(min_warmup_bars=warmup_bars)

        # 2. Component Scorers
        weights = scoring_cfg.get("weights", {})
        self.htf_scorer = HTFTrendScorer(weight=float(weights.get("htf_trend", 0.15)))
        self.structure_scorer = MarketStructureScorer(weight=float(weights.get("market_structure", 0.15)))
        self.liquidity_scorer = LiquidityScorer(weight=float(weights.get("liquidity", 0.15)))
        self.momentum_scorer = MomentumScorer(weight=float(weights.get("momentum", 0.10)))
        self.volume_scorer = VolumeScorer(weight=float(weights.get("volume", 0.10)))
        self.volatility_scorer = VolatilityScorer(weight=float(weights.get("volatility", 0.05)))

        deriv_cfg = scoring_cfg.get("derivatives", {})
        freshness_minutes = int(deriv_cfg.get("freshness_max_age_minutes", 60))
        penalty_stale = float(deriv_cfg.get("penalty_if_stale", 25.0))
        self.derivatives_scorer = DerivativesScorer(
            weight=float(weights.get("derivatives", 0.15)),
            freshness_max_age_ms=freshness_minutes * 60 * 1000,
            stale_penalty=penalty_stale,
        )

        self.price_action_scorer = PriceActionScorer(weight=float(weights.get("price_action", 0.15)))

        # 3. Aggregation, Levels, and Filters
        self.scorer = SignalScorer(config=self.config)
        self.level_calculator = EntryLevelCalculator(config=self.config)
        self.filter_pipeline = SignalFilterPipeline(config=self.config)

        # Telegram dispatch policy
        tg_cfg = scoring_cfg.get("telegram", {})
        self.send_watch = tg_cfg.get("send_watch", False)
        self.send_signal = tg_cfg.get("send_signal", True)
        self.send_strong_signal = tg_cfg.get("send_strong_signal", True)

    async def evaluate_diagnostic(
        self,
        symbol: str,
        as_of: datetime | int | None = None,
    ) -> DiagnosticEvaluation:
        """
        Evaluates a symbol strictly as of `as_of` timestamp, returning a comprehensive
        DiagnosticEvaluation capturing scores, components, regime, and filter status
        regardless of whether the setup qualified as a signal or was filtered out.
        """
        # 1. Normalize as_of timestamp to epoch ms
        if as_of is None:
            as_of_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        elif isinstance(as_of, datetime):
            as_of_ms = int(as_of.timestamp() * 1000)
        else:
            as_of_ms = int(as_of)

        # 2. Multi-Timeframe Feature Snapshot
        mtf_context = self.mtf_analyzer.analyze(symbol, self.provider, as_of=as_of_ms)

        # Filter 1: Data Readiness
        readiness_res = self.filter_pipeline.check_readiness(mtf_context)
        if not readiness_res.passed:
            return DiagnosticEvaluation(
                symbol=symbol,
                as_of=as_of_ms,
                is_ready=False,
                direction="LONG",
                long_score=0.0,
                short_score=0.0,
                directional_edge=0.0,
                signal_status=SignalStatus.IGNORE,
                regime="UNKNOWN",
                filter_passed=False,
                filter_stop_reason=readiness_res.rejection_reason,
            )

        # 3. Retrieve Derivatives Snapshot
        derivatives_data = self.provider.get_derivatives(symbol, as_of=as_of_ms)

        # 4. Compute Component Scores Independently
        component_scores = {
            "htf_trend": self.htf_scorer.score(mtf_context),
            "market_structure": self.structure_scorer.score(mtf_context),
            "liquidity": self.liquidity_scorer.score(mtf_context),
            "momentum": self.momentum_scorer.score(mtf_context),
            "volume": self.volume_scorer.score(mtf_context),
            "volatility": self.volatility_scorer.score(mtf_context),
            "derivatives": self.derivatives_scorer.score(mtf_context, derivatives_data, as_of=as_of_ms),
            "price_action": self.price_action_scorer.score(mtf_context),
        }

        # 5. Total Linear Combination & Status Categorization
        (
            direction,
            long_score,
            short_score,
            directional_edge,
            status,
            penalties,
        ) = self.scorer.evaluate(component_scores, mtf_context)

        primary_score = long_score if direction == "LONG" else short_score

        active_comp_map = {
            name: (c.long_score if direction == "LONG" else c.short_score)
            for name, c in component_scores.items()
        }
        comp_details_map = {
            name: {
                "long_score": c.long_score,
                "short_score": c.short_score,
                "weight": c.weight,
                "reasons": c.reasons,
                "penalties": c.penalties,
            }
            for name, c in component_scores.items()
        }

        regime_str = (
            mtf_context.m15.structure.regime.value
            if (mtf_context.m15.structure and mtf_context.m15.structure.regime)
            else "NORMAL"
        )

        diag = DiagnosticEvaluation(
            symbol=symbol,
            as_of=as_of_ms,
            is_ready=True,
            direction=direction,
            long_score=round(long_score, 2),
            short_score=round(short_score, 2),
            directional_edge=round(directional_edge, 2),
            signal_status=status,
            regime=regime_str,
            component_scores=active_comp_map,
            component_details=comp_details_map,
            filter_passed=False,
            filter_stop_reason=None,
        )

        # 6. Current Price
        current_price = self.provider.get_latest_price(symbol, as_of=as_of_ms)
        if current_price <= 0:
            if mtf_context.m5.indicators and mtf_context.m5.indicators.close > 0:
                current_price = mtf_context.m5.indicators.close
            else:
                diag.filter_stop_reason = "No price data available"
                return diag

        # 7. Compute Structural Levels (Entry Zone, Stop Loss, TP1, TP2, R:R)
        levels = self.level_calculator.calculate_levels(direction, current_price, mtf_context)
        if levels is None:
            diag.filter_stop_reason = "Invalid geometric risk-reward levels"
            return diag

        entry_low, entry_high, stop_loss, tp1, tp2, rr_tp1, rr_tp2 = levels

        # Check sequential filters (tracked for diagnostics and qualification)
        filter_passed = True
        filter_stop_reason = None

        edge_res = self.filter_pipeline.check_directional_edge(directional_edge)
        if not edge_res.passed and filter_stop_reason is None:
            filter_stop_reason = edge_res.rejection_reason
            filter_passed = False

        score_res = self.filter_pipeline.check_score_threshold(primary_score, allow_watch=True)
        if not score_res.passed and filter_stop_reason is None:
            filter_stop_reason = score_res.rejection_reason
            filter_passed = False

        regime_res = self.filter_pipeline.check_market_regime(mtf_context)
        if not regime_res.passed and filter_stop_reason is None:
            filter_stop_reason = regime_res.rejection_reason
            filter_passed = False

        rr_res = self.filter_pipeline.check_risk_reward(rr_tp1)
        if not rr_res.passed and filter_stop_reason is None:
            filter_stop_reason = rr_res.rejection_reason
            filter_passed = False

        cooldown_res = self.filter_pipeline.check_cooldown(symbol, direction, as_of_ms)
        if not cooldown_res.passed and filter_stop_reason is None:
            filter_stop_reason = cooldown_res.rejection_reason
            filter_passed = False

        # 8. Consolidate Confluent Reasons and Warnings
        active_reasons: list[str] = list(mtf_context.reasons)
        for comp in component_scores.values():
            active_reasons.extend(comp.reasons)
        seen = set()
        dedup_reasons = []
        for r in active_reasons:
            if r not in seen:
                seen.add(r)
                dedup_reasons.append(r)

        tf_context = {
            "h4_trend": mtf_context.h4.indicators.ema_alignment if mtf_context.h4.indicators else "UNKNOWN",
            "h1_structure": mtf_context.h1.structure.structure_state.value if mtf_context.h1.structure else "UNKNOWN",
            "m15_setup": (
                mtf_context.m15.structure.latest_sweep.sweep_type
                if (mtf_context.m15.structure and mtf_context.m15.structure.latest_sweep)
                else (mtf_context.m15.structure.structure_state.value if mtf_context.m15.structure else "UNKNOWN")
            ),
            "m5_entry": (
                "CONFIRMED"
                if mtf_context.entry_confirmation == direction
                else mtf_context.entry_confirmation
            ),
        }

        # 9. Instantiate Signal Candidate
        candidate = SignalCandidate(
            symbol=symbol,
            timestamp=datetime.fromtimestamp(as_of_ms / 1000.0, tz=timezone.utc),
            as_of_timestamp=as_of_ms,
            direction=direction,
            long_score=long_score,
            short_score=short_score,
            directional_edge=directional_edge,
            signal_status=status,
            regime=regime_str,
            entry_zone_low=entry_low,
            entry_zone_high=entry_high,
            current_price=current_price,
            stop_loss=stop_loss,
            take_profit_1=tp1,
            take_profit_2=tp2,
            risk_reward_tp1=rr_tp1,
            risk_reward_tp2=rr_tp2,
            reason_codes=dedup_reasons,
            warning_codes=list(set(penalties)),
            component_scores=active_comp_map,
            component_details=component_scores,
            timeframe_context=tf_context,
        )

        diag.filter_passed = filter_passed
        diag.filter_stop_reason = filter_stop_reason
        diag.candidate = candidate
        return diag

    async def evaluate(
        self,
        symbol: str,
        as_of: datetime | int | None = None,
    ) -> SignalCandidate | None:
        """
        Deterministically evaluates a symbol strictly as of the requested timestamp.
        Returns a qualified SignalCandidate, or None if filtered out or insufficient data.
        """
        diag = await self.evaluate_diagnostic(symbol, as_of)
        if not diag.candidate or not diag.filter_passed:
            if diag.filter_stop_reason:
                logger.debug(f"{symbol}: Filtered out ({diag.filter_stop_reason})")
            return None

        candidate = diag.candidate
        status = candidate.signal_status
        primary_score = candidate.long_score if candidate.direction == "LONG" else candidate.short_score

        # Post-Qualification Processing (Registration, DB Persistence, Telegram Dispatch)
        if status in [SignalStatus.SIGNAL, SignalStatus.STRONG_SIGNAL]:
            self.filter_pipeline.register_signal(candidate)

            # Persist to SQLite via DatabaseRepository
            if self.db_repo is not None:
                await self._persist_signal(candidate)

            # Dispatch via Telegram Notifier
            if self.telegram is not None:
                should_send = (
                    (status == SignalStatus.STRONG_SIGNAL and self.send_strong_signal)
                    or (status == SignalStatus.SIGNAL and self.send_signal)
                )
                if should_send:
                    await self.telegram.send_signal(candidate)

        elif status == SignalStatus.WATCH and self.send_watch and self.telegram is not None:
            await self.telegram.send_signal(candidate)

        logger.info(
            f"Generated {status.value} for {symbol} ({candidate.direction}) | "
            f"Score: {primary_score:.1f}/100 | RR: 1:{candidate.risk_reward_tp1:.1f}"
        )
        return candidate

    async def _persist_signal(self, candidate: SignalCandidate) -> None:
        """Saves qualified signal and feature breakdown to database."""
        try:
            signal_dict = {
                "id": candidate.id,
                "symbol": candidate.symbol,
                "direction": candidate.direction,
                "timestamp": candidate.as_of_timestamp,
                "score": candidate.long_score if candidate.direction == "LONG" else candidate.short_score,
                "market_regime": candidate.regime,
                "current_price": candidate.current_price,
                "entry_min": candidate.entry_zone_low,
                "entry_max": candidate.entry_zone_high,
                "stop_loss": candidate.stop_loss,
                "tp1": candidate.take_profit_1,
                "tp2": candidate.take_profit_2,
                "risk_reward": candidate.risk_reward_tp1,
                "status": candidate.signal_status.value,
                "telegram_sent": False,
            }

            features_breakdown = [
                {
                    "feature_name": name,
                    "feature_value": float(score_val),
                    "contribution": float(score_val * self.scorer.weights.get(name, 0.15)),
                    "details": ", ".join(candidate.component_details[name].reasons) if name in candidate.component_details else None,
                }
                for name, score_val in candidate.component_scores.items()
            ]

            if self.db_repo:
                await self.db_repo.save_signal(signal_dict, features_breakdown)
                logger.debug(f"Signal {candidate.id} successfully persisted in database.")
        except Exception as e:
            logger.error(f"Failed to persist signal {candidate.id} to database: {e}")

    async def evaluate_universe(
        self,
        symbols: list[str],
        as_of: datetime | int | None = None,
    ) -> list[SignalCandidate]:
        """Evaluates an entire universe of symbols chronologically and returns qualified setups."""
        candidates = []
        for symbol in symbols:
            candidate = await self.evaluate(symbol, as_of=as_of)
            if candidate is not None:
                candidates.append(candidate)
        return candidates
