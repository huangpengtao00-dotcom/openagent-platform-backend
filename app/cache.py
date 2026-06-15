from __future__ import annotations

import random
import threading
import time
import json
from dataclasses import dataclass
from typing import Any

import redis


@dataclass
class CacheEntry:
    value: Any
    expires_at: float
    negative: bool = False


class MemoryCache:
    def __init__(self, default_ttl: int, negative_ttl: int, jitter: int) -> None:
        self.default_ttl = default_ttl
        self.negative_ttl = negative_ttl
        self.jitter = jitter
        self._items: dict[str, CacheEntry] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def ttl_with_jitter(self, base_ttl: int | None = None) -> int:
        base = self.default_ttl if base_ttl is None else base_ttl
        return base + random.randint(0, max(0, self.jitter))

    def get(self, key: str) -> Any:
        entry = self._items.get(key)
        if not entry or entry.expires_at <= time.time():
            self._items.pop(key, None)
            return None
        return entry.value

    def set(self, key: str, value: Any, ttl: int | None = None, negative: bool = False) -> None:
        base_ttl = self.negative_ttl if negative else ttl
        self._items[key] = CacheEntry(value=value, expires_at=time.time() + self.ttl_with_jitter(base_ttl), negative=negative)

    def lock_for(self, key: str) -> threading.Lock:
        with self._guard:
            if key not in self._locks:
                self._locks[key] = threading.Lock()
            return self._locks[key]


class RedisCache:
    def __init__(self, client, default_ttl: int, negative_ttl: int, jitter: int) -> None:
        self.client = client
        self.default_ttl = default_ttl
        self.negative_ttl = negative_ttl
        self.jitter = jitter

    def ttl_with_jitter(self, base_ttl: int | None = None) -> int:
        base = self.default_ttl if base_ttl is None else base_ttl
        return base + random.randint(0, max(0, self.jitter))

    def get(self, key: str) -> Any:
        raw = self.client.get(key)
        if raw is None:
            return None
        return json.loads(raw)

    def set(self, key: str, value: Any, ttl: int | None = None, negative: bool = False) -> None:
        base_ttl = self.negative_ttl if negative else ttl
        self.client.setex(key, self.ttl_with_jitter(base_ttl), json.dumps(value))

    def lock_for(self, key: str):
        return self.client.lock(f"lock:{key}", timeout=10)


def build_cache(enable_redis: bool, redis_url: str, default_ttl: int, negative_ttl: int, jitter: int):
    if enable_redis:
        try:
            client = redis.Redis.from_url(redis_url, socket_connect_timeout=0.2, socket_timeout=0.2, decode_responses=True)
            client.ping()
            return RedisCache(client, default_ttl, negative_ttl, jitter)
        except redis.RedisError:
            pass
    return MemoryCache(default_ttl, negative_ttl, jitter)
