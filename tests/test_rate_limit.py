from __future__ import annotations

from datetime import datetime

import pytest

from app.rate_limit import MemoryRateLimiter, RateLimitExceeded


def test_rate_limiter_rejects_excess_requests():
    limiter = MemoryRateLimiter(limit=1)
    now = datetime(2026, 6, 15)
    limiter.check("user", now)
    with pytest.raises(RateLimitExceeded):
        limiter.check("user", now)

