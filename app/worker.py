from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from sqlalchemy.orm import Session

from .config import load_settings
from .db import SessionLocal, init_db
from .harness_client import HarnessClient
from .run_queue import DBPollingQueueBackend, QueueBackend, build_run_queue
from .process_manager import ProcessRegistry
from .services import execute_run


SessionFactory = Callable[[], Session]


def process_next_run(
    session_factory: SessionFactory,
    harness_client: HarnessClient,
    harness_runs_root: Path,
    run_queue: QueueBackend | None = None,
) -> int | None:
    queue = run_queue or DBPollingQueueBackend()
    run_id = queue.dequeue(session_factory)
    if run_id is None:
        return None

    settings = load_settings()
    settings.harness_runs_root = Path(harness_runs_root).resolve()
    db = session_factory()
    try:
        executed = execute_run(db, run_id, harness_client, settings)
    finally:
        db.close()
    return run_id if executed else None


@dataclass
class Worker:
    session_factory: SessionFactory
    harness_client: HarnessClient
    harness_runs_root: Path
    run_queue: QueueBackend | None = None

    def run_once(self) -> bool:
        return process_next_run(self.session_factory, self.harness_client, self.harness_runs_root, self.run_queue) is not None

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
        executor=settings.harness_executor,
        docker_image=settings.harness_docker_image,
        container_harness_root=settings.harness_container_root,
        container_runs_root=settings.harness_container_runs_root,
        process_registry=ProcessRegistry(),
    )
    return Worker(
        session_factory=SessionLocal,
        harness_client=client,
        harness_runs_root=settings.harness_runs_root,
        run_queue=build_run_queue(settings),
    )


def main() -> None:
    build_default_worker().run_forever()


if __name__ == "__main__":
    main()
