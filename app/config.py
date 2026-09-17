"""Application settings and configuration management."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Core application settings with environment variable priority."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Bybit Credentials
    BYBIT_API_KEY: str = Field(default="", description="Bybit API Key (read-only)")
    BYBIT_API_SECRET: str = Field(default="", description="Bybit API Secret")
    BYBIT_TESTNET: bool = Field(default=False, description="Use Bybit testnet if true")
    BYBIT_REST_URL: str = Field(default="https://api.bybit.com")
    BYBIT_WS_URL: str = Field(default="wss://stream.bybit.com/v5/public/linear")

    # Telegram Bot
    TELEGRAM_BOT_TOKEN: str = Field(default="", description="Telegram Bot Token")
    TELEGRAM_CHAT_ID: str = Field(default="", description="Telegram Chat ID")

    # Universe Selection
    TOP_SYMBOLS: int = Field(default=20, ge=5, le=100, description="Number of liquid pairs to monitor")
    TOP_REFRESH_INTERVAL_HOURS: int = Field(default=4, ge=1, le=24)
    BOOTSTRAP_CANDLE_COUNT: int = Field(default=2000, ge=200, le=5000, description="Initial closed candles per TF")

    # Signal & Scoring Constraints
    MIN_SCORE: float = Field(default=75.0, ge=0.0, le=100.0)
    MIN_DIRECTIONAL_EDGE: float = Field(default=5.0, ge=0.0, le=50.0)
    SIGNAL_COOLDOWN_MINUTES: int = Field(default=20, ge=1)

    # Paper Tracking Policy
    AMBIGUOUS_CANDLE_POLICY: str = Field(
        default="conservative",
        description="Policy for simultaneous TP/SL hit inside one candle: conservative | optimistic | unknown",
    )

    # Persistence & Logging
    DATABASE_URL: str = Field(default="sqlite+aiosqlite:///./data/signals.db")
    LOG_LEVEL: str = Field(default="INFO")

    # Config paths
    CONFIG_DIR: Path = Field(default=Path("config"))

    def load_scoring_config(self) -> dict[str, Any]:
        """Loads quantitative scoring weights and thresholds from YAML."""
        scoring_path = self.CONFIG_DIR / "scoring.yaml"
        if not scoring_path.exists():
            return {
                "weights": {
                    "htf_trend": 15,
                    "market_structure": 15,
                    "liquidity": 15,
                    "momentum": 10,
                    "volume": 10,
                    "volatility": 5,
                    "derivatives": 15,
                    "price_action": 15,
                },
                "thresholds": {
                    "ignore_max": 59,
                    "watch_min": 60,
                    "signal_min": 75,
                    "strong_signal_min": 85,
                    "min_directional_edge": 5,
                },
                "targets": {
                    "sl_atr_multiplier": 1.5,
                    "tp1_r_multiple": 1.0,
                    "tp2_r_multiple": 2.0,
                    "min_risk_reward": 1.8,
                },
            }
        with open(scoring_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def load_ranking_config(self) -> dict[str, Any]:
        """Loads universe selection and multi-factor ranking config from YAML."""
        ranking_path = self.CONFIG_DIR / "ranking.yaml"
        if not ranking_path.exists():
            return {
                "weights": {
                    "turnover_24h": 0.35,
                    "open_interest": 0.25,
                    "volume_24h": 0.15,
                    "volatility": 0.10,
                    "trades_activity": 0.10,
                    "spread_penalty": 0.05,
                },
                "filters": {
                    "min_turnover_24h_usdt": 10000000.0,
                    "min_open_interest_usdt": 2000000.0,
                    "max_bid_ask_spread_pct": 0.0015,
                    "min_history_candles": 2000,
                    "quote_coin": "USDT",
                    "contract_status": "Trading",
                },
            }
        with open(ranking_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def load_indicators_config(self) -> dict[str, Any]:
        """Loads technical indicators and market structure config from YAML."""
        ind_path = self.CONFIG_DIR / "indicators.yaml"
        if not ind_path.exists():
            return {
                "indicators": {
                    "ema": {"periods": [20, 50, 100, 200], "slope_period": 5},
                    "adx": {"period": 14},
                    "rsi": {"period": 14},
                    "stoch_rsi": {"rsi_period": 14, "stoch_period": 14, "k_period": 3, "d_period": 3},
                    "macd": {"fast_period": 12, "slow_period": 26, "signal_period": 9},
                    "roc": {"period": 14},
                    "atr": {"period": 14},
                    "bollinger": {"period": 20, "stddev": 2.0},
                    "volume": {"sma_period": 20, "vwap_window_bars": 288},
                    "warmup_bars": 200,
                },
                "market_structure": {
                    "swing": {"left_bars": 3, "right_bars": 3, "min_atr_distance": 0.5},
                    "rejection": {"min_wick_ratio": 0.6, "max_body_ratio": 0.35, "min_range_atr": 0.8},
                    "engulfing": {"min_body_ratio": 1.0, "min_range_atr": 0.5},
                    "regime": {
                        "consolidation_bb_bandwidth": 0.035,
                        "expansion_volume_ratio": 1.5,
                        "expansion_atr_ratio": 1.25,
                    },
                },
            }
        with open(ind_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def load_backtest_config(self) -> dict[str, Any]:
        """Loads historical backtest configuration from YAML."""
        bt_path = self.CONFIG_DIR / "backtest.yaml"
        if not bt_path.exists():
            return {
                "backtest": {
                    "start_date": "2026-08-15",
                    "end_date": "2026-09-15",
                    "eval_step_minutes": 5,
                    "universe": {"mode": "configured", "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"]},
                    "execution": {
                        "entry_mode": "zone_touch",
                        "max_bars_to_enter": 12,
                        "slippage": {"enabled": True, "bps": 2.0},
                        "ambiguous_candle": "conservative",
                    },
                    "fees": {"model": "taker", "taker_rate": 0.00055, "maker_rate": 0.00020},
                    "funding": {"enabled": True, "default_rate_per_8h": 0.0001},
                    "risk": {"risk_per_trade_pct": 1.0, "initial_capital": 10000.0},
                    "cache_dir": "data/historical",
                }
            }
        with open(bt_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)


settings = Settings()
