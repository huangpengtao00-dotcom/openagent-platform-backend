from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .artifacts import read_json, resolve_artifact
from .models import Run, Task


def build_evaluation_summary(db: Session, runs_root: Path) -> dict[str, Any]:
    runs = db.execute(select(Run).join(Task).order_by(Run.created_at, Run.id)).scalars().all()
    attempt_counts: dict[tuple[int, str, str], int] = defaultdict(int)
    rows: list[dict[str, Any]] = []

    for run in runs:
        task = db.get(Task, run.task_id)
        key = (run.task_id, run.mode, run.model)
        attempt_counts[key] += 1
        attempt_index = attempt_counts[key]
        scorecard = _artifact_json(runs_root, run, "scorecard.json")
        test_result = _artifact_json(runs_root, run, "test_result.json")
        patch_stats = _patch_stats(runs_root, run)
        duration_seconds = _duration_seconds(run.started_at, run.finished_at)
        usage = run.usage
        failure_type = "None" if run.status == "pass" else _first_text(run.failure_type, scorecard.get("failure_type"))
        row = {
            "run_id": run.id,
            "task_id": task.name if task else str(run.task_id),
            "harness_run_id": run.harness_run_id,
            "profile": _profile_label(run, attempt_index),
            "attempt_index": attempt_index,
            "status": run.status,
            "score": int(scorecard.get("score") or (100 if run.status == "pass" else 0)),
            "patch_lines": int(scorecard.get("patch_lines") or patch_stats["patch_lines"]),
            "changed_files": int(scorecard.get("changed_files") or patch_stats["changed_files"]),
            "tests_passed": bool(scorecard.get("tests_passed") or test_result.get("tests_passed") or False),
            "failure_type": failure_type or "Unknown",
            "tokens": int(usage.total_tokens if usage else 0),
            "estimated_cost_usd": float(usage.estimated_cost_usd if usage else 0.0),
            "duration_seconds": duration_seconds,
            "report_link": f"/runs/{run.id}/report" if run.artifacts_dir else None,
        }
        rows.append(row)

    completed_rows = [row for row in rows if row["status"] in {"pass", "fail", "timeout", "cancelled"}]
    total = len(rows)
    passed = sum(1 for row in rows if row["status"] == "pass")
    failed = sum(1 for row in rows if row["status"] in {"fail", "timeout", "cancelled"})
    avg_score = round(sum(row["score"] for row in completed_rows) / len(completed_rows), 2) if completed_rows else 0.0
    summary = {
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": round(passed / total, 4) if total else 0.0,
        "avg_score": avg_score,
        "total_patch_lines": sum(row["patch_lines"] for row in rows),
        "total_changed_files": sum(row["changed_files"] for row in rows),
        "tests_passed": sum(1 for row in rows if row["tests_passed"]),
        "failure_types": dict(Counter(row["failure_type"] for row in rows)),
        "tokens": sum(row["tokens"] for row in rows),
        "total_cost_usd": round(sum(row["estimated_cost_usd"] for row in rows), 8),
        "duration_seconds": round(sum(row["duration_seconds"] or 0 for row in rows), 3),
    }
    return {
        "summary": summary,
        "profiles": _profile_summaries(rows),
        "tasks": rows,
        "retry_comparisons": _retry_comparisons(rows),
    }


def _profile_label(run: Run, attempt_index: int) -> str:
    if run.mode == "local":
        return "scripted baseline"
    if attempt_index > 1:
        return "retry with context"
    return "DeepSeek API"


def _profile_summaries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["profile"]].append(row)
    order = {"scripted baseline": 0, "DeepSeek API": 1, "retry with context": 2}
    profiles = []
    for profile, items in sorted(grouped.items(), key=lambda item: order.get(item[0], 99)):
        passed = sum(1 for row in items if row["status"] == "pass")
        profiles.append(
            {
                "profile": profile,
                "total": len(items),
                "passed": passed,
                "failed": sum(1 for row in items if row["status"] in {"fail", "timeout", "cancelled"}),
                "pass_rate": round(passed / len(items), 4) if items else 0.0,
                "avg_score": round(sum(row["score"] for row in items) / len(items), 2) if items else 0.0,
                "patch_lines": sum(row["patch_lines"] for row in items),
                "changed_files": sum(row["changed_files"] for row in items),
                "tokens": sum(row["tokens"] for row in items),
                "estimated_cost_usd": round(sum(row["estimated_cost_usd"] for row in items), 8),
                "duration_seconds": round(sum(row["duration_seconds"] or 0 for row in items), 3),
            }
        )
    return profiles


def _retry_comparisons(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["profile"] in {"DeepSeek API", "retry with context"}:
            grouped[(row["task_id"], row["profile"] if row["profile"] == "DeepSeek API" else "DeepSeek API")].append(row)

    comparisons: list[dict[str, Any]] = []
    for (task_id, _profile), items in grouped.items():
        ordered = sorted(items, key=lambda row: row["attempt_index"])
        if len(ordered) < 2:
            continue
        first, retry = ordered[0], ordered[-1]
        comparisons.append(
            {
                "task_id": task_id,
                "first_attempt_status": first["status"],
                "retry_status": retry["status"],
                "fail_to_pass": first["status"] != "pass" and retry["status"] == "pass",
                "retry_cost": retry["estimated_cost_usd"],
                "retry_patch_lines": retry["patch_lines"],
                "failure_type_changed": first["failure_type"] != retry["failure_type"],
                "first_failure_type": first["failure_type"],
                "retry_failure_type": retry["failure_type"],
            }
        )
    return comparisons


def _artifact_json(runs_root: Path, run: Run, filename: str) -> dict[str, Any]:
    if not run.artifacts_dir:
        return {}
    try:
        return read_json(resolve_artifact(runs_root, run.artifacts_dir, filename))
    except Exception:
        return {}


def _patch_stats(runs_root: Path, run: Run) -> dict[str, int]:
    if not run.artifacts_dir:
        return {"patch_lines": 0, "changed_files": 0}
    try:
        path = resolve_artifact(runs_root, run.artifacts_dir, "patch.diff")
        patch = path.read_text(encoding="utf-8")
    except Exception:
        return {"patch_lines": 0, "changed_files": 0}
    return {
        "patch_lines": sum(1 for line in patch.splitlines() if line.startswith("+") or line.startswith("-")),
        "changed_files": sum(1 for line in patch.splitlines() if line.startswith("diff --git")),
    }


def _duration_seconds(started_at: datetime | None, finished_at: datetime | None) -> float | None:
    if not started_at or not finished_at:
        return None
    return round(max(0.0, (finished_at - started_at).total_seconds()), 3)


def _first_text(*values: object) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text and text.lower() not in {"none", "null", "nil"}:
            return text
    return None
