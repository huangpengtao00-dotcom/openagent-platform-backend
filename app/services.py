from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import Settings
from .harness_client import HarnessClient
from .models import Run, RunStatus, Task, Usage
from .rate_limit import MemoryRateLimiter
from .schemas import CostMetricsOut, CostModelOut, RunCreate, TaskCreate
from .time import utc_now


class ProcessCanceller(Protocol):
    def cancel(self, run_id: int) -> bool:
        ...


def create_task(db: Session, body: TaskCreate, settings: Settings) -> Task:
    task_spec_path = _resolve_harness_task_path(body.harness_task_path, settings.harness_root)
    task = Task(name=body.name, description=body.description, harness_task_path=str(task_spec_path))
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def create_run(
    db: Session,
    body: RunCreate,
    user_id: str,
    idempotency_key: str | None,
    settings: Settings,
    limiter: MemoryRateLimiter,
) -> Run:
    task = db.get(Task, body.task_id)
    if not task:
        raise LookupError("task not found")
    if idempotency_key:
        existing = db.execute(
            select(Run).where(Run.user_id == user_id, Run.idempotency_key == idempotency_key)
        ).scalar_one_or_none()
        if existing:
            return existing
    if body.mode == "api" and body.allow_llm_calls and not settings.allow_real_llm_calls:
        raise PermissionError("real LLM calls are disabled by ALLOW_REAL_LLM_CALLS")
    limiter.check(f"runs:{user_id}")
    run = Run(
        task_id=task.id,
        user_id=user_id,
        idempotency_key=idempotency_key,
        status=RunStatus.pending.value,
        mode=body.mode,
        model=body.model or settings.harness_default_model,
        allow_llm_calls=body.allow_llm_calls,
        timeout_seconds=body.timeout_seconds,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def execute_run(db: Session, run_id: int, client: HarnessClient, settings: Settings) -> None:
    run = db.get(Run, run_id)
    if not run:
        return
    if run.status == RunStatus.cancelled.value:
        return
    task = db.get(Task, run.task_id)
    if not task:
        run.status = RunStatus.failed.value
        run.failure_type = "task_not_found"
        run.error_message = "task not found"
        run.finished_at = utc_now()
        db.commit()
        return
    run.status = RunStatus.running.value
    run.started_at = utc_now()
    db.commit()
    try:
        result = client.run_task(
            task_spec_path=task.harness_task_path,
            mode=run.mode,
            model=run.model,
            runs_root=str(settings.harness_runs_root),
            allow_llm_calls=run.allow_llm_calls,
            timeout_seconds=run.timeout_seconds,
            run_id=run.id,
            should_cancel=lambda: _run_is_cancelled(db, run),
        )
        db.refresh(run)
        if run.status == RunStatus.cancelled.value:
            return
        run.harness_run_id = result.harness_run_id
        run.artifacts_dir = str(result.artifacts_dir)
        run.status = RunStatus.passed.value if result.status == "pass" else RunStatus.failed.value
        failure_type = _normalize_failure_type(result.failure_type)
        run.failure_type = failure_type
        run.error_message = None if run.status == RunStatus.passed.value else (failure_type or "harness failed")
        upsert_usage(db, run, result.usage)
    except subprocess.TimeoutExpired as exc:
        db.refresh(run)
        if run.status == RunStatus.cancelled.value:
            return
        run.status = RunStatus.timeout.value
        run.failure_type = "timeout"
        run.error_message = str(exc)
    except Exception as exc:
        db.refresh(run)
        if run.status == RunStatus.cancelled.value:
            return
        run.status = RunStatus.failed.value
        run.failure_type = type(exc).__name__
        run.error_message = str(exc)
    finally:
        if run.status == RunStatus.cancelled.value:
            if run.finished_at is None:
                run.finished_at = utc_now()
                db.commit()
        else:
            run.finished_at = utc_now()
            db.commit()


def upsert_usage(db: Session, run: Run, data: dict) -> Usage:
    usage = run.usage or Usage(run_id=run.id)
    usage.model = str(data.get("model") or run.model)
    usage.prompt_tokens = int(data.get("prompt_tokens") or 0)
    usage.completion_tokens = int(data.get("completion_tokens") or 0)
    usage.total_tokens = int(data.get("total_tokens") or 0)
    usage.estimated_cost_usd = float(data.get("estimated_cost_usd") or 0.0)
    db.add(usage)
    return usage


def _resolve_harness_task_path(task_path: str, harness_root: Path) -> Path:
    root = Path(harness_root).resolve()
    candidate = Path(task_path)
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.resolve()
    if candidate != root and root not in candidate.parents:
        raise PermissionError(f"harness_task_path must stay inside allowed harness root: {root}")
    return candidate


def _normalize_failure_type(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"none", "null", "nil"}:
        return None
    return text


def _run_is_cancelled(db: Session, run: Run) -> bool:
    db.refresh(run)
    return run.status == RunStatus.cancelled.value


def cost_metrics(db: Session, date_from: datetime | None = None, date_to: datetime | None = None) -> CostMetricsOut:
    query = select(Usage.model, func.count(Usage.id), func.sum(Usage.total_tokens), func.sum(Usage.estimated_cost_usd)).join(Run)
    if date_from:
        query = query.where(Run.created_at >= date_from)
    if date_to:
        query = query.where(Run.created_at <= date_to)
    query = query.group_by(Usage.model)
    rows = db.execute(query).all()
    by_model = [
        CostModelOut(model=row[0], runs=row[1], tokens=int(row[2] or 0), estimated_cost_usd=float(row[3] or 0.0))
        for row in rows
    ]
    return CostMetricsOut(
        total_runs=sum(item.runs for item in by_model),
        total_tokens=sum(item.tokens for item in by_model),
        estimated_cost_usd=sum(item.estimated_cost_usd for item in by_model),
        by_model=by_model,
    )


def artifact_links(run: Run) -> dict[str, str]:
    if not run.artifacts_dir:
        return {}
    base = f"/runs/{run.id}"
    return {
        "report": f"{base}/report",
        "patch": f"{base}/patch",
        "scorecard": f"{base}/scorecard",
        "test_result": f"{base}/test-result",
        "trace": f"{base}/trace",
    }


def cancel_run(db: Session, run_id: int, process_canceller: ProcessCanceller | None = None) -> Run:
    run = db.get(Run, run_id)
    if not run:
        raise LookupError("run not found")
    if run.status in {RunStatus.pending.value, RunStatus.running.value}:
        if process_canceller is not None:
            process_canceller.cancel(run_id)
        run.status = RunStatus.cancelled.value
        run.finished_at = utc_now()
        db.commit()
        db.refresh(run)
    return run
