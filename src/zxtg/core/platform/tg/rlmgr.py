import asyncio
from collections.abc import Callable, Coroutine
import logging
import time
from typing import Any, TypeVar

from zxtg.core.platform.tg.protocol import TelegramRetryAfterError

logger = logging.getLogger("zxtg.platform.tg.rlmgr")

T = TypeVar("T")


class FakeClock:
    """In-memory fake clock for testing token bucket rate limits without real sleep."""

    def __init__(self, start: float = 1000.0) -> None:
        self.current_time = start
        self.sleep_calls: list[float] = []

    def time(self) -> float:
        return self.current_time

    async def sleep(self, seconds: float) -> None:
        if seconds > 0:
            self.sleep_calls.append(seconds)
            self.current_time += seconds
        await asyncio.sleep(0)


class TokenBucket:
    """Token bucket implementation for per-chat throughput throttling (FR-TG-02)."""

    def __init__(self, rate: float, capacity: float, initial_tokens: float | None = None) -> None:
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity if initial_tokens is None else initial_tokens
        self.last_update = 0.0

    async def acquire(
        self,
        now: float,
        sleep_fn: Callable[[float], Coroutine[Any, Any, None]],
    ) -> float:
        """Consume 1 token from bucket; sleep if tokens are insufficient."""
        if self.last_update == 0.0:
            self.last_update = now

        elapsed = max(0.0, now - self.last_update)
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_update = now

        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return 0.0

        needed = 1.0 - self.tokens
        wait_seconds = needed / self.rate
        await sleep_fn(wait_seconds)

        # Update bucket after waiting
        self.tokens = 0.0
        self.last_update = now + wait_seconds
        return wait_seconds


class RateLimiter:
    """Per-chat rate limiter and Retry-After backoff manager (FR-TG-02, FR-TG-03, FR-TG-04)."""

    def __init__(
        self,
        time_fn: Callable[[], float] = time.monotonic,
        sleep_fn: Callable[[float], Coroutine[Any, Any, None]] = asyncio.sleep,
        group_rate: float = 20.0 / 60.0,  # ~20 msgs per minute in groups
        group_capacity: float = 20.0,
        private_rate: float = 60.0 / 60.0,  # 60 msgs per minute in private chats
        private_capacity: float = 30.0,
    ) -> None:
        self._time_fn = time_fn
        self._sleep_fn = sleep_fn
        self._group_rate = group_rate
        self._group_capacity = group_capacity
        self._private_rate = private_rate
        self._private_capacity = private_capacity

        self._buckets: dict[str, TokenBucket] = {}
        self._retry_until: dict[str, float] = {}

    def _is_group(self, chat_id: int | str, is_group: bool | None = None) -> bool:
        if is_group is not None:
            return is_group
        cid_str = str(chat_id)
        return cid_str.startswith("-")

    def get_bucket(self, chat_id: int | str, is_group: bool | None = None) -> TokenBucket:
        cid_str = str(chat_id)
        if cid_str not in self._buckets:
            if self._is_group(chat_id, is_group):
                self._buckets[cid_str] = TokenBucket(rate=self._group_rate, capacity=self._group_capacity)
            else:
                self._buckets[cid_str] = TokenBucket(rate=self._private_rate, capacity=self._private_capacity)
        return self._buckets[cid_str]

    def record_retry_after(self, chat_id: int | str, seconds: float) -> None:
        """Record Retry-After cooldown received from Telegram API (FR-TG-03)."""
        cid_str = str(chat_id)
        now = self._time_fn()
        self._retry_until[cid_str] = now + seconds
        logger.warning("Chat %s throttled by Telegram Retry-After: wait %.2fs", cid_str, seconds)

    async def acquire(self, chat_id: int | str, is_group: bool | None = None) -> None:
        """Ensure both Retry-After cooldown and token bucket requirements are met."""
        cid_str = str(chat_id)
        now = self._time_fn()

        # 1. Obey Retry-After if currently active
        cooldown = self._retry_until.get(cid_str, 0.0)
        if cooldown > now:
            wait_time = cooldown - now
            await self._sleep_fn(wait_time)
            now = self._time_fn()

        # 2. Consume from token bucket
        bucket = self.get_bucket(chat_id, is_group)
        await bucket.acquire(now, self._sleep_fn)

    async def execute(
        self,
        chat_id: int | str,
        coro_fn: Callable[[], Coroutine[Any, Any, T]],
        is_group: bool | None = None,
    ) -> T:
        """Execute network call through rate limiter with automatic Retry-After retry (FR-TG-04)."""
        while True:
            await self.acquire(chat_id, is_group=is_group)
            try:
                return await coro_fn()
            except TelegramRetryAfterError as err:
                self.record_retry_after(chat_id, err.retry_after)
                await self._sleep_fn(err.retry_after)


__all__ = ["FakeClock", "TokenBucket", "RateLimiter"]
