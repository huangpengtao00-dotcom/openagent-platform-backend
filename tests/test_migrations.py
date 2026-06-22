from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect


def _load_alembic():
    try:
        command = importlib.import_module("alembic.command")
        config_module = importlib.import_module("alembic.config")
    except ModuleNotFoundError as exc:
        if exc.name and exc.name.startswith("alembic"):
            pytest.skip(
                "Alembic is not installed in this environment; run `pip install -e .[dev]` to enable migration tests.",
                allow_module_level=True,
            )
        raise
    except ImportError as exc:
        alembic_pkg = importlib.import_module("alembic")
        if getattr(alembic_pkg, "__file__", None) is None and getattr(alembic_pkg, "__path__", None):
            pytest.skip(
                "Alembic dependency is missing and the local `alembic/` migration folder is shadowing the package; run `pip install -e .[dev]` to enable migration tests.",
                allow_module_level=True,
            )
        raise exc
    return command, config_module.Config


command, Config = _load_alembic()


def test_alembic_upgrade_head_creates_platform_schema(tmp_path: Path):
    db_path = tmp_path / "platform.db"
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")

    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{db_path}")
    inspector = inspect(engine)
    assert {"tasks", "runs", "usage"}.issubset(set(inspector.get_table_names()))
    run_columns = {column["name"] for column in inspector.get_columns("runs")}
    assert {
        "id",
        "task_id",
        "status",
        "mode",
        "model",
        "timeout_seconds",
        "artifacts_dir",
        "failure_type",
    }.issubset(run_columns)
