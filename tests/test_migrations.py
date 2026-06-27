from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_alembic_upgrade_head_creates_platform_schema(tmp_path: Path):
    db_path = tmp_path / "platform.db"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")

    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)
    assert {"tenants", "workspaces", "tasks", "runs", "usage"}.issubset(set(inspector.get_table_names()))
    task_columns = {column["name"] for column in inspector.get_columns("tasks")}
    assert "workspace_id" in task_columns
    run_columns = {column["name"] for column in inspector.get_columns("runs")}
    assert {
        "id",
        "task_id",
        "status",
        "mode",
        "model",
        "model_provider",
        "base_url",
        "wire_api",
        "reasoning_effort",
        "disable_response_storage",
        "timeout_seconds",
        "source_run_id",
        "failure_context_path",
        "artifacts_dir",
        "failure_type",
    }.issubset(run_columns)
