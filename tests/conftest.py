from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_openagent_platform.db")
os.environ.setdefault("HARNESS_RUNS_ROOT", "./test_artifacts/harness_runs")
os.environ.setdefault("ALLOW_REAL_LLM_CALLS", "false")

from app.db import Base, get_db  # noqa: E402
from app.main import app, settings  # noqa: E402


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "platform.db"
    runs_root = tmp_path / "harness_runs"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(settings, "harness_runs_root", runs_root)
    monkeypatch.setattr(settings, "harness_root", tmp_path / "harness")
    runs_root.mkdir(parents=True, exist_ok=True)
    settings.harness_root.mkdir(parents=True, exist_ok=True)

    def override_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.state.session_factory = TestingSession
    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
