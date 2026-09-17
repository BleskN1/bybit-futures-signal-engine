"""Entry Zone, Stop Loss, and Take Profit Level Calculator enforcing positive risk-to-reward."""

import math
from typing import Any, Literal

from app.analysis.models import SwingPoint, SwingType
from app.signal.mtf import MTFContext


class EntryLevelCalculator:
    """
    Computes precise entry zone, structure-based invalidation (Stop Loss),
    and target levels (TP1, TP2) with minimum Risk-to-Reward validation.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        cfg = config or {}
        scoring_cfg = cfg.get("scoring", cfg)

        risk_cfg = scoring_cfg.get("risk", {})
        self.min_rr_tp1 = float(risk_cfg.get("min_rr_tp1", 1.5))
        self.min_rr_tp2 = float(risk_cfg.get("min_rr_tp2", 2.0))
        self.tp1_r_multiple = float(risk_cfg.get("tp1_r_multiple", 1.5))
        self.tp2_r_multiple = float(risk_cfg.get("tp2_r_multiple", 3.0))

        entry_cfg = scoring_cfg.get("entry", {})
        self.entry_atr_buffer = float(entry_cfg.get("atr_buffer_multiplier", 0.2))

        sl_cfg = scoring_cfg.get("stop_loss", {})
        self.sl_atr_buffer = float(sl_cfg.get("atr_buffer_multiplier", 0.2))

    def calculate_levels(
        self,
        direction: Literal["LONG", "SHORT"],
        current_price: float,
        mtf: MTFContext,
    ) -> tuple[float, float, float, float, float, float, float] | None:
        """
        Calculates:
        (entry_zone_low, entry_zone_high, stop_loss, tp1, tp2, rr_tp1, rr_tp2)

        Returns None if geometric or R:R constraints cannot be fulfilled.
        """
        if current_price <= 0.0:
            return None

        # Determine reference ATR from 15M (fallback to 5M or 0.8% of price)
        m15_atr = mtf.m15.indicators.atr if (mtf.m15.indicators and mtf.m15.indicators.atr) else None
        m5_atr = mtf.m5.indicators.atr if (mtf.m5.indicators and mtf.m5.indicators.atr) else None
        atr = m15_atr or m5_atr or (current_price * 0.008)

        if atr <= 0.0:
            atr = current_price * 0.008

        # 1. Entry Zone
        entry_buffer = atr * self.entry_atr_buffer
        if direction == "LONG":
            entry_low = current_price - entry_buffer
            entry_high = current_price
        else:
            entry_low = current_price
            entry_high = current_price + entry_buffer

        entry_mid = (entry_low + entry_high) / 2.0

        # Collect confirmed swings from 15M and 1H
        swings_15m = mtf.m15.structure.recent_swings if mtf.m15.structure else []
        swings_1h = mtf.h1.structure.recent_swings if mtf.h1.structure else []
        all_swings = swings_15m + swings_1h

        # 2. Stop Loss Calculation
        sl_buffer = atr * self.sl_atr_buffer
        if direction == "LONG":
            # Invalidation: low of recent bullish sweep, or lowest swing low below entry
            sweep_low = None
            if mtf.m15.structure and mtf.m15.structure.latest_sweep:
                if mtf.m15.structure.latest_sweep.sweep_type == "BULLISH_SWEEP":
                    sweep_low = mtf.m15.structure.latest_sweep.extreme_price

            candidate_lows = [
                s.price for s in all_swings
                if s.type == SwingType.LOW and s.price < entry_low
            ]
            if sweep_low and sweep_low < entry_low:
                invalidation_level = sweep_low
            elif candidate_lows:
                invalidation_level = max(candidate_lows)  # closest confirmed structural low
            else:
                invalidation_level = entry_low - (1.2 * atr)

            stop_loss = invalidation_level - sl_buffer
            # Ensure SL is strictly below entry low
            if stop_loss >= entry_low:
                stop_loss = entry_low - (1.0 * atr)

        else:  # SHORT
            sweep_high = None
            if mtf.m15.structure and mtf.m15.structure.latest_sweep:
                if mtf.m15.structure.latest_sweep.sweep_type == "BEARISH_SWEEP":
                    sweep_high = mtf.m15.structure.latest_sweep.extreme_price

            candidate_highs = [
                s.price for s in all_swings
                if s.type == SwingType.HIGH and s.price > entry_high
            ]
            if sweep_high and sweep_high > entry_high:
                invalidation_level = sweep_high
            elif candidate_highs:
                invalidation_level = min(candidate_highs)  # closest confirmed structural high
            else:
                invalidation_level = entry_high + (1.2 * atr)

            stop_loss = invalidation_level + sl_buffer
            # Ensure SL is strictly above entry high
            if stop_loss <= entry_high:
                stop_loss = entry_high + (1.0 * atr)

        # 3. Risk Calculation
        risk = abs(entry_mid - stop_loss)
        if risk <= 0.0 or math.isnan(risk):
            return None

        # 4. Take Profit Levels
        if direction == "LONG":
            # Search for opposing swing highs
            target_highs = sorted([
                s.price for s in all_swings
                if s.type == SwingType.HIGH and s.price > entry_high
            ])

            # TP1: opposing swing high if R:R >= min_rr_tp1, else R-multiple
            tp1_target = entry_mid + (risk * self.tp1_r_multiple)
            for th in target_highs:
                if (th - entry_mid) >= (risk * self.min_rr_tp1):
                    tp1_target = th
                    break
            tp1 = max(tp1_target, entry_mid + (risk * self.min_rr_tp1))

            # TP2: next higher target or tp2_r_multiple
            tp2_target = entry_mid + (risk * self.tp2_r_multiple)
            for th in target_highs:
                if th > tp1 and (th - entry_mid) >= (risk * self.min_rr_tp2):
                    tp2_target = th
                    break
            tp2 = max(tp2_target, tp1 + (risk * 1.0))

            reward_1 = tp1 - entry_mid
            reward_2 = tp2 - entry_mid

        else:  # SHORT
            target_lows = sorted([
                s.price for s in all_swings
                if s.type == SwingType.LOW and s.price < entry_low
            ], reverse=True)

            tp1_target = entry_mid - (risk * self.tp1_r_multiple)
            for tl in target_lows:
                if (entry_mid - tl) >= (risk * self.min_rr_tp1):
                    tp1_target = tl
                    break
            tp1 = min(tp1_target, entry_mid - (risk * self.min_rr_tp1))

            tp2_target = entry_mid - (risk * self.tp2_r_multiple)
            for tl in target_lows:
                if tl < tp1 and (entry_mid - tl) >= (risk * self.min_rr_tp2):
                    tp2_target = tl
                    break
            tp2 = min(tp2_target, tp1 - (risk * 1.0))

            reward_1 = entry_mid - tp1
            reward_2 = entry_mid - tp2

        rr_tp1 = reward_1 / risk
        rr_tp2 = reward_2 / risk

        # Final sanity validations
        if direction == "LONG":
            if not (stop_loss < entry_low <= entry_high < tp1 < tp2):
                return None
        else:
            if not (stop_loss > entry_high >= entry_low > tp1 > tp2):
                return None

        return (
            round(entry_low, 4),
            round(entry_high, 4),
            round(stop_loss, 4),
            round(tp1, 4),
            round(tp2, 4),
            round(rr_tp1, 2),
            round(rr_tp2, 2),
        )
