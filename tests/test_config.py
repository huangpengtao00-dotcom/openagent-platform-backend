from pathlib import Path

from app.config import _default_harness_root_for_backend, load_settings


def test_default_harness_root_prefers_bundle_harness(tmp_path: Path) -> None:
    backend_root = tmp_path / "01_OpenAgent_Platform_Backend"
    harness_root = tmp_path / "02_OpenAgent_Harness"
    cli_path = harness_root / "src" / "openagent_harness" / "cli.py"
    backend_root.mkdir()
    cli_path.parent.mkdir(parents=True)
    cli_path.write_text("def main(): pass\n", encoding="utf-8")
    (harness_root / "pyproject.toml").write_text("[project]\nname = 'openagent-harness'\n", encoding="utf-8")

    root = _default_harness_root_for_backend(backend_root)

    assert root.name == "02_OpenAgent_Harness"
    assert (root / "src" / "openagent_harness" / "cli.py").exists()
    assert "OpenAgent-Harness-v1-final" not in str(root)


def test_default_harness_root_has_stable_standalone_fallback(tmp_path: Path) -> None:
    backend_root = tmp_path / "OpenAgent-Platform-Backend"
    backend_root.mkdir()

    root = _default_harness_root_for_backend(backend_root)

    assert root == (tmp_path / "02_OpenAgent_Harness").resolve()


def test_default_real_api_budget_matches_interview_smoke_budget(monkeypatch) -> None:
    monkeypatch.delenv("REAL_API_BUDGET_LIMIT_CNY", raising=False)

    settings = load_settings()

    assert settings.real_api_budget_limit_cny == 1.0


def test_run_queue_backend_defaults_to_database(monkeypatch) -> None:
    monkeypatch.delenv("QUEUE_BACKEND", raising=False)
    monkeypatch.delenv("RUN_QUEUE_BACKEND", raising=False)
    monkeypatch.delenv("RUN_QUEUE_KEY", raising=False)

    settings = load_settings()

    assert settings.run_queue_backend == "db"
    assert settings.run_queue_key == "openagent:runs"


def test_queue_backend_env_takes_precedence_over_legacy_run_queue_backend(monkeypatch) -> None:
    monkeypatch.setenv("QUEUE_BACKEND", "redis")
    monkeypatch.setenv("RUN_QUEUE_BACKEND", "database")
    monkeypatch.setenv("RUN_QUEUE_KEY", "openagent:test")

    settings = load_settings()

    assert settings.run_queue_backend == "redis"
    assert settings.run_queue_key == "openagent:test"


def test_legacy_database_queue_backend_alias_still_works(monkeypatch) -> None:
    monkeypatch.delenv("QUEUE_BACKEND", raising=False)
    monkeypatch.setenv("RUN_QUEUE_BACKEND", "database")

    settings = load_settings()

    assert settings.run_queue_backend == "db"


def test_harness_executor_defaults_to_local(monkeypatch) -> None:
    monkeypatch.delenv("HARNESS_EXECUTOR", raising=False)
    monkeypatch.delenv("HARNESS_DOCKER_IMAGE", raising=False)

    settings = load_settings()

    assert settings.harness_executor == "local"
    assert settings.harness_docker_image == "openagent-harness:latest"
