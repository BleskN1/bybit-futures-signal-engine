"""Deterministic trade execution simulator enforcing no-lookahead, conservative ambiguous candle resolution, and realistic fee/slippage/funding models."""

from typing import Any

from app.backtest.models import TradeOutcome, TradeRecord, TradeState
from app.signal.models import SignalCandidate
from app.utils.logging import setup_logger

logger = setup_logger("signal_engine.simulator")


class TradeSimulator:
    """
    Simulates order fills, SL/TP execution, and trade lifecycle
    against sequential future closed candles.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        cfg = config or {}
        bt_cfg = cfg.get("backtest", cfg)

        exec_cfg = bt_cfg.get("execution", {})
        self.entry_mode = exec_cfg.get("entry_mode", "zone_touch")
        self.max_bars_to_enter = int(exec_cfg.get("max_bars_to_enter", 12))

        slip_cfg = exec_cfg.get("slippage", {})
        self.slippage_enabled = slip_cfg.get("enabled", True)
        self.slippage_bps = float(slip_cfg.get("bps", 2.0))
        self.slippage_rate = (self.slippage_bps / 10000.0) if self.slippage_enabled else 0.0

        fees_cfg = bt_cfg.get("fees", {})
        self.fee_model = fees_cfg.get("model", "taker")
        self.taker_rate = float(fees_cfg.get("taker_rate", 0.00055))
        self.maker_rate = float(fees_cfg.get("maker_rate", 0.00020))
        self.fee_per_leg = self.taker_rate if self.fee_model == "taker" else self.maker_rate

        funding_cfg = bt_cfg.get("funding", {})
        self.funding_enabled = funding_cfg.get("enabled", True)
        self.default_funding_rate_8h = float(funding_cfg.get("default_rate_per_8h", 0.0001))

        self.ambiguous_policy = exec_cfg.get("ambiguous_candle", "conservative")

    def create_trade_from_candidate(self, candidate: SignalCandidate) -> TradeRecord:
        """Instantiates a pending TradeRecord from a qualified SignalCandidate."""
        initial_risk = abs(candidate.current_price - candidate.stop_loss)
        if initial_risk <= 0.0:
            initial_risk = candidate.current_price * 0.005  # 0.5% default floor

        return TradeRecord(
            symbol=candidate.symbol,
            direction=candidate.direction,
            signal_id=candidate.id,
            signal_time=candidate.as_of_timestamp,
            signal_score=(candidate.long_score if candidate.direction == "LONG" else candidate.short_score),
            component_scores=candidate.component_scores,
            regime=candidate.regime,
            reason_codes=candidate.reason_codes,
            state=TradeState.WAITING_FOR_ENTRY,
            entry_zone_low=candidate.entry_zone_low,
            entry_zone_high=candidate.entry_zone_high,
            stop_loss=candidate.stop_loss,
            take_profit_1=candidate.take_profit_1,
            take_profit_2=candidate.take_profit_2,
            risk_reward_tp1=candidate.risk_reward_tp1,
            risk_reward_tp2=candidate.risk_reward_tp2,
            initial_risk=initial_risk,
        )

    def process_candle(
        self,
        trade: TradeRecord,
        candle: dict[str, Any],
        bars_since_signal: int,
        funding_rate_snapshot: float | None = None,
    ) -> TradeRecord:
        """
        Processes a single forward closed candle for a trade.
        Returns the updated trade object.
        """
        if trade.state in [TradeState.CLOSED, TradeState.CANCELLED]:
            return trade

        # -------------------------------------------------------------
        # 1. WAITING FOR ENTRY STATE
        # -------------------------------------------------------------
        if trade.state == TradeState.WAITING_FOR_ENTRY:
            # Check expiration
            if bars_since_signal > self.max_bars_to_enter:
                trade.state = TradeState.CANCELLED
                trade.exit_reason = "ENTRY_EXPIRED"
                return trade

            c_high = candle["high"]
            c_low = candle["low"]
            c_open = candle["open"]

            filled = False
            fill_price = 0.0

            if trade.direction == "LONG":
                # Price touches entry zone (between entry_zone_low and entry_zone_high)
                if c_low <= trade.entry_zone_high and c_high >= trade.entry_zone_low:
                    # Realistic fill price within zone plus slippage
                    fill_base = min(trade.entry_zone_high, max(trade.entry_zone_low, c_open))
                    fill_price = fill_base * (1.0 + self.slippage_rate)
                    filled = True
            else:  # SHORT
                if c_high >= trade.entry_zone_low and c_low <= trade.entry_zone_high:
                    fill_base = max(trade.entry_zone_low, min(trade.entry_zone_high, c_open))
                    fill_price = fill_base * (1.0 - self.slippage_rate)
                    filled = True

            if filled:
                trade.state = TradeState.ACTIVE
                trade.entry_time = candle["timestamp"]
                trade.entry_price = fill_price
                trade.initial_risk = abs(fill_price - trade.stop_loss)
                if trade.initial_risk <= 0.0:
                    trade.initial_risk = fill_price * 0.005
                # Recalculate R:R from actual filled entry
                if trade.direction == "LONG":
                    trade.risk_reward_tp1 = (trade.take_profit_1 - fill_price) / trade.initial_risk
                    trade.risk_reward_tp2 = (trade.take_profit_2 - fill_price) / trade.initial_risk
                else:
                    trade.risk_reward_tp1 = (fill_price - trade.take_profit_1) / trade.initial_risk
                    trade.risk_reward_tp2 = (fill_price - trade.take_profit_2) / trade.initial_risk

            return trade

        # -------------------------------------------------------------
        # 2. ACTIVE TRADE STATE
        # -------------------------------------------------------------
        if trade.state == TradeState.ACTIVE:
            entry = trade.entry_price or trade.entry_zone_high
            risk = trade.initial_risk
            risk_pct = risk / entry

            c_high = candle["high"]
            c_low = candle["low"]
            c_close = candle["close"]
            ts = candle["timestamp"]

            # Update MFE / MAE
            if trade.direction == "LONG":
                fav = max(0.0, c_high - entry)
                adv = max(0.0, entry - c_low)
            else:
                fav = max(0.0, entry - c_low)
                adv = max(0.0, c_high - entry)

            trade.mfe_price = max(trade.mfe_price, fav)
            trade.mfe_r = trade.mfe_price / risk
            trade.mfe_pct = (trade.mfe_price / entry) * 100.0

            trade.mae_price = max(trade.mae_price, adv)
            trade.mae_r = trade.mae_price / risk
            trade.mae_pct = (trade.mae_price / entry) * 100.0

            # Check 8-hour funding settlement event
            # Standard Bybit funding interval: every 8h (00:00, 08:00, 16:00 UTC)
            if self.funding_enabled:
                # If timestamp is an 8h mark: ts % 28800000 < 300000
                if (ts % (8 * 3600 * 1000)) < (5 * 60 * 1000):
                    rate = funding_rate_snapshot if funding_rate_snapshot is not None else self.default_funding_rate_8h
                    funding_cost_r = (rate / risk_pct) if trade.direction == "LONG" else (-rate / risk_pct)
                    trade.funding_cost_r += max(0.0, funding_cost_r)

            # Check SL, TP1, TP2 triggers
            sl_hit = False
            tp1_hit = False
            tp2_hit = False

            if trade.direction == "LONG":
                if c_low <= trade.stop_loss:
                    sl_hit = True
                if c_high >= trade.take_profit_1:
                    tp1_hit = True
                if c_high >= trade.take_profit_2:
                    tp2_hit = True
            else:  # SHORT
                if c_high >= trade.stop_loss:
                    sl_hit = True
                if c_low <= trade.take_profit_1:
                    tp1_hit = True
                if c_low <= trade.take_profit_2:
                    tp2_hit = True

            # ---------------------------------------------------------
            # AMBIGUOUS CANDLE RULE
            # ---------------------------------------------------------
            # If both SL and any TP are touched in the same candle:
            # Conservative deterministic rule: assume SL hit first.
            if sl_hit and (tp1_hit or tp2_hit):
                trade.ambiguous_candle = True
                if self.ambiguous_policy == "conservative":
                    # Assume SL hit first
                    tp1_hit = False
                    tp2_hit = False

            # Check Exits
            if sl_hit:
                # Stop loss hit
                exit_price = trade.stop_loss * (1.0 - self.slippage_rate if trade.direction == "LONG" else 1.0 + self.slippage_rate)
                trade.exit_time = ts
                trade.exit_price = exit_price
                trade.exit_reason = "STOP_LOSS"
                trade.outcome = TradeOutcome.STOP_LOSS
                trade.state = TradeState.CLOSED

                # Calculate returns & costs
                gross_r = -1.0
                total_fees_r = (2 * self.fee_per_leg) / risk_pct
                total_slip_r = (2 * self.slippage_rate) / risk_pct

                trade.gross_r = gross_r
                trade.fee_cost_r = total_fees_r
                trade.slippage_cost_r = total_slip_r
                trade.net_r = gross_r - total_fees_r - total_slip_r - trade.funding_cost_r
                trade.holding_time_minutes = (ts - (trade.entry_time or ts)) / (60 * 1000.0)
                return trade

            if tp2_hit:
                # Full TP2 reached (50% closed at TP1, 50% at TP2)
                exit_price = trade.take_profit_2 * (1.0 - self.slippage_rate if trade.direction == "LONG" else 1.0 + self.slippage_rate)
                trade.exit_time = ts
                trade.exit_price = exit_price
                trade.exit_reason = "TAKE_PROFIT_2"
                trade.outcome = TradeOutcome.TP2
                trade.state = TradeState.CLOSED

                gross_r = (0.5 * trade.risk_reward_tp1) + (0.5 * trade.risk_reward_tp2)
                total_fees_r = (2 * self.fee_per_leg) / risk_pct
                total_slip_r = (2 * self.slippage_rate) / risk_pct

                trade.gross_r = gross_r
                trade.fee_cost_r = total_fees_r
                trade.slippage_cost_r = total_slip_r
                trade.net_r = gross_r - total_fees_r - total_slip_r - trade.funding_cost_r
                trade.holding_time_minutes = (ts - (trade.entry_time or ts)) / (60 * 1000.0)
                return trade

            if tp1_hit:
                # If TP1 hit: lock in 50% at TP1, move SL to breakeven for remaining 50%
                trade.take_profit_1 = c_high if trade.direction == "LONG" else c_low  # Recorded
                trade.stop_loss = entry  # Trailed to breakeven

        return trade

    def close_open_trade_at_end(self, trade: TradeRecord, last_candle: dict[str, Any]) -> TradeRecord:
        """Forces an open trade to close at the end of the historical backtest."""
        if trade.state == TradeState.ACTIVE:
            ts = last_candle["timestamp"]
            c_close = last_candle["close"]
            entry = trade.entry_price or trade.entry_zone_high
            risk = trade.initial_risk
            risk_pct = risk / entry

            exit_price = c_close * (1.0 - self.slippage_rate if trade.direction == "LONG" else 1.0 + self.slippage_rate)
            if trade.direction == "LONG":
                gross_r = (exit_price - entry) / risk
            else:
                gross_r = (entry - exit_price) / risk

            total_fees_r = (2 * self.fee_per_leg) / risk_pct
            total_slip_r = (2 * self.slippage_rate) / risk_pct

            trade.exit_time = ts
            trade.exit_price = exit_price
            trade.exit_reason = "BACKTEST_END_CLOSE"
            trade.outcome = TradeOutcome.EXPIRED
            trade.state = TradeState.CLOSED
            trade.gross_r = gross_r
            trade.fee_cost_r = total_fees_r
            trade.slippage_cost_r = total_slip_r
            trade.net_r = gross_r - total_fees_r - total_slip_r - trade.funding_cost_r
            trade.holding_time_minutes = (ts - (trade.entry_time or ts)) / (60 * 1000.0)

        elif trade.state == TradeState.WAITING_FOR_ENTRY:
            trade.state = TradeState.CANCELLED
            trade.exit_reason = "BACKTEST_END_UNFILLED"

        return trade
