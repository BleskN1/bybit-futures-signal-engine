"""Market Structure Engine synthesizing swing analysis, liquidity sweeps, and price action."""

from typing import Any

import pandas as pd

from app.analysis.models import (
    PriceActionSnapshot,
)
from app.analysis.price_action import (
    detect_candle_patterns,
    detect_liquidity_sweep,
    determine_market_regime,
)
from app.analysis.structure import MarketStructureAnalyzer
from app.config import settings
from app.indicators.models import IndicatorSnapshot


class MarketStructureEngine:
    """
    Synthesizes Market Structure and Price Action Analysis for a symbol and timeframe.
    Works deterministically on LiveMarketDataProvider, HistoricalMarketDataProvider,
    and backtest engines.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        if config is None:
            config = settings.load_indicators_config().get("market_structure", {})
        self.config = config

        swing_cfg = self.config.get("swing", {})
        self.left_bars = swing_cfg.get("left_bars", 3)
        self.right_bars = swing_cfg.get("right_bars", 3)

        rej_cfg = self.config.get("rejection", {})
        self.min_wick_ratio = rej_cfg.get("min_wick_ratio", 0.60)
        self.max_body_ratio = rej_cfg.get("max_body_ratio", 0.35)
        self.min_range_atr = rej_cfg.get("min_range_atr", 0.80)

        eng_cfg = self.config.get("engulfing", {})
        self.engulf_range_atr = eng_cfg.get("min_range_atr", 0.50)

        reg_cfg = self.config.get("regime", {})
        self.consolidation_bw = reg_cfg.get("consolidation_bb_bandwidth", 0.035)
        self.expansion_vol_ratio = reg_cfg.get("expansion_volume_ratio", 1.5)
        self.expansion_atr_ratio = reg_cfg.get("expansion_atr_ratio", 1.25)

        self.analyzer = MarketStructureAnalyzer(
            left_bars=self.left_bars, right_bars=self.right_bars
        )

    def analyze(
        self,
        symbol: str,
        timeframe: str,
        candles: list[dict[str, Any]],
        indicator_snapshot: IndicatorSnapshot | None = None,
    ) -> PriceActionSnapshot | None:
        """
        Analyzes closed candles strictly up to the latest closed candle.
        Guarantees zero look-ahead bias.
        """
        if not candles:
            return None

        df = pd.DataFrame(candles)
        if "is_closed" in df.columns:
            df = df[df["is_closed"] == True]

        df = df.sort_values("timestamp").reset_index(drop=True)
        n_bars = len(df)
        if n_bars == 0:
            return None

        # Convert numeric columns
        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        last_idx = n_bars - 1
        curr_bar = df.iloc[last_idx]
        prev_bar = df.iloc[last_idx - 1] if last_idx > 0 else None

        ts = int(curr_bar["timestamp"])
        close_price = float(curr_bar["close"])
        candle_range = float(curr_bar["high"]) - float(curr_bar["low"])

        # 1. Structure Analysis (Swings, HH/HL/LH/LL, BOS, CHOCH)
        state, last_high, last_low, recent_swings, latest_break = self.analyzer.analyze_structure(
            df, as_of_index=last_idx
        )

        # 2. Liquidity Sweep
        latest_sweep = detect_liquidity_sweep(curr_bar, last_high, last_low)

        # 3. Candle Geometry (Rejection pinbar, Engulfing)
        atr_val = indicator_snapshot.atr if indicator_snapshot else None
        candle_event = detect_candle_patterns(
            curr_bar=curr_bar,
            prev_bar=prev_bar,
            atr=atr_val,
            min_wick_ratio=self.min_wick_ratio,
            max_body_ratio=self.max_body_ratio,
            min_range_atr=self.min_range_atr,
            engulf_range_atr=self.engulf_range_atr,
        )

        # 4. Market Regime (Consolidation vs Expansion vs Trending)
        bb_bw = indicator_snapshot.bb_bandwidth if indicator_snapshot else None
        vol_ratio = indicator_snapshot.volume_ratio if indicator_snapshot else None
        adx_val = indicator_snapshot.adx if indicator_snapshot else None
        alignment = indicator_snapshot.ema_alignment if indicator_snapshot else "UNKNOWN"

        regime = determine_market_regime(
            bb_bandwidth=bb_bw,
            volume_ratio=vol_ratio,
            candle_range=candle_range,
            atr=atr_val,
            adx=adx_val,
            ema_alignment=alignment,
            consolidation_bandwidth=self.consolidation_bw,
            expansion_volume_ratio=self.expansion_vol_ratio,
            expansion_atr_ratio=self.expansion_atr_ratio,
        )

        return PriceActionSnapshot(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=ts,
            close=close_price,
            structure_state=state,
            last_swing_high=last_high,
            last_swing_low=last_low,
            recent_swings=recent_swings,
            latest_break=latest_break,
            latest_sweep=latest_sweep,
            candle_event=candle_event,
            regime=regime,
            bb_bandwidth=bb_bw,
        )
