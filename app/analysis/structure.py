"""Market structure engine: Swing detection, HH/HL/LH/LL, BOS, and CHOCH."""

import pandas as pd

from app.analysis.models import (
    BreakType,
    MarketStructureState,
    StructureBreakEvent,
    SwingPoint,
    SwingType,
)


def detect_swings(
    df: pd.DataFrame, left_bars: int = 3, right_bars: int = 3
) -> list[SwingPoint]:
    """
    Detects pivot swing highs and swing lows across historical closed candles.
    
    Guarantees strict zero look-ahead bias:
    A swing bar at index `i` is ONLY confirmed and visible at index `i + right_bars`
    (timestamp = df['timestamp'].iloc[i + right_bars]).
    """
    n_bars = len(df)
    if n_bars < (left_bars + right_bars + 1):
        return []

    highs = df["high"].values
    lows = df["low"].values
    timestamps = df["timestamp"].values

    raw_swings: list[SwingPoint] = []

    for i in range(left_bars, n_bars - right_bars):
        # 1. Check Swing High
        curr_high = highs[i]
        left_window_h = highs[i - left_bars : i]
        right_window_h = highs[i + 1 : i + 1 + right_bars]

        if curr_high >= left_window_h.max() and curr_high > right_window_h.max():
            conf_idx = i + right_bars
            raw_swings.append(
                SwingPoint(
                    index=i,
                    timestamp=int(timestamps[i]),
                    type=SwingType.HIGH,
                    price=float(curr_high),
                    confirmed_index=conf_idx,
                    confirmed_timestamp=int(timestamps[conf_idx]),
                )
            )

        # 2. Check Swing Low
        curr_low = lows[i]
        left_window_l = lows[i - left_bars : i]
        right_window_l = lows[i + 1 : i + 1 + right_bars]

        if curr_low <= left_window_l.min() and curr_low < right_window_l.min():
            conf_idx = i + right_bars
            raw_swings.append(
                SwingPoint(
                    index=i,
                    timestamp=int(timestamps[i]),
                    type=SwingType.LOW,
                    price=float(curr_low),
                    confirmed_index=conf_idx,
                    confirmed_timestamp=int(timestamps[conf_idx]),
                )
            )

    # Sort swings chronologically by confirmation time (so they appear in order of availability)
    raw_swings.sort(key=lambda s: (s.confirmed_index, s.index))

    # Assign HH, LH, HL, LL labels
    labeled_swings: list[SwingPoint] = []
    last_high: SwingPoint | None = None
    last_low: SwingPoint | None = None

    for s in raw_swings:
        if s.type == SwingType.HIGH:
            if last_high is None:
                s.label = "HIGH"
            elif s.price > last_high.price:
                s.label = "HH"
            else:
                s.label = "LH"
            last_high = s
        else:
            if last_low is None:
                s.label = "LOW"
            elif s.price > last_low.price:
                s.label = "HL"
            else:
                s.label = "LL"
            last_low = s

        labeled_swings.append(s)

    return labeled_swings


class MarketStructureAnalyzer:
    """
    Evaluates market structure (BOS, CHOCH, MarketStructureState) as of candle index T.
    Ensures that at time T, only swings confirmed at or before T (confirmed_index <= T) are considered.
    """

    def __init__(self, left_bars: int = 3, right_bars: int = 3):
        self.left_bars = left_bars
        self.right_bars = right_bars

    def analyze_structure(
        self, df: pd.DataFrame, as_of_index: int | None = None
    ) -> tuple[
        MarketStructureState,
        SwingPoint | None,
        SwingPoint | None,
        list[SwingPoint],
        StructureBreakEvent | None,
    ]:
        """
        Analyzes market structure up to `as_of_index` (default: last bar).
        Returns:
            - MarketStructureState (BULLISH, BEARISH, RANGE, UNKNOWN)
            - last_swing_high (active confirmed swing high)
            - last_swing_low (active confirmed swing low)
            - confirmed_swings (list of visible confirmed swings)
            - latest_break (BOS or CHOCH event on this candle, if any)
        """
        n_bars = len(df)
        if n_bars == 0:
            return MarketStructureState.UNKNOWN, None, None, [], None

        if as_of_index is None or as_of_index >= n_bars:
            as_of_index = n_bars - 1

        all_swings = detect_swings(df.iloc[: as_of_index + 1], self.left_bars, self.right_bars)

        # Filter: only swings whose confirmation index <= as_of_index
        confirmed_swings = [s for s in all_swings if s.confirmed_index <= as_of_index]

        high_swings = [s for s in confirmed_swings if s.type == SwingType.HIGH]
        low_swings = [s for s in confirmed_swings if s.type == SwingType.LOW]

        last_high = high_swings[-1] if high_swings else None
        last_low = low_swings[-1] if low_swings else None

        # Current bar details
        curr_bar = df.iloc[as_of_index]
        curr_close = float(curr_bar["close"])
        curr_high = float(curr_bar["high"])
        curr_low = float(curr_bar["low"])
        curr_ts = int(curr_bar["timestamp"])

        # Determine baseline structure state from recent swings
        state = MarketStructureState.UNKNOWN
        if len(high_swings) >= 2 and len(low_swings) >= 2:
            prev_h, curr_h = high_swings[-2], high_swings[-1]
            prev_l, curr_l = low_swings[-2], low_swings[-1]

            is_hh = curr_h.price > prev_h.price
            is_hl = curr_l.price > prev_l.price
            is_lh = curr_h.price < prev_h.price
            is_ll = curr_l.price < prev_l.price

            if is_hh and is_hl:
                state = MarketStructureState.BULLISH
            elif is_lh and is_ll:
                state = MarketStructureState.BEARISH
            elif is_hh and not is_ll:
                state = MarketStructureState.BULLISH
            elif is_ll and not is_hh:
                state = MarketStructureState.BEARISH
            else:
                state = MarketStructureState.RANGE
        elif len(high_swings) >= 2 and len(low_swings) >= 1:
            prev_h, curr_h = high_swings[-2], high_swings[-1]
            if curr_h.price > prev_h.price and curr_close >= low_swings[-1].price:
                state = MarketStructureState.BULLISH
            elif curr_h.price < prev_h.price and curr_close <= low_swings[-1].price:
                state = MarketStructureState.BEARISH
            else:
                state = MarketStructureState.RANGE
        elif len(low_swings) >= 2 and len(high_swings) >= 1:
            prev_l, curr_l = low_swings[-2], low_swings[-1]
            if curr_l.price > prev_l.price and curr_close >= curr_l.price:
                state = MarketStructureState.BULLISH
            elif curr_l.price < prev_l.price and curr_close <= high_swings[-1].price:
                state = MarketStructureState.BEARISH
            else:
                state = MarketStructureState.RANGE
        elif len(high_swings) >= 1 and len(low_swings) >= 1:
            state = MarketStructureState.RANGE

        # Check for BOS / CHOCH on the current bar
        latest_break: StructureBreakEvent | None = None

        # A break occurs if current candle CLOSE pierces beyond the last confirmed swing level
        # Note: The candle that established the swing cannot break itself; swing must have formed before as_of_index
        if (
            last_high is not None
            and last_high.index < as_of_index
            and curr_close > last_high.price
        ):
            # Candle broke above confirmed Swing High
            if state == MarketStructureState.BEARISH:
                break_type = BreakType.CHOCH_BULLISH
                desc = f"CHOCH Bullish: Closed {curr_close:.2f} above bearish Swing High {last_high.price:.2f}"
                state = MarketStructureState.BULLISH
            else:
                break_type = BreakType.BOS_BULLISH
                desc = f"BOS Bullish: Closed {curr_close:.2f} above prior Swing High {last_high.price:.2f}"
                state = MarketStructureState.BULLISH

            latest_break = StructureBreakEvent(
                break_type=break_type,
                timestamp=curr_ts,
                swing_level=last_high.price,
                breakout_price=curr_high,
                close_price=curr_close,
                swing_timestamp=last_high.timestamp,
                description=desc,
            )

        if (
            last_low is not None
            and last_low.index < as_of_index
            and latest_break is None
            and curr_close < last_low.price
        ):
            # Candle broke below confirmed Swing Low
            if state == MarketStructureState.BULLISH:
                break_type = BreakType.CHOCH_BEARISH
                desc = f"CHOCH Bearish: Closed {curr_close:.2f} below bullish Swing Low {last_low.price:.2f}"
                state = MarketStructureState.BEARISH
            else:
                break_type = BreakType.BOS_BEARISH
                desc = f"BOS Bearish: Closed {curr_close:.2f} below prior Swing Low {last_low.price:.2f}"
                state = MarketStructureState.BEARISH

            latest_break = StructureBreakEvent(
                break_type=break_type,
                timestamp=curr_ts,
                swing_level=last_low.price,
                breakout_price=curr_low,
                close_price=curr_close,
                swing_timestamp=last_low.timestamp,
                description=desc,
            )

        return state, last_high, last_low, confirmed_swings[-10:], latest_break
