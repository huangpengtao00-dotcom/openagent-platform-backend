from __future__ import annotations

import subprocess
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.harness_client import HarnessRunResult
from app.models import Run, RunStatus, Task
from app.run_queue import DBPollingQueueBackend, RedisQueueBackend, RedisRunQueue
from app.services import cancel_run, execute_run
from app.worker import Worker, process_next_run


class FakeHarnessClient:
    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        self.calls = 0

    def run_task(self, **kwargs):
        self.calls += 1
        self.run_dir.mkdir(parents=True, exist_ok=True)
        return HarnessRunResult(
            harness_run_id="worker-run",
            artifacts_dir=self.run_dir,
            status="pass",
            failure_type=None,
            usage={"model": "scripted", "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "estimated_cost_usd": 0.0},
        )


def make_session(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'worker.db'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def seed_pending_run(session_factory):
    db = session_factory()
    task = Task(name="worker task", harness_task_path="task.json")
    db.add(task)
    db.commit()
    run = Run(task_id=task.id, status=RunStatus.pending.value, mode="local", model="scripted")
    db.add(run)
    db.commit()
    run_id = run.id
    db.close()
    return run_id


class FakeRedis:
    def __init__(self) -> None:
        self.values: list[str] = []

    def rpush(self, key: str, value: str) -> None:
        self.values.append(value)

    def blpop(self, key: str, timeout: int = 0):
        if not self.values:
            return None
        return (key, self.values.pop(0))

    def lpop(self, key: str):
        if not self.values:
            return None
        return self.values.pop(0)

    def llen(self, key: str) -> int:
        return len(self.values)


def test_process_next_run_executes_oldest_pending_run(tmp_path: Path, monkeypatch):
    session_factory = make_session(tmp_path)
    run_id = seed_pending_run(session_factory)
    fake = FakeHarnessClient(tmp_path / "artifacts" / "worker-run")

    processed = process_next_run(session_factory, fake, harness_runs_root=tmp_path / "artifacts")

    assert processed == run_id
    db = session_factory()
    run = db.get(Run, run_id)
    assert run.status == RunStatus.passed.value
    assert run.harness_run_id == "worker-run"
    assert run.usage.total_tokens == 0
    assert fake.calls == 1
    db.close()


def test_db_polling_queue_backend_keeps_legacy_pending_scan(tmp_path: Path):
    session_factory = make_session(tmp_path)
    run_id = seed_pending_run(session_factory)
    queue = DBPollingQueueBackend()

    queue.enqueue(run_id)

    assert queue.dequeue(session_factory) == run_id
    assert queue.depth() is None


def test_worker_run_once_returns_false_when_no_pending_runs(tmp_path: Path):
    session_factory = make_session(tmp_path)
    fake = FakeHarnessClient(tmp_path / "artifacts" / "worker-run")
    worker = Worker(session_factory=session_factory, harness_client=fake, harness_runs_root=tmp_path / "artifacts")

    assert worker.run_once() is False


def test_redis_run_queue_dequeues_pending_run_fifo(tmp_path: Path):
    session_factory = make_session(tmp_path)
    first = seed_pending_run(session_factory)
    second = seed_pending_run(session_factory)
    redis_client = FakeRedis()
    queue = RedisRunQueue(client=redis_client, key="test:runs")

    queue.enqueue(first)
    queue.enqueue(second)

    assert queue.dequeue(session_factory) == first
    assert queue.dequeue(session_factory) == second


def test_redis_queue_backend_enqueue_dequeue_and_depth(tmp_path: Path):
    session_factory = make_session(tmp_path)
    run_id = seed_pending_run(session_factory)
    redis_client = FakeRedis()
    queue = RedisQueueBackend(client=redis_client, key="test:runs")

    queue.enqueue(run_id)

    assert queue.depth() == 1
    assert queue.dequeue(session_factory) == run_id
    assert queue.depth() == 0


def test_redis_run_queue_skips_cancelled_or_completed_run_ids(tmp_path: Path):
    session_factory = make_session(tmp_path)
    cancelled = seed_pending_run(session_factory)
    pending = seed_pending_run(session_factory)
    db = session_factory()
    run = db.get(Run, cancelled)
    run.status = RunStatus.cancelled.value
    db.commit()
    db.close()
    redis_client = FakeRedis()
    queue = RedisRunQueue(client=redis_client, key="test:runs")

    queue.enqueue(cancelled)
    queue.enqueue("not-an-int")
    queue.enqueue(pending)

    assert queue.dequeue(session_factory) == pending


def test_duplicate_enqueue_does_not_execute_run_twice(tmp_path: Path):
    session_factory = make_session(tmp_path)
    run_id = seed_pending_run(session_factory)
    fake = FakeHarnessClient(tmp_path / "artifacts" / "worker-run")
    redis_client = FakeRedis()
    queue = RedisQueueBackend(client=redis_client, key="test:runs")
    queue.enqueue(run_id)
    queue.enqueue(run_id)

    first = process_next_run(session_factory, fake, harness_runs_root=tmp_path / "artifacts", run_queue=queue)
    second = process_next_run(session_factory, fake, harness_runs_root=tmp_path / "artifacts", run_queue=queue)

    assert first == run_id
    assert second is None
    assert fake.calls == 1


def test_cancelled_run_dequeued_by_worker_is_skipped(tmp_path: Path):
    session_factory = make_session(tmp_path)
    run_id = seed_pending_run(session_factory)
    db = session_factory()
    cancel_run(db, run_id)
    db.close()
    fake = FakeHarnessClient(tmp_path / "artifacts" / "should-not-run")
    redis_client = FakeRedis()
    queue = RedisQueueBackend(client=redis_client, key="test:runs")
    queue.enqueue(run_id)

    processed = process_next_run(session_factory, fake, harness_runs_root=tmp_path / "artifacts", run_queue=queue)

    assert processed is None
    assert fake.calls == 0


def test_execute_run_marks_subprocess_timeout_as_timeout(tmp_path: Path):
    session_factory = make_session(tmp_path)
    run_id = seed_pending_run(session_factory)

    class TimeoutHarnessClient:
        def run_task(self, **kwargs):
            raise subprocess.TimeoutExpired(cmd="openagent_harness", timeout=1)

    class Settings:
        harness_runs_root = tmp_path / "artifacts"

    db = session_factory()
    execute_run(db, run_id, TimeoutHarnessClient(), Settings())
    run = db.get(Run, run_id)

    assert run.status == RunStatus.timeout.value
    assert run.failure_type == "timeout"
    assert "timed out" in run.error_message
    db.close()


def test_cancel_running_run_terminates_registered_process(tmp_path: Path):
    session_factory = make_session(tmp_path)
    run_id = seed_pending_run(session_factory)
    db = session_factory()
    run = db.get(Run, run_id)
    run.status = RunStatus.running.value
    db.commit()

    class FakeProcessRegistry:
        def __init__(self) -> None:
            self.cancelled = []

        def cancel(self, run_id: int) -> bool:
            self.cancelled.append(run_id)
            return True

    registry = FakeProcessRegistry()
    cancelled = cancel_run(db, run_id, registry)

    assert cancelled.status == RunStatus.cancelled.value
    assert registry.cancelled == [run_id]
    db.close()


def test_execute_run_does_not_overwrite_cancelled_run_after_harness_returns(tmp_path: Path):
    session_factory = make_session(tmp_path)
    run_id = seed_pending_run(session_factory)

    class CancellingHarnessClient:
        def __init__(self, session_factory):
            self.session_factory = session_factory

        def run_task(self, **kwargs):
            db = self.session_factory()
            run = db.get(Run, run_id)
            run.status = RunStatus.cancelled.value
            db.commit()
            db.close()
            return HarnessRunResult(
                harness_run_id="late-success",
                artifacts_dir=tmp_path / "artifacts" / "late-success",
                status="pass",
                failure_type=None,
                usage={
                    "model": "scripted",
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "estimated_cost_usd": 0.0,
                },
            )

    class Settings:
        harness_runs_root = tmp_path / "artifacts"

    db = session_factory()
    execute_run(db, run_id, CancellingHarnessClient(session_factory), Settings())
    run = db.get(Run, run_id)

    assert run.status == RunStatus.cancelled.value
    assert run.harness_run_id is None
    assert run.finished_at is not None
    db.close()


def test_process_next_run_marks_missing_task_as_failed(tmp_path: Path):
    session_factory = make_session(tmp_path)
    db = session_factory()
    run = Run(task_id=999, status=RunStatus.pending.value, mode="local", model="scripted")
    db.add(run)
    db.commit()
    run_id = run.id
    db.close()

    fake = FakeHarnessClient(tmp_path / "artifacts" / "worker-run")
    processed = process_next_run(session_factory, fake, harness_runs_root=tmp_path / "artifacts")

    assert processed == run_id
    db = session_factory()
    run = db.get(Run, run_id)
    assert run.status == RunStatus.failed.value
    assert run.failure_type == "task_not_found"
    assert run.finished_at is not None
    assert fake.calls == 0
    db.close()


def test_execute_run_normalizes_string_none_failure_type(tmp_path: Path):
    session_factory = make_session(tmp_path)
    run_id = seed_pending_run(session_factory)

    class NoneStringHarnessClient:
        def run_task(self, **kwargs):
            return HarnessRunResult(
                harness_run_id="none-string-run",
                artifacts_dir=tmp_path / "artifacts" / "none-string-run",
                status="fail",
                failure_type="None",
                usage={
                    "model": "scripted",
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "estimated_cost_usd": 0.0,
                },
            )

    class Settings:
        harness_runs_root = tmp_path / "artifacts"

    db = session_factory()
    execute_run(db, run_id, NoneStringHarnessClient(), Settings())
    run = db.get(Run, run_id)

    assert run.status == RunStatus.failed.value
    assert run.failure_type is None
    assert run.error_message == "harness failed"
    db.close()


def test_execute_run_ignores_non_pending_run(tmp_path: Path):
    session_factory = make_session(tmp_path)
    run_id = seed_pending_run(session_factory)
    db = session_factory()
    run = db.get(Run, run_id)
    run.status = RunStatus.passed.value
    run.harness_run_id = "already-done"
    db.commit()

    fake = FakeHarnessClient(tmp_path / "artifacts" / "should-not-run")

    class Settings:
        harness_runs_root = tmp_path / "artifacts"

    execute_run(db, run_id, fake, Settings())
    db.refresh(run)

    assert fake.calls == 0
    assert run.status == RunStatus.passed.value
    assert run.harness_run_id == "already-done"
    db.close()
