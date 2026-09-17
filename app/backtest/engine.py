"""Historical Replay & Backtest Engine driving the production SignalEngine."""

from typing import Any

from app.backtest.interface import BacktestEngine
from app.backtest.metrics import MetricsCalculator
from app.backtest.models import BacktestMetrics, TradeRecord, TradeState
from app.backtest.simulator import TradeSimulator
from app.config import settings
from app.market_data.provider import MarketDataProvider
from app.signal.engine import SignalEngine
from app.signal.models import SignalStatus
from app.utils.logging import setup_logger

logger = setup_logger("signal_engine.backtest")


class HistoricalBacktestEngine(BacktestEngine):
    """
    Simulates sequential market time to evaluate the production SignalEngine
    against historical Bybit market data without lookahead bias.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        if config is None:
            config = settings.load_backtest_config()
        self.config = config
        self.simulator = TradeSimulator(config=self.config)

        bt_cfg = self.config.get("backtest", self.config)
        self.step_minutes = int(bt_cfg.get("eval_step_minutes", 5))
        self.step_ms = self.step_minutes * 60 * 1000

        risk_cfg = bt_cfg.get("risk", {})
        self.max_trades_per_sym = int(risk_cfg.get("max_active_trades_per_symbol", 1))

    async def run(
        self,
        provider: MarketDataProvider,
        symbols: list[str],
        start_time: int,
        end_time: int,
        signal_engine: SignalEngine | None = None,
    ) -> dict[str, Any]:
        """
        Executes a chronological historical replay.
        At each evaluation timestamp `as_of`, invokes `signal_engine.evaluate(sym, as_of)`.
        """
        logger.info(
            f"Starting historical backtest: {len(symbols)} symbols from "
            f"{start_time} to {end_time} (step={self.step_minutes}m)..."
        )

        if signal_engine is None:
            signal_engine = SignalEngine(provider=provider)

        trades: list[TradeRecord] = []
        pending_and_active: list[TradeRecord] = []

        total_evaluations = 0
        signals_generated = 0
        signal_count = 0
        strong_signal_count = 0

        # Precompute the timeline of closed 5m bar close timestamps
        current_ts = start_time
        # Ensure aligned to 5m boundary
        current_ts = ((current_ts + self.step_ms - 1) // self.step_ms) * self.step_ms

        while current_ts <= end_time:
            # 1. Update any existing active or waiting trades with the bar closing at current_ts
            still_open: list[TradeRecord] = []
            for tr in pending_and_active:
                candles_5m = provider.get_candles(tr.symbol, "5", limit=1, as_of=current_ts)
                if candles_5m:
                    candle = candles_5m[-1]
                    bars_since_sig = int((current_ts - tr.signal_time) / self.step_ms)
                    derivs = provider.get_derivatives(tr.symbol, as_of=current_ts)
                    funding_rate = derivs.get("funding_rate", 0.0)

                    self.simulator.process_candle(
                        trade=tr,
                        candle=candle,
                        bars_since_signal=bars_since_sig,
                        funding_rate_snapshot=funding_rate,
                    )

                if tr.state in [TradeState.WAITING_FOR_ENTRY, TradeState.ACTIVE]:
                    still_open.append(tr)

            pending_and_active = still_open

            # 2. Evaluate signals across universe symbols
            for sym in symbols:
                # Count current open trades for this symbol
                open_for_sym = [t for t in pending_and_active if t.symbol == sym]
                if len(open_for_sym) >= self.max_trades_per_sym:
                    # Skip signal evaluation if symbol already has active position
                    continue

                total_evaluations += 1

                # Execute production signal engine strictly as of current_ts
                candidate = await signal_engine.evaluate(sym, as_of=current_ts)

                if candidate is not None:
                    signals_generated += 1
                    if candidate.signal_status == SignalStatus.STRONG_SIGNAL:
                        strong_signal_count += 1
                    else:
                        signal_count += 1

                    # Create trade record and register into tracking queue
                    new_trade = self.simulator.create_trade_from_candidate(candidate)
                    trades.append(new_trade)
                    pending_and_active.append(new_trade)

            current_ts += self.step_ms

        # 3. Close any remaining open trades at the end of backtest
        for tr in pending_and_active:
            candles = provider.get_candles(tr.symbol, "5", limit=1, as_of=end_time)
            if candles:
                self.simulator.close_open_trade_at_end(tr, candles[-1])

        # 4. Compute Performance Metrics
        metrics = MetricsCalculator.calculate_metrics(
            trades=trades,
            total_evaluations=total_evaluations,
            signals_generated=signals_generated,
            signal_count=signal_count,
            strong_signal_count=strong_signal_count,
            start_time=start_time,
            end_time=end_time,
            symbols=symbols,
        )

        logger.info(
            f"Backtest finished: {total_evaluations} evaluations, {signals_generated} signals, "
            f"{metrics.total_trades} trades executed. Win Rate: {metrics.win_rate}%, Total R: {metrics.total_r}."
        )

        return {
            "metrics": metrics.model_dump(),
            "trades": [t.model_dump() for t in trades],
        }
