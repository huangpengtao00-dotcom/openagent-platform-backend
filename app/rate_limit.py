from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta


class RateLimitExceeded(Exception):
    pass


class MemoryRateLimiter:
    def __init__(self, limit: int, window_seconds: int = 60) -> None:
        self.limit = max(1, limit)
        self.window = timedelta(seconds=window_seconds)
        self.buckets: dict[str, deque[datetime]] = defaultdict(deque)

    def check(self, key: str, now: datetime | None = None) -> None:
        now = now or datetime.utcnow()
        bucket = self.buckets[key]
        cutoff = now - self.window
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if len(bucket) >= self.limit:
            raise RateLimitExceeded("rate limit exceeded")
        bucket.append(now)

