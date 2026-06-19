from pathlib import Path

from app.config import _default_harness_root, load_settings


def test_default_harness_root_prefers_bundle_harness() -> None:
    root = _default_harness_root()

    assert root.name == "02_OpenAgent_Harness"
    assert (root / "src" / "openagent_harness" / "cli.py").exists()
    assert "OpenAgent-Harness-v1-final" not in str(root)


def test_default_real_api_budget_matches_interview_smoke_budget(monkeypatch) -> None:
    monkeypatch.delenv("REAL_API_BUDGET_LIMIT_CNY", raising=False)

    settings = load_settings()

    assert settings.real_api_budget_limit_cny == 1.0
