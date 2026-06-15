from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import Settings
from .harness_client import HarnessClient
from .models import Run, RunStatus, Task, Usage
from .rate_limit import MemoryRateLimiter
from .schemas import CostMetricsOut, CostModelOut, RunCreate, TaskCreate


def create_task(db: Session, body: TaskCreate) -> Task:
    task = Task(name=body.name, description=body.description, harness_task_path=body.harness_task_path)
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
    task = db.get(Task, run.task_id)
    if not task:
        return
    run.status = RunStatus.running.value
    run.started_at = datetime.utcnow()
    db.commit()
    try:
        result = client.run_task(
            task_spec_path=task.harness_task_path,
            mode=run.mode,
            model=run.model,
            runs_root=str(settings.harness_runs_root),
            allow_llm_calls=run.allow_llm_calls,
            timeout_seconds=run.timeout_seconds,
        )
        run.harness_run_id = result.harness_run_id
        run.artifacts_dir = str(result.artifacts_dir)
        run.status = RunStatus.passed.value if result.status == "pass" else RunStatus.failed.value
        run.failure_type = result.failure_type
        run.error_message = None if run.status == RunStatus.passed.value else result.failure_type
        upsert_usage(db, run, result.usage)
    except subprocess.TimeoutExpired as exc:
        run.status = RunStatus.timeout.value
        run.failure_type = "timeout"
        run.error_message = str(exc)
    except Exception as exc:
        run.status = RunStatus.failed.value
        run.failure_type = type(exc).__name__
        run.error_message = str(exc)
    finally:
        run.finished_at = datetime.utcnow()
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


def cancel_run(db: Session, run_id: int) -> Run:
    run = db.get(Run, run_id)
    if not run:
        raise LookupError("run not found")
    if run.status in {RunStatus.pending.value, RunStatus.running.value}:
        run.status = RunStatus.cancelled.value
        run.finished_at = datetime.utcnow()
        db.commit()
        db.refresh(run)
    return run
