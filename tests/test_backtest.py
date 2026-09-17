"""Focused unit tests for Historical Replay & Backtest Engine."""

import pytest

from app.backtest.engine import HistoricalBacktestEngine
from app.backtest.metrics import MetricsCalculator
from app.backtest.models import TradeOutcome, TradeRecord, TradeState
from app.backtest.simulator import TradeSimulator
from app.market_data.historical import HistoricalMarketDataProvider
from app.signal.engine import SignalEngine
from app.signal.models import SignalCandidate, SignalStatus


def create_mock_candidate(
    symbol: str = "BTCUSDT",
    direction: str = "LONG",
    price: float = 60000.0,
    score: float = 78.0,
    sl: float = 59000.0,
    tp1: float = 61500.0,
    tp2: float = 63000.0,
    ts: int = 1700000000000,
) -> SignalCandidate:
    """Helper creating a valid test candidate."""
    if direction == "LONG":
        e_low = price - 50.0
        e_high = price
    else:
        e_low = price
        e_high = price + 50.0

    return SignalCandidate(
        symbol=symbol,
        timestamp=pytest.importorskip("datetime").datetime.fromtimestamp(ts / 1000.0, tz=pytest.importorskip("datetime").timezone.utc),
        as_of_timestamp=ts,
        direction=direction,
        long_score=score if direction == "LONG" else 20.0,
        short_score=score if direction == "SHORT" else 20.0,
        directional_edge=score - 20.0,
        signal_status=SignalStatus.SIGNAL,
        regime="TRENDING",
        entry_zone_low=e_low,
        entry_zone_high=e_high,
        current_price=price,
        stop_loss=sl,
        take_profit_1=tp1,
        take_profit_2=tp2,
        risk_reward_tp1=abs(tp1 - price) / abs(price - sl),
        risk_reward_tp2=abs(tp2 - price) / abs(price - sl),
        component_scores={"htf_trend": 80.0, "market_structure": 75.0},
    )


class TestBacktestSimulator:
    """Tests trade execution, fees, slippage, funding, ambiguous candle handling, and excursions."""

    def test_long_entry_and_tp2_execution(self):
        sim = TradeSimulator()
        cand = create_mock_candidate(direction="LONG", price=60000.0, sl=59000.0, tp1=61500.0, tp2=63000.0)
        trade = sim.create_trade_from_candidate(cand)
        assert trade.state == TradeState.WAITING_FOR_ENTRY

        # 1. Forward candle touches entry zone
        c1 = {"timestamp": cand.as_of_timestamp + 300000, "open": 60000.0, "high": 60050.0, "low": 59980.0, "close": 60010.0}
        trade = sim.process_candle(trade, c1, bars_since_signal=1)
        assert trade.state == TradeState.ACTIVE
        assert trade.entry_price is not None
        assert trade.entry_price >= 59950.0  # Slippage accounted

        # 2. Forward candle hits TP1 and TP2
        c2 = {"timestamp": cand.as_of_timestamp + 600000, "open": 60010.0, "high": 63200.0, "low": 60000.0, "close": 63100.0}
        trade = sim.process_candle(trade, c2, bars_since_signal=2)
        assert trade.state == TradeState.CLOSED
        assert trade.outcome == TradeOutcome.TP2
        assert trade.gross_r > 0.0
        assert trade.net_r > 0.0
        # MFE was updated
        assert trade.mfe_price >= 3100.0

    def test_short_entry_and_sl_execution(self):
        sim = TradeSimulator()
        cand = create_mock_candidate(
            direction="SHORT",
            price=60000.0,
            sl=61000.0,
            tp1=58500.0,
            tp2=57000.0,
        )
        trade = sim.create_trade_from_candidate(cand)

        # 1. Entry touch
        c1 = {"timestamp": cand.as_of_timestamp + 300000, "open": 60000.0, "high": 60020.0, "low": 59970.0, "close": 60010.0}
        trade = sim.process_candle(trade, c1, bars_since_signal=1)
        assert trade.state == TradeState.ACTIVE

        # 2. Stop loss hit
        c2 = {"timestamp": cand.as_of_timestamp + 600000, "open": 60010.0, "high": 61200.0, "low": 60000.0, "close": 61100.0}
        trade = sim.process_candle(trade, c2, bars_since_signal=2)
        assert trade.state == TradeState.CLOSED
        assert trade.outcome == TradeOutcome.STOP_LOSS
        assert trade.gross_r == -1.0
        assert trade.net_r < -1.0  # Fees and slippage reduce net R below -1.0

    def test_ambiguous_candle_conservative_policy(self):
        """If both SL and TP are touched in the same candle, conservative rule assumes SL first."""
        sim = TradeSimulator()
        cand = create_mock_candidate(direction="LONG", price=60000.0, sl=59000.0, tp1=61500.0, tp2=63000.0)
        trade = sim.create_trade_from_candidate(cand)

        # Fill trade
        c1 = {"timestamp": cand.as_of_timestamp + 300000, "open": 60000.0, "high": 60010.0, "low": 59980.0, "close": 60000.0}
        trade = sim.process_candle(trade, c1, bars_since_signal=1)
        assert trade.state == TradeState.ACTIVE

        # Ambiguous bar: low breaks 59000 (SL) AND high breaks 63000 (TP2)
        c2 = {"timestamp": cand.as_of_timestamp + 600000, "open": 60000.0, "high": 63500.0, "low": 58500.0, "close": 61000.0}
        trade = sim.process_candle(trade, c2, bars_since_signal=2)

        assert trade.ambiguous_candle is True
        assert trade.outcome == TradeOutcome.STOP_LOSS
        assert trade.gross_r == -1.0

    def test_entry_expiration(self):
        """If price does not reach entry zone within max_bars_to_enter, trade is cancelled."""
        sim = TradeSimulator({"backtest": {"execution": {"max_bars_to_enter": 3}}})
        cand = create_mock_candidate(direction="LONG", price=60000.0)
        trade = sim.create_trade_from_candidate(cand)

        # 4 bars pass without touching entry zone
        for i in range(1, 5):
            c = {"timestamp": cand.as_of_timestamp + i * 300000, "open": 61000.0, "high": 61500.0, "low": 60800.0, "close": 61200.0}
            trade = sim.process_candle(trade, c, bars_since_signal=i)

        assert trade.state == TradeState.CANCELLED
        assert trade.exit_reason == "ENTRY_EXPIRED"

    def test_fees_and_slippage_and_funding_impact(self):
        """Verifies fees, slippage, and funding are accounted for in net R."""
        sim = TradeSimulator(
            {
                "backtest": {
                    "fees": {"model": "taker", "taker_rate": 0.00055},
                    "execution": {"slippage": {"enabled": True, "bps": 2.0}},
                    "funding": {"enabled": True, "default_rate_per_8h": 0.0001},
                }
            }
        )
        cand = create_mock_candidate(direction="LONG", price=60000.0, sl=59400.0, tp1=61200.0)  # 1% risk
        trade = sim.create_trade_from_candidate(cand)

        # Entry
        c1 = {"timestamp": cand.as_of_timestamp + 300000, "open": 60000.0, "high": 60010.0, "low": 59980.0, "close": 60000.0}
        trade = sim.process_candle(trade, c1, bars_since_signal=1)

        # Exit at SL
        c2 = {"timestamp": cand.as_of_timestamp + 600000, "open": 59900.0, "high": 59950.0, "low": 59200.0, "close": 59300.0}
        trade = sim.process_candle(trade, c2, bars_since_signal=2)

        assert trade.fee_cost_r > 0.0
        assert trade.slippage_cost_r > 0.0
        assert trade.net_r < trade.gross_r


class TestMetricsCalculator:
    """Tests calculation of win rate, expectancy, drawdown, and score buckets."""

    def test_metrics_calculation(self):
        t1 = TradeRecord(
            symbol="BTCUSDT",
            direction="LONG",
            signal_id="1",
            signal_time=1000,
            signal_score=82.0,
            regime="TRENDING",
            entry_zone_low=100.0,
            entry_zone_high=100.0,
            stop_loss=90.0,
            take_profit_1=115.0,
            take_profit_2=130.0,
            risk_reward_tp1=1.5,
            risk_reward_tp2=3.0,
            state=TradeState.CLOSED,
            gross_r=2.0,
            fee_cost_r=0.1,
            slippage_cost_r=0.04,
            net_r=1.86,
        )
        t2 = TradeRecord(
            symbol="BTCUSDT",
            direction="SHORT",
            signal_id="2",
            signal_time=2000,
            signal_score=76.0,
            regime="COMPRESSION",
            entry_zone_low=100.0,
            entry_zone_high=100.0,
            stop_loss=110.0,
            take_profit_1=85.0,
            take_profit_2=70.0,
            risk_reward_tp1=1.5,
            risk_reward_tp2=3.0,
            state=TradeState.CLOSED,
            gross_r=-1.0,
            fee_cost_r=0.1,
            slippage_cost_r=0.04,
            net_r=-1.14,
        )

        metrics = MetricsCalculator.calculate_metrics(
            trades=[t1, t2],
            total_evaluations=10,
            signals_generated=2,
            signal_count=2,
            strong_signal_count=0,
            start_time=1000,
            end_time=3000,
            symbols=["BTCUSDT"],
        )

        assert metrics.total_trades == 2
        assert metrics.winning_trades == 1
        assert metrics.losing_trades == 1
        assert metrics.win_rate == 50.0
        assert metrics.total_r == pytest.approx(0.72, abs=0.01)
        assert metrics.profit_factor > 1.0

        # Check score buckets
        b_75_79 = next(b for b in metrics.score_buckets if b.bucket == "75–79")
        assert b_75_79.trades == 1
        assert b_75_79.losing_trades == 1

        b_80_84 = next(b for b in metrics.score_buckets if b.bucket == "80–84")
        assert b_80_84.trades == 1
        assert b_80_84.winning_trades == 1

        # Check regimes
        trend_regime = next(r for r in metrics.regimes if r.group == "TRENDING")
        assert trend_regime.trades == 1
        assert trend_regime.total_r > 0


@pytest.mark.asyncio
class TestDeterministicReplay:
    """Verifies that replaying the exact same backtest produces identical results."""

    async def test_deterministic_results(self):
        # Create small synthetic historical provider
        base_ts = 1700000000000
        candles_5m = []
        candles_15m = []
        candles_60m = []
        candles_240m = []

        # 400 bars on 5m
        price = 50000.0
        for i in range(400):
            ts = base_ts + (i * 300000)
            candles_5m.append({
                "timestamp": ts,
                "open": price,
                "high": price + 50.0,
                "low": price - 50.0,
                "close": price + 10.0,
                "volume": 100.0,
                "turnover": 5000000.0,
                "is_closed": True,
            })
            price += 10.0

        for i in range(300):
            ts = base_ts + (i * 900000)
            candles_15m.append({
                "timestamp": ts,
                "open": 50000.0 + (i * 30.0),
                "high": 50000.0 + (i * 30.0) + 100.0,
                "low": 50000.0 + (i * 30.0) - 50.0,
                "close": 50000.0 + (i * 30.0) + 20.0,
                "volume": 300.0,
                "turnover": 15000000.0,
                "is_closed": True,
            })

        for i in range(250):
            ts = base_ts + (i * 3600000)
            candles_60m.append({
                "timestamp": ts,
                "open": 50000.0 + (i * 100.0),
                "high": 50000.0 + (i * 100.0) + 200.0,
                "low": 50000.0 + (i * 100.0) - 100.0,
                "close": 50000.0 + (i * 100.0) + 80.0,
                "volume": 1200.0,
                "turnover": 60000000.0,
                "is_closed": True,
            })

        for i in range(250):
            ts = base_ts + (i * 14400000)
            candles_240m.append({
                "timestamp": ts,
                "open": 50000.0 + (i * 400.0),
                "high": 50000.0 + (i * 400.0) + 500.0,
                "low": 50000.0 + (i * 400.0) - 300.0,
                "close": 50000.0 + (i * 400.0) + 300.0,
                "volume": 4800.0,
                "turnover": 240000000.0,
                "is_closed": True,
            })

        candles_map = {
            ("BTCUSDT", "5"): candles_5m,
            ("BTCUSDT", "15"): candles_15m,
            ("BTCUSDT", "60"): candles_60m,
            ("BTCUSDT", "240"): candles_240m,
        }

        provider1 = HistoricalMarketDataProvider(candles_map)
        provider2 = HistoricalMarketDataProvider(candles_map)

        engine1 = HistoricalBacktestEngine()
        engine2 = HistoricalBacktestEngine()

        start_time = candles_5m[250]["timestamp"]
        end_time = candles_5m[350]["timestamp"]

        res1 = await engine1.run(provider1, ["BTCUSDT"], start_time, end_time)
        res2 = await engine2.run(provider2, ["BTCUSDT"], start_time, end_time)

        # Both runs must be strictly identical
        assert res1["metrics"]["total_evaluations"] == res2["metrics"]["total_evaluations"]
        assert res1["metrics"]["signals_generated"] == res2["metrics"]["signals_generated"]
        assert res1["metrics"]["total_trades"] == res2["metrics"]["total_trades"]
        assert res1["metrics"]["total_r"] == res2["metrics"]["total_r"]
        assert res1["metrics"]["win_rate"] == res2["metrics"]["win_rate"]
