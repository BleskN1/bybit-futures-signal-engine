"""Token Bucket Rate Limiter for API endpoints."""

import asyncio
import time


class AsyncTokenBucketRateLimiter:
    """Asynchronous Token Bucket Rate Limiter to respect exchange rate limits."""

    def __init__(self, rate: float, capacity: float):
        """
        Args:
            rate: Tokens added per second.
            capacity: Maximum bucket token capacity.
        """
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: float = 1.0) -> None:
        """Acquires specified tokens, waiting if necessary."""
        async with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self.last_update
                self.last_update = now
                self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)

                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return

                needed = tokens - self.tokens
                wait_time = needed / self.rate
                await asyncio.sleep(wait_time)
