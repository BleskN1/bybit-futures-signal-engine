"""Logging configuration for Bybit Futures Signal Engine."""

import logging
import sys


def setup_logger(name: str = "signal_engine", level: str | None = "INFO") -> logging.Logger:
    """Configures structured console logging with ISO timestamps and logger context."""
    logger = logging.getLogger(name)
    log_level = getattr(logging, (level or "INFO").upper(), logging.INFO)
    logger.setLevel(log_level)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(log_level)
        formatter = logging.Formatter(
            fmt="%(asctime)s.%(msecs)03d UTC [%(levelname)s] [%(name)s:%(funcName)s]: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    logger.propagate = False
    return logger
