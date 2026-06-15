from __future__ import annotations

from datetime import datetime

import pytest

from app.rate_limit import MemoryRateLimiter, RateLimitExceeded, RedisRateLimiter, build_rate_limiter


def test_rate_limiter_rejects_excess_requests():
    limiter = MemoryRateLimiter(limit=1)
    now = datetime(2026, 6, 15)
    limiter.check("user", now)
    with pytest.raises(RateLimitExceeded):
        limiter.check("user", now)


def test_noop_rate_limiter_allows_when_limit_disabled():
    limiter = MemoryRateLimiter(limit=0)
    now = datetime(2026, 6, 15)
    for _ in range(10):
        limiter.check("user", now)


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.expire_calls = []

    def incr(self, key):
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]

    def expire(self, key, seconds):
        self.expire_calls.append((key, seconds))


def test_redis_rate_limiter_uses_counter_and_expiry():
    fake = FakeRedis()
    limiter = RedisRateLimiter(fake, limit=2, window_seconds=60)

    limiter.check("user")
    limiter.check("user")
    with pytest.raises(RateLimitExceeded):
        limiter.check("user")

    assert fake.expire_calls == [("rate:user", 60)]


def test_rate_limiter_factory_falls_back_to_memory():
    limiter = build_rate_limiter(enable_redis=True, redis_url="redis://127.0.0.1:1/0", limit=1)
    limiter.check("user")
    with pytest.raises(RateLimitExceeded):
        limiter.check("user")
