from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from sqlalchemy.orm import Session

from .artifacts import ArtifactNotFound, UnsafeArtifactPath, read_json, resolve_artifact
from .cache import build_cache
from .config import load_settings
from .db import SessionLocal, get_db, init_db
from .harness_client import HarnessClient
from .models import Run, Task
from .process_manager import ProcessRegistry
from .rate_limit import RateLimitExceeded, build_rate_limiter
from .schemas import CostMetricsOut, RunCreate, RunOut, TaskCreate, TaskOut
from .services import artifact_links, cancel_run, cost_metrics, create_run, create_task, execute_run

settings = load_settings()
settings.harness_runs_root.mkdir(parents=True, exist_ok=True)
limiter = build_rate_limiter(settings.enable_redis, settings.redis_url, settings.rate_limit_runs_per_minute)
cache = build_cache(
    settings.enable_redis,
    settings.redis_url,
    settings.cache_default_ttl_seconds,
    settings.cache_negative_ttl_seconds,
    settings.cache_ttl_jitter_seconds,
)
process_registry = ProcessRegistry()
harness_client = HarnessClient(
    settings.harness_root,
    settings.harness_python,
    settings.harness_pythonpath,
    process_registry=process_registry,
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="OpenAgent Platform Backend", version="0.2.0", lifespan=lifespan)
app.state.session_factory = SessionLocal


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/tasks", response_model=TaskOut)
def post_task(body: TaskCreate, db: Session = Depends(get_db)) -> TaskOut:
    try:
        task = create_task(db, body, settings)
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return TaskOut(
        task_id=task.id,
        name=task.name,
        description=task.description,
        harness_task_path=task.harness_task_path,
        created_at=task.created_at,
    )


@app.post("/runs", response_model=RunOut)
def post_run(
    body: RunCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user_id: str = Header(default="anonymous", alias="X-User-ID"),
) -> RunOut:
    try:
        run = create_run(db, body, user_id, idempotency_key, settings, limiter)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    if run.status == "pending" and settings.auto_start_runs:
        _schedule_run(background_tasks, run.id)
    return _run_out(run)


@app.post("/runs/{run_id}/cancel", response_model=RunOut)
def post_cancel_run(run_id: int, db: Session = Depends(get_db)) -> RunOut:
    try:
        run = cancel_run(db, run_id, process_registry)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _run_out(run)


@app.get("/runs/{run_id}", response_model=RunOut)
def get_run(run_id: int, db: Session = Depends(get_db)) -> RunOut:
    cached = cache.get(f"run:{run_id}")
    if cached == "__missing__":
        raise HTTPException(status_code=404, detail="run not found")
    run = db.get(Run, run_id)
    if not run:
        cache.set(f"run:{run_id}", "__missing__", negative=True)
        raise HTTPException(status_code=404, detail="run not found")
    cache.set(f"run:{run_id}", run.status)
    return _run_out(run)


@app.get("/runs/{run_id}/report", response_class=HTMLResponse)
def get_report(run_id: int, db: Session = Depends(get_db)):
    return HTMLResponse(_artifact(run_id, db, "report.html").read_text(encoding="utf-8"))


@app.get("/runs/{run_id}/patch", response_class=PlainTextResponse)
def get_patch(run_id: int, db: Session = Depends(get_db)):
    return PlainTextResponse(_artifact(run_id, db, "patch.diff").read_text(encoding="utf-8"), media_type="text/plain")


@app.get("/runs/{run_id}/scorecard")
def get_scorecard(run_id: int, db: Session = Depends(get_db)):
    return JSONResponse(read_json(_artifact(run_id, db, "scorecard.json")))


@app.get("/runs/{run_id}/test-result")
def get_test_result(run_id: int, db: Session = Depends(get_db)):
    return JSONResponse(read_json(_artifact(run_id, db, "test_result.json")))


@app.get("/runs/{run_id}/trace", response_class=PlainTextResponse)
def get_trace(run_id: int, db: Session = Depends(get_db)):
    return PlainTextResponse(_artifact(run_id, db, "trace.jsonl").read_text(encoding="utf-8"), media_type="text/plain")


@app.get("/metrics/cost", response_model=CostMetricsOut)
def get_cost_metrics(
    db: Session = Depends(get_db),
    date_from: str | None = Query(default=None, alias="from"),
    date_to: str | None = Query(default=None, alias="to"),
) -> CostMetricsOut:
    return cost_metrics(db, _parse_date(date_from), _parse_date(date_to))


def _execute_run_in_new_session(run_id: int) -> None:
    db = app.state.session_factory()
    try:
        execute_run(db, run_id, harness_client, settings)
    finally:
        db.close()


def _schedule_run(background_tasks: BackgroundTasks, run_id: int) -> None:
    background_tasks.add_task(_execute_run_in_new_session, run_id)


def _run_out(run: Run) -> RunOut:
    usage = None
    if run.usage:
        usage = {
            "prompt_tokens": run.usage.prompt_tokens,
            "completion_tokens": run.usage.completion_tokens,
            "total_tokens": run.usage.total_tokens,
            "estimated_cost_usd": run.usage.estimated_cost_usd,
            "model": run.usage.model,
        }
    out = RunOut(
        run_id=run.id,
        task_id=run.task_id,
        status=run.status,
        mode=run.mode,
        model=run.model,
        timeout_seconds=run.timeout_seconds,
        harness_run_id=run.harness_run_id,
        artifacts_dir=run.artifacts_dir,
        failure_type=run.failure_type,
        error_message=run.error_message,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        usage=usage,
    )
    out.artifacts = artifact_links(run)
    return out


def _artifact(run_id: int, db: Session, filename: str) -> Path:
    run = db.get(Run, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    if not run.artifacts_dir:
        raise HTTPException(status_code=404, detail="artifact not found")
    try:
        return resolve_artifact(settings.harness_runs_root, run.artifacts_dir, filename)
    except ArtifactNotFound as exc:
        raise HTTPException(status_code=404, detail="artifact not found") from exc
    except UnsafeArtifactPath as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)
