from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import load_settings
from .db import SessionLocal, init_db
from .harness_client import HarnessClient
from .process_manager import ProcessRegistry
from .models import Run, RunStatus
from .services import execute_run


SessionFactory = Callable[[], Session]


def process_next_run(session_factory: SessionFactory, harness_client: HarnessClient, harness_runs_root: Path) -> int | None:
    db = session_factory()
    try:
        run = db.execute(
            select(Run).where(Run.status == RunStatus.pending.value).order_by(Run.created_at, Run.id).limit(1)
        ).scalar_one_or_none()
        if not run:
            return None
        run_id = run.id
    finally:
        db.close()

    settings = load_settings()
    settings.harness_runs_root = Path(harness_runs_root).resolve()
    db = session_factory()
    try:
        execute_run(db, run_id, harness_client, settings)
    finally:
        db.close()
    return run_id


@dataclass
class Worker:
    session_factory: SessionFactory
    harness_client: HarnessClient
    harness_runs_root: Path

    def run_once(self) -> bool:
        return process_next_run(self.session_factory, self.harness_client, self.harness_runs_root) is not None

    def run_forever(self, poll_seconds: float = 2.0) -> None:
        while True:
            processed = self.run_once()
            if not processed:
                time.sleep(poll_seconds)


def build_default_worker() -> Worker:
    settings = load_settings()
    init_db()
    client = HarnessClient(
        settings.harness_root,
        settings.harness_python,
        settings.harness_pythonpath,
        process_registry=ProcessRegistry(),
    )
    return Worker(session_factory=SessionLocal, harness_client=client, harness_runs_root=settings.harness_runs_root)


def main() -> None:
    build_default_worker().run_forever()


if __name__ == "__main__":
    main()
