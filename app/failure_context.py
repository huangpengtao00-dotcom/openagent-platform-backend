from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from .artifacts import read_json, resolve_artifact
from .evaluation_memory import EvaluationMemoryStore
from .models import Run, Task


_MAX_TEXT_CHARS = 4000
_MAX_TRACE_LINES = 24


def build_failure_context(
    db: Session,
    run_id: int,
    runs_root: Path,
    memory_path: Path | None = None,
    workspace_id: int | None = None,
) -> dict[str, Any]:
    run = db.get(Run, run_id)
    if not run:
        raise LookupError("run not found")
    task = db.get(Task, run.task_id)
    if not task:
        raise LookupError("task not found")
    if not run.artifacts_dir:
        raise FileNotFoundError("run has no artifacts")

    artifacts = {
        "task_spec": _artifact_json(runs_root, run, "task_spec.json"),
        "scorecard": _artifact_json(runs_root, run, "scorecard.json"),
        "test_result": _compact_test_result(_artifact_json(runs_root, run, "test_result.json")),
        "patch_excerpt": _artifact_text(runs_root, run, "patch.diff"),
        "trace_excerpt": _trace_excerpt(runs_root, run),
        "report_excerpt": _report_excerpt(runs_root, run),
    }
    return {
        "source_run_id": run.id,
        "status": run.status,
        "failure_type": run.failure_type,
        "error_message": run.error_message,
        "harness_run_id": run.harness_run_id,
        "artifacts_dir": run.artifacts_dir,
        "task": {
            "id": task.id,
            "name": task.name,
            "description": task.description,
            "harness_task_path": task.harness_task_path,
        },
        "artifacts": artifacts,
        "memory_hints": _memory_hints(memory_path, run, artifacts, workspace_id=workspace_id),
        "retry_guidance": {
            "mode": "human_confirmed_retry",
            "rules": [
                "Use this evidence to avoid repeating the previous failure.",
                "Do not repeat the previous failed patch blindly.",
                "Keep the next patch inside the task allowlist.",
                "Run the original acceptance command before finishing.",
            ],
        },
    }


def write_failure_context(db: Session, run_id: int, runs_root: Path, memory_path: Path | None = None) -> Path:
    run = db.get(Run, run_id)
    if not run or not run.artifacts_dir:
        raise FileNotFoundError("run has no artifacts")
    workspace_id = run.task.workspace_id if run.task else None
    context = build_failure_context(db, run_id, runs_root, memory_path, workspace_id=workspace_id)
    run_dir = _safe_run_dir(runs_root, run.artifacts_dir)
    path = run_dir / "failure_context.json"
    path.write_text(json.dumps(context, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _safe_run_dir(runs_root: Path, artifacts_dir: str) -> Path:
    root = runs_root.resolve()
    run_dir = Path(artifacts_dir).resolve()
    if root != run_dir and root not in run_dir.parents:
        raise ValueError(f"artifact path escaped root: {run_dir}")
    return run_dir


def _artifact_json(runs_root: Path, run: Run, filename: str) -> dict[str, Any]:
    try:
        return read_json(resolve_artifact(runs_root, run.artifacts_dir or "", filename))
    except Exception:
        return {}


def _artifact_text(runs_root: Path, run: Run, filename: str, *, max_chars: int = _MAX_TEXT_CHARS) -> str:
    try:
        text = resolve_artifact(runs_root, run.artifacts_dir or "", filename).read_text(encoding="utf-8")
    except Exception:
        return ""
    return _clip(text, max_chars)


def _trace_excerpt(runs_root: Path, run: Run) -> str:
    text = _artifact_text(runs_root, run, "trace.jsonl", max_chars=20_000)
    lines = [line for line in text.splitlines() if line.strip()]
    return _clip("\n".join(lines[-_MAX_TRACE_LINES:]), _MAX_TEXT_CHARS)


def _report_excerpt(runs_root: Path, run: Run) -> str:
    html = _artifact_text(runs_root, run, "report.html", max_chars=12_000)
    if not html:
        return _artifact_text(runs_root, run, "final_report.md")
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()
    return _clip(text, _MAX_TEXT_CHARS)


def _compact_test_result(data: dict[str, Any]) -> dict[str, Any]:
    if not data:
        return {}
    compact = dict(data)
    if isinstance(compact.get("stdout"), str):
        compact["stdout"] = _clip(str(compact["stdout"]))
    if isinstance(compact.get("stderr"), str):
        compact["stderr"] = _clip(str(compact["stderr"]))
    results = compact.get("results")
    if isinstance(results, list):
        compact["results"] = results[-3:]
    return compact


def _memory_hints(memory_path: Path | None, run: Run, artifacts: dict[str, Any], workspace_id: int | None = None) -> list[dict[str, Any]]:
    if memory_path is None:
        return []
    task_spec = artifacts.get("task_spec") if isinstance(artifacts.get("task_spec"), dict) else {}
    allowlist = task_spec.get("allowlist")
    source_filename = str(allowlist[0]) if isinstance(allowlist, list) and allowlist else ""
    goal = str(task_spec.get("goal") or "")
    return [
        hit.to_dict()
        for hit in EvaluationMemoryStore(memory_path).search_similar(
            goal=goal,
            source_filename=source_filename,
            failure_type=run.failure_type,
            exclude_run_id=run.id,
            workspace_id=workspace_id,
            limit=3,
        )
    ]


def _clip(text: str, max_chars: int = _MAX_TEXT_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 32] + "\n...<truncated for retry context>"
