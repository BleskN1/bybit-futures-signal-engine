"""Data models for technical indicators."""

from pydantic import BaseModel, Field


class IndicatorSnapshot(BaseModel):
    """
    Complete snapshot of computed technical indicators for a specific symbol,
    timeframe, and closed candle timestamp.
    """

    symbol: str
    timeframe: str
    timestamp: int  # Epoch ms of the closed candle
    close: float
    is_ready: bool = Field(
        default=False,
        description="True if minimum historical warmup bars were met and values are valid",
    )
    warmup_bars: int = Field(default=0, description="Number of closed bars used in calculation")

    # Trend Indicators
    ema20: float | None = None
    ema50: float | None = None
    ema100: float | None = None
    ema200: float | None = None
    ema_slope_20: float | None = Field(
        default=None,
        description="Slope of EMA20 normalized by ATR: (EMA20[t] - EMA20[t-n]) / ATR[t]",
    )
    ema_slope_50: float | None = Field(
        default=None,
        description="Slope of EMA50 normalized by ATR: (EMA50[t] - EMA50[t-n]) / ATR[t]",
    )
    ema_distance_20_50_pct: float | None = Field(
        default=None,
        description="Percentage distance: (EMA20 - EMA50) / EMA50 * 100",
    )
    ema_distance_50_200_pct: float | None = Field(
        default=None,
        description="Percentage distance: (EMA50 - EMA200) / EMA200 * 100",
    )
    ema_alignment: str = Field(
        default="UNKNOWN",
        description="BULLISH (20>50>100>200) | BEARISH (20<50<100<200) | MIXED | UNKNOWN",
    )

    # ADX / Directional Movement
    adx: float | None = Field(default=None, description="14-period ADX (Welles Wilder)")
    plus_di: float | None = Field(default=None, description="+DI (14)")
    minus_di: float | None = Field(default=None, description="-DI (14)")

    # Momentum Indicators
    rsi: float | None = Field(default=None, description="14-period RSI (Welles Wilder smoothing)")
    stoch_rsi_k: float | None = Field(default=None, description="StochRSI %K (FastK 3-period SMA)")
    stoch_rsi_d: float | None = Field(default=None, description="StochRSI %D (%K 3-period SMA)")
    macd_line: float | None = Field(default=None, description="MACD line (EMA12 - EMA26)")
    macd_signal: float | None = Field(default=None, description="MACD signal line (EMA9)")
    macd_hist: float | None = Field(default=None, description="MACD histogram (line - signal)")
    roc: float | None = Field(default=None, description="14-period Rate of Change (%)")

    # Volatility Indicators
    atr: float | None = Field(default=None, description="14-period Average True Range")
    atr_pct: float | None = Field(default=None, description="ATR as percentage of close: ATR / Close * 100")
    bb_upper: float | None = Field(default=None, description="Bollinger upper band (SMA20 + 2*std)")
    bb_middle: float | None = Field(default=None, description="Bollinger middle band (SMA20)")
    bb_lower: float | None = Field(default=None, description="Bollinger lower band (SMA20 - 2*std)")
    bb_bandwidth: float | None = Field(
        default=None,
        description="Bollinger bandwidth: (Upper - Lower) / Middle",
    )
    bb_percent_b: float | None = Field(
        default=None,
        description="Bollinger %B: (Close - Lower) / (Upper - Lower)",
    )

    # Volume & Money Flow
    volume: float = 0.0
    volume_sma: float | None = Field(default=None, description="20-period SMA of volume")
    volume_ratio: float | None = Field(
        default=None,
        description="Volume ratio vs 20-period SMA: Volume / Volume_SMA",
    )
    vwap: float | None = Field(default=None, description="Rolling VWAP over configurable window")
    obv: float | None = Field(default=None, description="On-Balance Volume")
    obv_slope: float | None = Field(default=None, description="5-period OBV normalized rate of change")
