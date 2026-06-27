from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

import redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .models import Run, RunStatus


SessionFactory = Callable[[], Session]


class QueueBackend(Protocol):
    name: str

    def enqueue(self, run_id: int) -> None:
        ...

    def dequeue(self, session_factory: SessionFactory) -> int | None:
        ...

    def depth(self) -> int | None:
        ...


@dataclass
class DBPollingQueueBackend:
    name: str = "db"

    def enqueue(self, run_id: int) -> None:
        # The database row is already the queue item for the polling backend.
        return None

    def dequeue(self, session_factory: SessionFactory) -> int | None:
        db = session_factory()
        try:
            run = db.execute(
                select(Run).where(Run.status == RunStatus.pending.value).order_by(Run.created_at, Run.id).limit(1)
            ).scalar_one_or_none()
            return run.id if run else None
        finally:
            db.close()

    def depth(self) -> int | None:
        return None


@dataclass
class RedisQueueBackend:
    client: redis.Redis
    key: str
    fallback: QueueBackend | None = None
    pop_timeout_seconds: int = 1
    name: str = "redis"

    def enqueue(self, run_id: int) -> None:
        try:
            self.client.rpush(self.key, str(run_id))
        except redis.RedisError:
            if self.fallback is not None:
                self.fallback.enqueue(run_id)
                return
            raise

    def dequeue(self, session_factory: SessionFactory) -> int | None:
        while True:
            try:
                raw = self._pop_raw()
            except redis.RedisError:
                return self.fallback.dequeue(session_factory) if self.fallback is not None else None
            if raw is None:
                return self.fallback.dequeue(session_factory) if self.fallback is not None else None
            try:
                run_id = int(raw)
            except (TypeError, ValueError):
                continue
            if _is_pending(session_factory, run_id):
                return run_id

    def depth(self) -> int | None:
        try:
            return int(self.client.llen(self.key))
        except redis.RedisError:
            return None

    def ping(self) -> bool:
        try:
            return bool(self.client.ping())
        except redis.RedisError:
            return False

    def _pop_raw(self):
        if hasattr(self.client, "blpop"):
            popped = self.client.blpop(self.key, timeout=self.pop_timeout_seconds)
            if popped is None:
                return None
            if isinstance(popped, tuple) and len(popped) == 2:
                return popped[1]
            return popped
        return self.client.lpop(self.key)


RunQueue = QueueBackend
DatabaseRunQueue = DBPollingQueueBackend
RedisRunQueue = RedisQueueBackend


def build_run_queue(settings: Settings) -> QueueBackend:
    fallback = DBPollingQueueBackend()
    if settings.run_queue_backend == "redis" or (settings.enable_redis and settings.run_queue_backend == "auto"):
        try:
            client = redis.Redis.from_url(
                settings.redis_url,
                socket_connect_timeout=0.2,
                socket_timeout=0.2,
                decode_responses=True,
            )
            client.ping()
            return RedisQueueBackend(client=client, key=settings.run_queue_key, fallback=fallback)
        except redis.RedisError:
            return fallback
    return fallback


def _is_pending(session_factory: SessionFactory, run_id: int) -> bool:
    db = session_factory()
    try:
        run = db.get(Run, run_id)
        return bool(run and run.status == RunStatus.pending.value)
    finally:
        db.close()
