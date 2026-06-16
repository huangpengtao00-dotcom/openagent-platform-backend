from __future__ import annotations

import subprocess
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.harness_client import HarnessRunResult
from app.models import Run, RunStatus, Task
from app.services import execute_run
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


def test_worker_run_once_returns_false_when_no_pending_runs(tmp_path: Path):
    session_factory = make_session(tmp_path)
    fake = FakeHarnessClient(tmp_path / "artifacts" / "worker-run")
    worker = Worker(session_factory=session_factory, harness_client=fake, harness_runs_root=tmp_path / "artifacts")

    assert worker.run_once() is False


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
