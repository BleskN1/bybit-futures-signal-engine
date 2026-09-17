"""Quantitative backtest metrics calculation, equity curve tracking, and multi-factor breakdown."""

import statistics
from typing import Any

from app.backtest.models import (
    BacktestMetrics,
    EquityPoint,
    ScoreBucketMetrics,
    SubgroupMetrics,
    TradeRecord,
    TradeState,
)


class MetricsCalculator:
    """Computes comprehensive performance statistics for historical backtest trades."""

    SCORE_BUCKET_RANGES = [
        ("60–64", 60.0, 64.999),
        ("65–69", 65.0, 69.999),
        ("70–74", 70.0, 74.999),
        ("75–79", 75.0, 79.999),
        ("80–84", 80.0, 84.999),
        ("85–89", 85.0, 89.999),
        ("90–100", 90.0, 100.0),
    ]

    @staticmethod
    def calculate_subgroup_metrics(group_name: str, trades: list[TradeRecord]) -> SubgroupMetrics:
        """Calculates win rate, average R, expectancy, and profit factor for a subset of trades."""
        if not trades:
            return SubgroupMetrics(group=group_name)

        n = len(trades)
        wins = [t for t in trades if t.net_r > 0]
        losses = [t for t in trades if t.net_r < 0]

        win_rate = (len(wins) / n) * 100.0 if n > 0 else 0.0
        tot_r = sum(t.net_r for t in trades)
        avg_r = tot_r / n if n > 0 else 0.0

        pos_r = sum(t.net_r for t in wins)
        neg_r = abs(sum(t.net_r for t in losses))

        if neg_r > 0:
            profit_factor = pos_r / neg_r
        elif pos_r > 0:
            profit_factor = 999.0
        else:
            profit_factor = 0.0

        avg_win = (pos_r / len(wins)) if wins else 0.0
        avg_loss = (neg_r / len(losses)) if losses else 0.0
        win_frac = len(wins) / n if n > 0 else 0.0
        loss_frac = len(losses) / n if n > 0 else 0.0
        expectancy = (win_frac * avg_win) - (loss_frac * avg_loss)

        return SubgroupMetrics(
            group=group_name,
            trades=n,
            winning_trades=len(wins),
            losing_trades=len(losses),
            win_rate=round(win_rate, 2),
            average_r=round(avg_r, 4),
            expectancy=round(expectancy, 4),
            profit_factor=round(profit_factor, 2),
            total_r=round(tot_r, 4),
        )

    @classmethod
    def calculate_metrics(
        cls,
        trades: list[TradeRecord],
        total_evaluations: int,
        signals_generated: int,
        signal_count: int,
        strong_signal_count: int,
        start_time: int,
        end_time: int,
        symbols: list[str],
    ) -> BacktestMetrics:
        """Computes all quantitative metrics, score buckets, regimes, and equity trajectory."""
        closed_trades = [t for t in trades if t.state == TradeState.CLOSED]
        total_trades = len(closed_trades)

        duration_days = max(0.1, (end_time - start_time) / (1000.0 * 86400))

        if total_trades == 0:
            return BacktestMetrics(
                start_time=start_time,
                end_time=end_time,
                duration_days=round(duration_days, 2),
                symbols=symbols,
                total_evaluations=total_evaluations,
                signals_generated=signals_generated,
                signal_count=signal_count,
                strong_signal_count=strong_signal_count,
                total_trades=0,
            )

        wins = [t for t in closed_trades if t.net_r > 0.0001]
        losses = [t for t in closed_trades if t.net_r < -0.0001]
        be = [t for t in closed_trades if abs(t.net_r) <= 0.0001]

        win_rate = (len(wins) / total_trades) * 100.0
        net_returns = [t.net_r for t in closed_trades]
        total_r = sum(net_returns)
        avg_r = total_r / total_trades
        median_r = statistics.median(net_returns) if net_returns else 0.0

        pos_r = sum(t.net_r for t in wins)
        neg_r = abs(sum(t.net_r for t in losses))
        profit_factor = (pos_r / neg_r) if neg_r > 0 else (999.0 if pos_r > 0 else 0.0)

        avg_win = (pos_r / len(wins)) if wins else 0.0
        avg_loss = (neg_r / len(losses)) if losses else 0.0
        win_frac = len(wins) / total_trades
        loss_frac = len(losses) / total_trades
        expectancy = (win_frac * avg_win) - (loss_frac * avg_loss)

        # Financial costs
        gross_pnl_r = sum(t.gross_r for t in closed_trades)
        fees_r = sum(t.fee_cost_r for t in closed_trades)
        funding_r = sum(t.funding_cost_r for t in closed_trades)
        slippage_r = sum(t.slippage_cost_r for t in closed_trades)

        # Drawdown and equity curve
        equity_curve: list[EquityPoint] = []
        cum_r = 0.0
        peak_r = 0.0
        max_dd_r = 0.0
        drawdowns: list[float] = []

        cur_losing_streak = 0
        max_losing_streak = 0

        for i, t in enumerate(closed_trades, 1):
            cum_r += t.net_r
            if cum_r > peak_r:
                peak_r = cum_r
            dd = peak_r - cum_r
            drawdowns.append(dd)
            if dd > max_dd_r:
                max_dd_r = dd

            if t.net_r < 0:
                cur_losing_streak += 1
                if cur_losing_streak > max_losing_streak:
                    max_losing_streak = cur_losing_streak
            else:
                cur_losing_streak = 0

            equity_curve.append(
                EquityPoint(
                    trade_index=i,
                    timestamp=t.exit_time or t.signal_time,
                    trade_id=t.id,
                    symbol=t.symbol,
                    net_r=round(t.net_r, 4),
                    cumulative_r=round(cum_r, 4),
                    peak_r=round(peak_r, 4),
                    drawdown_r=round(dd, 4),
                )
            )

        avg_dd_r = sum(drawdowns) / len(drawdowns) if drawdowns else 0.0
        holding_times = [t.holding_time_minutes for t in closed_trades]
        avg_holding = sum(holding_times) / len(holding_times) if holding_times else 0.0
        max_holding = max(holding_times) if holding_times else 0.0

        # Score Buckets
        score_buckets: list[ScoreBucketMetrics] = []
        for bucket_name, low_s, high_s in cls.SCORE_BUCKET_RANGES:
            b_trades = [t for t in closed_trades if low_s <= t.signal_score <= high_s]
            sub = cls.calculate_subgroup_metrics(bucket_name, b_trades)
            score_buckets.append(
                ScoreBucketMetrics(
                    bucket=bucket_name,
                    trades=sub.trades,
                    winning_trades=sub.winning_trades,
                    losing_trades=sub.losing_trades,
                    win_rate=sub.win_rate,
                    average_r=sub.average_r,
                    expectancy=sub.expectancy,
                    profit_factor=sub.profit_factor,
                    total_r=sub.total_r,
                )
            )

        # Regimes
        regime_names = ["TRENDING", "COMPRESSION", "EXPANSION", "CHOPPY", "CONSOLIDATION"]
        regime_metrics: list[SubgroupMetrics] = []
        for r_name in regime_names:
            r_trades = [t for t in closed_trades if t.regime == r_name]
            if r_trades or r_name in ["TRENDING", "COMPRESSION", "EXPANSION", "CHOPPY"]:
                regime_metrics.append(cls.calculate_subgroup_metrics(r_name, r_trades))

        # Directions
        dir_metrics: list[SubgroupMetrics] = [
            cls.calculate_subgroup_metrics("LONG", [t for t in closed_trades if t.direction == "LONG"]),
            cls.calculate_subgroup_metrics("SHORT", [t for t in closed_trades if t.direction == "SHORT"]),
        ]

        return BacktestMetrics(
            start_time=start_time,
            end_time=end_time,
            duration_days=round(duration_days, 2),
            symbols=symbols,
            total_evaluations=total_evaluations,
            signals_generated=signals_generated,
            signal_count=signal_count,
            strong_signal_count=strong_signal_count,
            total_trades=total_trades,
            winning_trades=len(wins),
            losing_trades=len(losses),
            breakeven_trades=len(be),
            win_rate=round(win_rate, 2),
            average_r=round(avg_r, 4),
            median_r=round(median_r, 4),
            total_r=round(total_r, 4),
            expectancy=round(expectancy, 4),
            profit_factor=round(profit_factor, 2),
            max_drawdown_r=round(max_dd_r, 4),
            average_drawdown_r=round(avg_dd_r, 4),
            largest_win_r=round(max(net_returns), 4) if net_returns else 0.0,
            largest_loss_r=round(min(net_returns), 4) if net_returns else 0.0,
            average_holding_time_minutes=round(avg_holding, 1),
            max_holding_time_minutes=round(max_holding, 1),
            max_losing_streak=max_losing_streak,
            gross_pnl_r=round(gross_pnl_r, 4),
            fees_r=round(fees_r, 4),
            funding_r=round(funding_r, 4),
            slippage_r=round(slippage_r, 4),
            net_pnl_r=round(total_r, 4),
            score_buckets=score_buckets,
            regimes=regime_metrics,
            directions=dir_metrics,
            equity_curve=equity_curve,
        )
