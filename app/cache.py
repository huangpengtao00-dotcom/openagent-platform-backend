from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass
from typing import Any


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

