from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import load_settings


class Base(DeclarativeBase):
    pass


settings = load_settings()
engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _ensure_sqlite_columns()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_sqlite_columns() -> None:
    if not settings.database_url.startswith("sqlite"):
        return
    inspector = inspect(engine)
    if "runs" not in inspector.get_table_names():
        return
    task_columns = {column["name"] for column in inspector.get_columns("tasks")}
    run_columns = {column["name"] for column in inspector.get_columns("runs")}
    pending_columns = {
        "timeout_seconds": "ALTER TABLE runs ADD COLUMN timeout_seconds INTEGER",
        "model_provider": "ALTER TABLE runs ADD COLUMN model_provider VARCHAR(80)",
        "base_url": "ALTER TABLE runs ADD COLUMN base_url TEXT",
        "wire_api": "ALTER TABLE runs ADD COLUMN wire_api VARCHAR(40)",
        "reasoning_effort": "ALTER TABLE runs ADD COLUMN reasoning_effort VARCHAR(40)",
        "disable_response_storage": "ALTER TABLE runs ADD COLUMN disable_response_storage BOOLEAN DEFAULT 0 NOT NULL",
        "source_run_id": "ALTER TABLE runs ADD COLUMN source_run_id INTEGER",
        "failure_context_path": "ALTER TABLE runs ADD COLUMN failure_context_path TEXT",
    }
    with engine.begin() as conn:
        if "evaluations" not in inspector.get_table_names():
            conn.execute(
                text(
                    """
                    CREATE TABLE evaluations (
                        id INTEGER NOT NULL PRIMARY KEY,
                        workspace_id INTEGER,
                        task_id INTEGER NOT NULL,
                        name VARCHAR(200) NOT NULL,
                        goal TEXT NOT NULL,
                        idempotency_key VARCHAR(200),
                        created_at DATETIME NOT NULL,
                        FOREIGN KEY(task_id) REFERENCES tasks (id),
                        FOREIGN KEY(workspace_id) REFERENCES workspaces (id),
                        CONSTRAINT uq_evaluations_workspace_idempotency UNIQUE (workspace_id, idempotency_key)
                    )
                    """
                )
            )
        if "workspace_id" not in task_columns:
            conn.execute(text("ALTER TABLE tasks ADD COLUMN workspace_id INTEGER"))
        for column, statement in pending_columns.items():
            if column not in run_columns:
                conn.execute(text(statement))
