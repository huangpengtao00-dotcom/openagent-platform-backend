from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Protocol

import redis


class RateLimitExceeded(Exception):
    pass


class RateLimiter(Protocol):
    def check(self, key: str, now: datetime | None = None) -> None:
        ...


class MemoryRateLimiter:
    def __init__(self, limit: int, window_seconds: int = 60) -> None:
        self.disabled = limit <= 0
        self.limit = max(1, limit)
        self.window = timedelta(seconds=window_seconds)
        self.buckets: dict[str, deque[datetime]] = defaultdict(deque)

    def check(self, key: str, now: datetime | None = None) -> None:
        if self.disabled:
            return
        now = now or datetime.utcnow()
        bucket = self.buckets[key]
        cutoff = now - self.window
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if len(bucket) >= self.limit:
            raise RateLimitExceeded("rate limit exceeded")
        bucket.append(now)


class RedisRateLimiter:
    def __init__(self, client, limit: int, window_seconds: int = 60) -> None:
        self.disabled = limit <= 0
        self.client = client
        self.limit = max(1, limit)
        self.window_seconds = window_seconds

    def check(self, key: str, now: datetime | None = None) -> None:
        _ = now
        if self.disabled:
            return
        redis_key = f"rate:{key}"
        count = int(self.client.incr(redis_key))
        if count == 1:
            self.client.expire(redis_key, self.window_seconds)
        if count > self.limit:
            raise RateLimitExceeded("rate limit exceeded")


def build_rate_limiter(enable_redis: bool, redis_url: str, limit: int) -> RateLimiter:
    if enable_redis:
        try:
            client = redis.Redis.from_url(redis_url, socket_connect_timeout=0.2, socket_timeout=0.2, decode_responses=True)
            client.ping()
            return RedisRateLimiter(client, limit)
        except redis.RedisError:
            pass
    return MemoryRateLimiter(limit)
