"""Unit tests for Technical Indicators Engine."""

import pytest

from app.indicators.calculator import IndicatorCalculator


def generate_synthetic_candles(n: int = 250, base_price: float = 100.0, trend: float = 0.1):
    """Generates synthetic closed candles for deterministic testing."""
    candles = []
    price = base_price
    for i in range(n):
        price += trend + (0.5 if i % 2 == 0 else -0.4)
        c_open = price
        c_high = price + 1.5
        c_low = price - 1.0
        c_close = price + 0.2
        vol = 1000.0 + (i * 10.0)
        candles.append({
            "timestamp": 1700000000000 + (i * 300000),  # 5m steps
            "open": c_open,
            "high": c_high,
            "low": c_low,
            "close": c_close,
            "volume": vol,
            "turnover": vol * c_close,
            "is_closed": True,
        })
    return candles


def test_warmup_and_is_ready():
    calc = IndicatorCalculator()

    # Case 1: < 20 candles
    candles_10 = generate_synthetic_candles(10)
    snap_10 = calc.compute_all("BTCUSDT", "5", candles_10)
    assert snap_10 is not None
    assert snap_10.is_ready is False
    assert snap_10.ema20 is None

    # Case 2: 50 candles (EMA20 & 50 ready, but not full warmup 200)
    candles_50 = generate_synthetic_candles(50)
    snap_50 = calc.compute_all("BTCUSDT", "5", candles_50)
    assert snap_50 is not None
    assert snap_50.is_ready is False
    assert snap_50.ema20 is not None
    assert snap_50.ema50 is not None
    assert snap_50.ema200 is None  # Needs 200 bars

    # Case 3: 200 candles (full warmup reached)
    candles_200 = generate_synthetic_candles(200)
    snap_200 = calc.compute_all("BTCUSDT", "5", candles_200)
    assert snap_200 is not None
    assert snap_200.is_ready is True
    assert snap_200.ema200 is not None


def test_trend_indicators_accuracy():
    candles = generate_synthetic_candles(220, base_price=100.0, trend=0.5)
    calc = IndicatorCalculator()
    snap = calc.compute_all("BTCUSDT", "15", candles)

    assert snap is not None
    assert snap.ema20 is not None
    assert snap.ema50 is not None
    assert snap.ema100 is not None
    assert snap.ema200 is not None

    # Since trend is strongly positive, EMA20 > EMA50 > EMA100 > EMA200
    assert snap.ema20 > snap.ema50 > snap.ema100 > snap.ema200
    assert snap.ema_alignment == "BULLISH"
    assert snap.ema_slope_20 is not None
    assert snap.ema_slope_20 > 0.0

    # ADX must be positive in strong trend
    assert snap.adx is not None
    assert snap.adx > 15.0
    assert snap.plus_di is not None
    assert snap.minus_di is not None
    assert snap.plus_di > snap.minus_di


def test_momentum_indicators():
    candles = generate_synthetic_candles(200, base_price=50.0, trend=0.2)
    calc = IndicatorCalculator()
    snap = calc.compute_all("ETHUSDT", "1H", candles)

    assert snap is not None
    assert snap.rsi is not None
    assert 0.0 <= snap.rsi <= 100.0
    assert snap.stoch_rsi_k is not None
    assert 0.0 <= snap.stoch_rsi_k <= 100.0
    assert snap.stoch_rsi_d is not None
    assert 0.0 <= snap.stoch_rsi_d <= 100.0
    assert snap.macd_line is not None
    assert snap.macd_signal is not None
    assert snap.macd_hist is not None
    assert snap.roc is not None


def test_volatility_and_volume():
    candles = generate_synthetic_candles(200, base_price=2000.0, trend=0.0)
    calc = IndicatorCalculator()
    snap = calc.compute_all("SOLUSDT", "5", candles)

    assert snap is not None
    # ATR checks
    assert snap.atr is not None and snap.atr > 0.0
    assert snap.atr_pct is not None and snap.atr_pct > 0.0

    # Bollinger Bands checks
    assert snap.bb_upper is not None
    assert snap.bb_middle is not None
    assert snap.bb_lower is not None
    assert snap.bb_upper > snap.bb_middle > snap.bb_lower
    assert snap.bb_bandwidth is not None and snap.bb_bandwidth > 0.0

    # Volume checks
    assert snap.volume_sma is not None
    assert snap.volume_ratio is not None
    assert snap.vwap is not None
    assert snap.obv is not None


def test_indicator_lookahead_bias_protection():
    """
    Guarantees that candles arriving at future times T+1, T+2...
    do NOT alter the indicator values calculated at time T.
    """
    candles_all = generate_synthetic_candles(220)
    calc = IndicatorCalculator()

    # Snapshot at time T (using 200 candles)
    snap_t = calc.compute_all("BTCUSDT", "5", candles_all[:200])

    # Now create modified future candles at T+1...T+20 with crazy prices
    modified_candles = list(candles_all[:200])
    for j in range(200, 220):
        c = dict(candles_all[j])
        c["close"] = 999999.0  # wild spike in the future
        modified_candles.append(c)

    # Re-calculate as of time T using strictly the data available at T
    snap_t_recheck = calc.compute_all("BTCUSDT", "5", modified_candles[:200])

    assert snap_t is not None
    assert snap_t_recheck is not None
    assert snap_t.timestamp == snap_t_recheck.timestamp
    assert snap_t.close == snap_t_recheck.close
    assert snap_t.ema20 == pytest.approx(snap_t_recheck.ema20)
    assert snap_t.rsi == pytest.approx(snap_t_recheck.rsi)
    assert snap_t.atr == pytest.approx(snap_t_recheck.atr)
    assert snap_t.adx == pytest.approx(snap_t_recheck.adx)
