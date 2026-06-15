from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ArtifactNotFound(FileNotFoundError):
    pass


class UnsafeArtifactPath(ValueError):
    pass


def resolve_artifact(root: Path, artifacts_dir: str | Path, filename: str) -> Path:
    root = root.resolve()
    base = Path(artifacts_dir).resolve()
    path = (base / filename).resolve()
    if root not in path.parents and path != root:
        raise UnsafeArtifactPath(f"artifact path escaped root: {path}")
    if not path.exists() or not path.is_file():
        raise ArtifactNotFound(filename)
    return path


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_usage_from_artifacts(run_dir: Path, fallback_model: str = "") -> dict[str, Any]:
    usage = _usage_from_trace(run_dir / "trace.jsonl") or _usage_from_api_agent(run_dir / "api_agent_run.json")
    if not usage:
        return {
            "model": fallback_model,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "estimated_cost_usd": 0.0,
        }
    return {
        "model": str(usage.get("model") or fallback_model),
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "completion_tokens": int(usage.get("completion_tokens") or 0),
        "total_tokens": int(usage.get("total_tokens") or 0),
        "estimated_cost_usd": float(usage.get("estimated_cost_usd") or 0.0),
    }


def _usage_from_trace(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    latest: dict[str, Any] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        observation = event.get("observation") or {}
        usage = observation.get("usage")
        if isinstance(usage, dict):
            latest = usage
    return latest


def _usage_from_api_agent(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    usage = data.get("total_usage") or data.get("usage")
    return usage if isinstance(usage, dict) else None

