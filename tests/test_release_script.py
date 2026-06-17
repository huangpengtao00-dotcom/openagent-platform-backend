from __future__ import annotations

from pathlib import Path


def test_clean_release_script_documents_two_release_profiles():
    script = Path("scripts/build_clean_release.ps1")

    assert script.exists()
    text = script.read_text(encoding="utf-8")
    assert "openagent-platform-runnable" in text
    assert "openagent-platform-interview-clean" in text
    for blocked in [".env", ".venv", "node_modules", "runs", "artifacts", ".git", "*.db", "*.sqlite"]:
        assert blocked in text
