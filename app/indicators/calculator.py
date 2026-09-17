"""Comprehensive Indicator Calculator orchestrating all technical indicator modules."""

from typing import Any

import numpy as np
import pandas as pd

from app.config import settings
from app.indicators.models import IndicatorSnapshot
from app.indicators.momentum import (
    compute_macd,
    compute_roc,
    compute_rsi,
    compute_stoch_rsi,
)
from app.indicators.trend import (
    compute_adx,
    compute_ema,
    compute_ema_distances,
    compute_ema_slope,
    get_ema_alignment,
)
from app.indicators.volatility import compute_atr, compute_bollinger_bands
from app.indicators.volume import (
    compute_obv,
    compute_rolling_vwap,
    compute_volume_metrics,
)


class IndicatorCalculator:
    """
    Computes all quantitative indicators for a given sequence of closed candles.
    Ensures deterministic calculations and strict protection against look-ahead bias.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        if config is None:
            config = settings.load_indicators_config().get("indicators", {})
        self.config = config
        self.warmup_bars = self.config.get("warmup_bars", 200)

        # EMA config
        ema_cfg = self.config.get("ema", {})
        self.ema_periods = ema_cfg.get("periods", [20, 50, 100, 200])
        self.ema_slope_period = ema_cfg.get("slope_period", 5)

        # ADX config
        self.adx_period = self.config.get("adx", {}).get("period", 14)

        # Momentum config
        self.rsi_period = self.config.get("rsi", {}).get("period", 14)
        stoch_cfg = self.config.get("stoch_rsi", {})
        self.stoch_rsi_period = stoch_cfg.get("rsi_period", 14)
        self.stoch_period = stoch_cfg.get("stoch_period", 14)
        self.stoch_k_period = stoch_cfg.get("k_period", 3)
        self.stoch_d_period = stoch_cfg.get("d_period", 3)

        macd_cfg = self.config.get("macd", {})
        self.macd_fast = macd_cfg.get("fast_period", 12)
        self.macd_slow = macd_cfg.get("slow_period", 26)
        self.macd_signal = macd_cfg.get("signal_period", 9)

        self.roc_period = self.config.get("roc", {}).get("period", 14)

        # Volatility config
        self.atr_period = self.config.get("atr", {}).get("period", 14)
        bb_cfg = self.config.get("bollinger", {})
        self.bb_period = bb_cfg.get("period", 20)
        self.bb_stddev = bb_cfg.get("stddev", 2.0)

        # Volume config
        vol_cfg = self.config.get("volume", {})
        self.vol_sma_period = vol_cfg.get("sma_period", 20)
        self.vwap_window = vol_cfg.get("vwap_window_bars", 288)

    def candles_to_dataframe(self, candles: list[dict[str, Any]]) -> pd.DataFrame:
        """Converts candle dict list into a validated, sorted pandas DataFrame."""
        if not candles:
            return pd.DataFrame(
                columns=["timestamp", "open", "high", "low", "close", "volume", "turnover"]
            )

        df = pd.DataFrame(candles)
        # Ensure only closed candles are used
        if "is_closed" in df.columns:
            df = df[df["is_closed"] == True]

        df = df.sort_values("timestamp").reset_index(drop=True)
        # Convert numeric columns
        for col in ["open", "high", "low", "close", "volume", "turnover"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        return df

    def compute_all(
        self,
        symbol: str,
        timeframe: str,
        candles: list[dict[str, Any]],
    ) -> IndicatorSnapshot | None:
        """
        Computes all indicators and returns the latest IndicatorSnapshot.
        If candles are empty, returns None.
        If candle count < warmup_bars, returns snapshot with is_ready=False.
        """
        if not candles:
            return None

        df = self.candles_to_dataframe(candles)
        n_bars = len(df)
        if n_bars == 0:
            return None

        last_row = df.iloc[-1]
        ts = int(last_row["timestamp"])
        close_price = float(last_row["close"])
        vol = float(last_row["volume"])

        is_ready = n_bars >= self.warmup_bars

        # If data is insufficient for even minimal calculations
        if n_bars < 20:
            return IndicatorSnapshot(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=ts,
                close=close_price,
                is_ready=False,
                warmup_bars=n_bars,
                volume=vol,
            )

        # 1. EMAs
        ema20_series = compute_ema(df["close"], 20)
        ema50_series = compute_ema(df["close"], 50)
        ema100_series = compute_ema(df["close"], 100) if n_bars >= 100 else pd.Series(np.nan, index=df.index)
        ema200_series = compute_ema(df["close"], 200) if n_bars >= 200 else pd.Series(np.nan, index=df.index)

        # 2. Volatility (ATR, BB)
        atr_series, atr_pct_series = compute_atr(df["high"], df["low"], df["close"], self.atr_period)
        bb_upper, bb_mid, bb_lower, bb_bw, bb_pct_b = compute_bollinger_bands(
            df["close"], self.bb_period, self.bb_stddev
        )

        # 3. EMA Slopes & Distances
        ema_slope_20 = compute_ema_slope(ema20_series, atr_series, self.ema_slope_period)
        ema_slope_50 = compute_ema_slope(ema50_series, atr_series, self.ema_slope_period)
        dist_20_50, dist_50_200 = compute_ema_distances(ema20_series, ema50_series, ema200_series)

        # 4. ADX
        adx_series, plus_di_series, minus_di_series = compute_adx(
            df["high"], df["low"], df["close"], self.adx_period
        )

        # 5. Momentum (RSI, StochRSI, MACD, ROC)
        rsi_series = compute_rsi(df["close"], self.rsi_period)
        stoch_k_series, stoch_d_series = compute_stoch_rsi(
            df["close"],
            self.stoch_rsi_period,
            self.stoch_period,
            self.stoch_k_period,
            self.stoch_d_period,
        )
        macd_line, macd_sig, macd_hist = compute_macd(
            df["close"], self.macd_fast, self.macd_slow, self.macd_signal
        )
        roc_series = compute_roc(df["close"], self.roc_period)

        # 6. Volume metrics & VWAP
        vol_sma, vol_ratio = compute_volume_metrics(df["volume"], self.vol_sma_period)
        vwap_series = compute_rolling_vwap(
            df["high"], df["low"], df["close"], df["volume"], self.vwap_window
        )
        obv_series, obv_slope_series = compute_obv(df["close"], df["volume"], slope_n=5)

        # Helper to safely extract float
        def _get_float(series: pd.Series) -> float | None:
            val = series.iloc[-1]
            if pd.isna(val) or np.isinf(val):
                return None
            return float(val)

        # EMA alignment
        e20_val = _get_float(ema20_series)
        e50_val = _get_float(ema50_series)
        e100_val = _get_float(ema100_series)
        e200_val = _get_float(ema200_series)

        if e20_val is not None and e50_val is not None and e100_val is not None and e200_val is not None:
            alignment = get_ema_alignment(e20_val, e50_val, e100_val, e200_val)
        else:
            alignment = "UNKNOWN"

        return IndicatorSnapshot(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=ts,
            close=close_price,
            is_ready=is_ready,
            warmup_bars=n_bars,
            # EMAs
            ema20=e20_val,
            ema50=e50_val,
            ema100=e100_val,
            ema200=e200_val,
            ema_slope_20=_get_float(ema_slope_20),
            ema_slope_50=_get_float(ema_slope_50),
            ema_distance_20_50_pct=_get_float(dist_20_50),
            ema_distance_50_200_pct=_get_float(dist_50_200),
            ema_alignment=alignment,
            # ADX
            adx=_get_float(adx_series),
            plus_di=_get_float(plus_di_series),
            minus_di=_get_float(minus_di_series),
            # Momentum
            rsi=_get_float(rsi_series),
            stoch_rsi_k=_get_float(stoch_k_series),
            stoch_rsi_d=_get_float(stoch_d_series),
            macd_line=_get_float(macd_line),
            macd_signal=_get_float(macd_sig),
            macd_hist=_get_float(macd_hist),
            roc=_get_float(roc_series),
            # Volatility
            atr=_get_float(atr_series),
            atr_pct=_get_float(atr_pct_series),
            bb_upper=_get_float(bb_upper),
            bb_middle=_get_float(bb_mid),
            bb_lower=_get_float(bb_lower),
            bb_bandwidth=_get_float(bb_bw),
            bb_percent_b=_get_float(bb_pct_b),
            # Volume
            volume=vol,
            volume_sma=_get_float(vol_sma),
            volume_ratio=_get_float(vol_ratio),
            vwap=_get_float(vwap_series),
            obv=_get_float(obv_series),
            obv_slope=_get_float(obv_slope_series),
        )
