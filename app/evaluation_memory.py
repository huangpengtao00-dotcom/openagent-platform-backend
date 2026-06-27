from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from .artifacts import read_json, resolve_artifact
from .models import Run, Task


_MAX_SUMMARY_CHARS = 1200
_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]+|\d+|[\u4e00-\u9fff]+")


@dataclass(frozen=True)
class MemoryHit:
    record: dict[str, Any]
    score: int

    def to_dict(self) -> dict[str, Any]:
        payload = dict(self.record)
        payload["score"] = self.score
        return payload


class EvaluationMemoryStore:
    """Append-only JSONL memory for evaluation and retry evidence.

    The file format is intentionally simple so the storage layer can later be
    replaced by BM25, SQLite FTS, or vector search without changing callers.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path).resolve()

    def append_from_run(self, db: Session, run: Run, runs_root: Path) -> dict[str, Any] | None:
        task = db.get(Task, run.task_id)
        if not task or not run.artifacts_dir or run.status in {"pending", "running"}:
            return None

        task_spec = _artifact_json(runs_root, run, "task_spec.json")
        scorecard = _artifact_json(runs_root, run, "scorecard.json")
        test_result = _artifact_json(runs_root, run, "test_result.json")
        record = {
            "run_id": run.id,
            "source_run_id": run.source_run_id,
            "task_id": run.task_id,
            "workspace_id": task.workspace_id,
            "tenant_id": task.workspace.tenant_id if task.workspace else None,
            "workspace_slug": task.workspace.slug if task.workspace else None,
            "tenant_slug": task.workspace.tenant.slug if task.workspace and task.workspace.tenant else None,
            "task_name": task.name,
            "task_description": task.description,
            "harness_task_path": task.harness_task_path,
            "goal": _first_text(task_spec.get("goal"), task.description, task.name),
            "source_filename": _first_allowlist(task_spec),
            "status": run.status,
            "failure_type": run.failure_type or scorecard.get("failure_type") or ("None" if run.status == "pass" else "Unknown"),
            "test_error_fingerprint": _test_error_fingerprint(test_result),
            "patch_summary": _artifact_text(runs_root, run, "patch.diff"),
            "successful_fix_summary": _success_summary(run, scorecard, test_result),
            "harness_run_id": run.harness_run_id,
            "artifacts_dir": run.artifacts_dir,
            "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        self.append(record)
        return record

    def append(self, record: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    def list_recent(self, limit: int = 50, workspace_id: int | None = None) -> list[dict[str, Any]]:
        records = _filter_workspace(self._read_records(), workspace_id)
        return records[-max(1, limit) :][::-1]

    def summarize(self, recent_limit: int = 5, workspace_id: int | None = None) -> dict[str, Any]:
        records = _filter_workspace(self._read_records(), workspace_id)
        total = len(records)
        passed = sum(1 for record in records if record.get("status") == "pass")
        failed = sum(1 for record in records if record.get("status") in {"fail", "timeout", "cancelled"})
        retry_records = [record for record in records if record.get("source_run_id")]
        retry_successes = sum(1 for record in retry_records if record.get("status") == "pass")
        return {
            "total_records": total,
            "passed_records": passed,
            "failed_records": failed,
            "retry_records": len(retry_records),
            "retry_successes": retry_successes,
            "fail_to_pass_rate": retry_successes / len(retry_records) if retry_records else 0.0,
            "failure_types": _count_by(records, "failure_type"),
            "top_tasks": _top_tasks(records),
            "recent_items": records[-max(1, recent_limit) :][::-1],
        }

    def search_similar(
        self,
        *,
        goal: str,
        source_filename: str = "",
        failure_type: str | None = None,
        exclude_run_id: int | None = None,
        workspace_id: int | None = None,
        limit: int = 3,
    ) -> list[MemoryHit]:
        query_tokens = _tokens(" ".join([goal, source_filename, failure_type or ""]))
        hits: list[MemoryHit] = []
        for record in _filter_workspace(self._read_records(), workspace_id):
            if exclude_run_id is not None and int(record.get("run_id") or -1) == exclude_run_id:
                continue
            score = _score_record(record, query_tokens, source_filename, failure_type)
            if score > 0:
                hits.append(MemoryHit(record, score))
        return sorted(hits, key=lambda hit: (hit.score, int(hit.record.get("run_id") or 0)), reverse=True)[:limit]

    def _read_records(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        records: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                records.append(data)
        return records


def _score_record(record: dict[str, Any], query_tokens: set[str], source_filename: str, failure_type: str | None) -> int:
    haystack = " ".join(
        str(record.get(key) or "")
        for key in ["goal", "task_name", "task_description", "source_filename", "failure_type", "test_error_fingerprint"]
    )
    record_tokens = _tokens(haystack)
    score = len(query_tokens & record_tokens)
    if source_filename and record.get("source_filename") == source_filename:
        score += 8
    if failure_type and record.get("failure_type") == failure_type:
        score += 4
    if record.get("status") == "pass":
        score += 2
    return score


def _filter_workspace(records: list[dict[str, Any]], workspace_id: int | None) -> list[dict[str, Any]]:
    if workspace_id is None:
        return records
    return [record for record in records if record.get("workspace_id") == workspace_id]


def _count_by(records: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = str(record.get(key) or "Unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _top_tasks(records: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for record in records:
        name = str(record.get("task_name") or record.get("task_id") or "unknown")
        bucket = buckets.setdefault(name, {"task_name": name, "total": 0, "passed": 0, "failed": 0, "last_run_id": None})
        bucket["total"] += 1
        if record.get("status") == "pass":
            bucket["passed"] += 1
        elif record.get("status") in {"fail", "timeout", "cancelled"}:
            bucket["failed"] += 1
        bucket["last_run_id"] = record.get("run_id")
    return sorted(buckets.values(), key=lambda item: (-int(item["total"]), str(item["task_name"])))[:limit]


def _tokens(text: str) -> set[str]:
    return {token.lower() for token in _TOKEN_RE.findall(text) if len(token.strip()) > 1}


def _artifact_json(runs_root: Path, run: Run, filename: str) -> dict[str, Any]:
    try:
        return read_json(resolve_artifact(runs_root, run.artifacts_dir or "", filename))
    except Exception:
        return {}


def _artifact_text(runs_root: Path, run: Run, filename: str) -> str:
    try:
        text = resolve_artifact(runs_root, run.artifacts_dir or "", filename).read_text(encoding="utf-8")
    except Exception:
        return ""
    return _clip(text)


def _first_allowlist(task_spec: dict[str, Any]) -> str:
    allowlist = task_spec.get("allowlist")
    if isinstance(allowlist, list) and allowlist:
        return str(allowlist[0])
    return ""


def _test_error_fingerprint(test_result: dict[str, Any]) -> str:
    stderr = str(test_result.get("stderr") or "")
    stdout = str(test_result.get("stdout") or "")
    text = stderr or stdout
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    return _clip("\n".join(lines[-8:]), 800)


def _success_summary(run: Run, scorecard: dict[str, Any], test_result: dict[str, Any]) -> str:
    tests_passed = bool(scorecard.get("tests_passed") or test_result.get("tests_passed"))
    score = scorecard.get("score")
    if run.status == "pass":
        return f"Passed with score={score}; tests_passed={tests_passed}."
    return ""


def _first_text(*values: object) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _clip(text: str, max_chars: int = _MAX_SUMMARY_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 28] + "\n...<memory summary truncated>"
