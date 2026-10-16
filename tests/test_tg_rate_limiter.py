import pytest

from zxtg.core.platform.tg.protocol import TelegramRetryAfterError
from zxtg.core.platform.tg.rlmgr import FakeClock, RateLimiter, TokenBucket


@pytest.mark.asyncio
async def test_token_bucket_burst_and_throttle():
    """Verify group chat token bucket allows 20 bursts and throttles 21st (FR-TG-02)."""
    clock = FakeClock(start=100.0)
    # Rate: 20 per 60s (1/3 token per second), capacity: 20 tokens
    bucket = TokenBucket(rate=20.0 / 60.0, capacity=20.0)

    # First 20 acquisitions succeed immediately
    for _ in range(20):
        waited = await bucket.acquire(clock.time(), clock.sleep)
        assert waited == 0.0

    assert bucket.tokens == pytest.approx(0.0)
    assert len(clock.sleep_calls) == 0

    # 21st acquisition must wait for 1 token = 1 / (20/60) = 3.0 seconds
    waited_21 = await bucket.acquire(clock.time(), clock.sleep)
    assert waited_21 == pytest.approx(3.0)
    assert clock.time() == pytest.approx(103.0)
    assert len(clock.sleep_calls) == 1
    assert clock.sleep_calls[0] == pytest.approx(3.0)


@pytest.mark.asyncio
async def test_retry_after_backoff_and_eventual_delivery():
    """Verify 429 Retry-After is respected and message is eventually delivered (FR-TG-03)."""
    clock = FakeClock(start=500.0)
    rlmgr = RateLimiter(time_fn=clock.time, sleep_fn=clock.sleep)

    attempts = 0

    async def flaky_send() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise TelegramRetryAfterError(429, "Too Many Requests", retry_after=7.5)
        return "delivered"

    res = await rlmgr.execute("-100123456", flaky_send)
    assert res == "delivered"
    assert attempts == 2
    # Verify rate limiter slept for the Retry-After duration
    assert 7.5 in clock.sleep_calls
    assert clock.time() >= 507.5


@pytest.mark.asyncio
async def test_offline_a5_batch_delivery_under_burst_and_retry_after():
    """Offline A5 verification: send 25 messages, handle bursts and 429s, all delivered."""
    clock = FakeClock(start=1000.0)
    rlmgr = RateLimiter(time_fn=clock.time, sleep_fn=clock.sleep)
    chat_id = "-100999"

    delivered_messages: list[int] = []
    retry_injected_at = 22

    async def send_msg(seq: int) -> int:
        nonlocal retry_injected_at
        if seq == retry_injected_at:
            retry_injected_at = -1  # only trigger once
            raise TelegramRetryAfterError(429, "Flood control", retry_after=12.0)
        delivered_messages.append(seq)
        return seq

    for i in range(1, 26):
        await rlmgr.execute(chat_id, lambda seq=i: send_msg(seq))

    # All 25 messages delivered in sequential order
    assert delivered_messages == list(range(1, 26))
    # Clock advanced due to token bucket throttling (5 throttles * 3s) + Retry-After (12s)
    assert 12.0 in clock.sleep_calls
    assert clock.time() > 1000.0
