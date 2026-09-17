"""Tests for MarketDataProvider and look-ahead bias prevention."""

from app.market_data.provider import LiveMarketDataProvider


def test_market_provider_lookahead_and_closed_bars():
    """Ensures provider strictly excludes unclosed bars and bars > as_of timestamp."""
    provider = LiveMarketDataProvider(max_buffer_size=100)

    # 1. Unclosed candle should be rejected from the analysis buffer
    unclosed_bar = {
        "timestamp": 1000,
        "open": 100.0,
        "high": 105.0,
        "low": 98.0,
        "close": 103.0,
        "volume": 50.0,
        "is_closed": False,
    }
    assert provider.update_candle("BTCUSDT", "5", unclosed_bar) is False
    assert len(provider.get_candles("BTCUSDT", "5")) == 0

    # 2. Add sequence of closed bars: T=1000, 2000, 3000, 4000
    for ts in [1000, 2000, 3000, 4000]:
        bar = {
            "timestamp": ts,
            "open": 100.0 + ts / 1000,
            "high": 105.0 + ts / 1000,
            "low": 95.0 + ts / 1000,
            "close": 102.0 + ts / 1000,
            "volume": 10.0,
            "is_closed": True,
        }
        provider.update_candle("BTCUSDT", "5", bar)

    assert len(provider.get_candles("BTCUSDT", "5")) == 4

    # 3. Test look-ahead bias prevention: as_of = 2500 should only return T=1000 and T=2000
    candles_as_of = provider.get_candles("BTCUSDT", "5", as_of=2500)
    assert len(candles_as_of) == 2
    assert [c["timestamp"] for c in candles_as_of] == [1000, 2000]

    # as_of = 1000 should return only T=1000
    candles_t1000 = provider.get_candles("BTCUSDT", "5", as_of=1000)
    assert len(candles_t1000) == 1
    assert candles_t1000[0]["timestamp"] == 1000
