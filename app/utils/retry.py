"""Retry utility with exponential backoff and jitter for asynchronous operations."""

import asyncio
import functools
import logging
import random
from collections.abc import Callable
from typing import Any

logger = logging.getLogger("signal_engine.retry")


def async_retry(
    max_retries: int = 5,
    initial_delay: float = 0.5,
    max_delay: float = 10.0,
    backoff_factor: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable:
    """Decorator for retrying async functions with exponential backoff and jitter."""

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            delay = initial_delay
            last_exception: Exception | None = None

            for attempt in range(1, max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as exc:
                    last_exception = exc
                    if attempt == max_retries:
                        logger.error(
                            f"Function {func.__name__} failed permanently after {max_retries} attempts. Error: {exc}"
                        )
                        raise

                    jitter = random.uniform(0.8, 1.2)
                    sleep_time = min(delay * jitter, max_delay)
                    logger.warning(
                        f"Attempt {attempt}/{max_retries} of {func.__name__} failed: {exc}. "
                        f"Retrying in {sleep_time:.2f}s..."
                    )
                    await asyncio.sleep(sleep_time)
                    delay *= backoff_factor

            if last_exception:
                raise last_exception

        return wrapper

    return decorator
