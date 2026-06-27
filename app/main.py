from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .artifacts import ArtifactNotFound, UnsafeArtifactPath, read_json, resolve_artifact
from .cache import build_cache
from .config import load_settings
from .db import SessionLocal, get_db, init_db
from .evaluation import build_evaluation_summary
from .evaluation_memory import EvaluationMemoryStore
from .failure_context import build_failure_context
from .harness_client import HarnessClient
from .models import Run, Task
from .process_manager import ProcessRegistry
from .rate_limit import RateLimitExceeded, build_rate_limiter
from .run_queue import build_run_queue
from .schemas import (
    CostMetricsOut,
    CustomTaskCreate,
    EvaluationCreate,
    EvaluationCreateOut,
    EvaluationDraftCreate,
    EvaluationDraftOut,
    EvaluationHistoryItemOut,
    EvaluationMatrixOut,
    DemoIdStateOut,
    DemoStateOut,
    EvaluationSummaryOut,
    EvaluationMemoryListOut,
    EvaluationMemorySummaryOut,
    FailureContextOut,
    RetryRunCreate,
    RunCatalogItemOut,
    RunCreate,
    RunOut,
    RunSourceOut,
    RuntimeStatusOut,
    SourceFileOut,
    TaskCreate,
    TaskOut,
)
from .services import (
    IdempotencyConflict,
    artifact_links,
    build_evaluation_draft,
    cancel_run,
    cost_metrics,
    create_custom_task,
    create_evaluation_runs,
    create_run,
    create_task,
    delete_evaluation_task,
    execute_run,
    get_evaluation_matrix,
    get_or_create_workspace,
    list_evaluation_history,
    retry_run,
)

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
run_queue = build_run_queue(settings)
harness_client = HarnessClient(
    settings.harness_root,
    settings.harness_python,
    settings.harness_pythonpath,
    executor=settings.harness_executor,
    docker_image=settings.harness_docker_image,
    container_harness_root=settings.harness_container_root,
    container_runs_root=settings.harness_container_runs_root,
    process_registry=process_registry,
)

_SOURCE_ALLOWED_SUFFIXES = {".py", ".md", ".json", ".txt", ".toml", ".yaml", ".yml"}
_SOURCE_IGNORED_DIR_NAMES = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
    ".venv",
    "runs",
    "runs_deepseek",
    "runs_deepseek_real",
    "artifacts",
}
_SOURCE_IGNORED_FILE_NAMES = {
    ".env",
    ".env.local",
    ".env.development",
    ".env.test",
    ".env.production",
}
_SOURCE_SENSITIVE_NAME_FRAGMENTS = {"secret", "token", "password", "credential", "api_key", "apikey"}
_SOURCE_MAX_FILES = 80
_SOURCE_MAX_FILE_BYTES = 64_000
_SOURCE_MAX_TOTAL_BYTES = 512_000
_REPORT_SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
}

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="OpenAgent Platform Backend", version="0.2.0", lifespan=lifespan)
app.state.session_factory = SessionLocal


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/demo/status", response_model=RuntimeStatusOut)
def demo_status() -> RuntimeStatusOut:
    redis_available = bool(getattr(run_queue, "ping", lambda: False)())
    return RuntimeStatusOut(
        status="ok",
        app_env=settings.app_env,
        database=settings.database_url,
        harness_root=str(settings.harness_root),
        harness_exists=(settings.harness_root / "src" / "openagent_harness" / "cli.py").exists(),
        harness_runs_root=str(settings.harness_runs_root),
        harness_executor=settings.harness_executor,
        harness_docker_image=settings.harness_docker_image,
        allow_real_llm_calls=settings.allow_real_llm_calls,
        real_api_budget_limit_cny=settings.real_api_budget_limit_cny,
        auto_start_runs=settings.auto_start_runs,
        queue_backend_configured=settings.run_queue_backend,
        queue_backend_active=run_queue.name,
        queue_key=settings.run_queue_key,
        queue_depth=run_queue.depth(),
        redis_enabled=settings.enable_redis,
        redis_url=_redact_url(settings.redis_url),
        redis_available=redis_available,
    )



@app.get("/demo/state", response_model=DemoStateOut)
def demo_state(
    db: Session = Depends(get_db),
    tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
    workspace_id: str = Header(default="default", alias="X-Workspace-ID"),
) -> DemoStateOut:
    workspace = get_or_create_workspace(db, tenant_id, workspace_id)
    task_ids = db.execute(select(Task.id).where(Task.workspace_id == workspace.id).order_by(Task.id).limit(200)).scalars().all()
    run_ids = db.execute(select(Run.id).join(Task).where(Task.workspace_id == workspace.id).order_by(Run.id).limit(200)).scalars().all()
    latest_runs = db.execute(
        select(Run).join(Task).where(Task.workspace_id == workspace.id).order_by(Run.created_at.desc(), Run.id.desc()).limit(8)
    ).scalars().all()
    return DemoStateOut(
        status="ok",
        database=settings.database_url,
        generated_at=datetime.now(timezone.utc),
        tasks=_id_state(task_ids),
        runs=_id_state(run_ids),
        latest_runs=[_run_catalog_item(run) for run in latest_runs],
    )

@app.post("/tasks", response_model=TaskOut)
def post_task(
    body: TaskCreate,
    db: Session = Depends(get_db),
    tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
    workspace_id: str = Header(default="default", alias="X-Workspace-ID"),
) -> TaskOut:
    try:
        workspace = get_or_create_workspace(db, tenant_id, workspace_id)
        task = create_task(db, body, settings, workspace_id=workspace.id)
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return TaskOut(
        task_id=task.id,
        workspace_id=task.workspace_id,
        name=task.name,
        description=task.description,
        harness_task_path=task.harness_task_path,
        created_at=task.created_at,
    )


@app.post("/custom-tasks", response_model=TaskOut)
def post_custom_task(
    body: CustomTaskCreate,
    db: Session = Depends(get_db),
    tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
    workspace_id: str = Header(default="default", alias="X-Workspace-ID"),
) -> TaskOut:
    try:
        workspace = get_or_create_workspace(db, tenant_id, workspace_id)
        task = create_custom_task(db, body, settings, workspace_id=workspace.id)
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return TaskOut(
        task_id=task.id,
        workspace_id=task.workspace_id,
        name=task.name,
        description=task.description,
        harness_task_path=task.harness_task_path,
        created_at=task.created_at,
    )


@app.post("/evaluation-drafts", response_model=EvaluationDraftOut)
def post_evaluation_draft(body: EvaluationDraftCreate) -> EvaluationDraftOut:
    try:
        return build_evaluation_draft(body)
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/evaluations", response_model=EvaluationCreateOut)
def post_evaluation(
    body: EvaluationCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user_id: str = Header(default="anonymous", alias="X-User-ID"),
    tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
    workspace_id: str = Header(default="default", alias="X-Workspace-ID"),
) -> EvaluationCreateOut:
    try:
        workspace = get_or_create_workspace(db, tenant_id, workspace_id)
        evaluation, task, runs, created = create_evaluation_runs(
            db,
            body,
            user_id,
            settings,
            limiter,
            workspace_id=workspace.id,
            idempotency_key=idempotency_key,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    if created:
        for run in runs:
            _dispatch_run(background_tasks, run.id, run.status)
    return EvaluationCreateOut(
        evaluation_id=evaluation.id,
        task=TaskOut(
            task_id=task.id,
            workspace_id=task.workspace_id,
            name=task.name,
            description=task.description,
            harness_task_path=task.harness_task_path,
            created_at=task.created_at,
        ),
        runs=[_run_out(run) for run in runs],
        next_steps=[
            "Open the run list to watch each model profile move from pending to pass/fail.",
            "Use /evaluation/summary after runs finish to compare pass rate, cost, patch size, and failure type.",
        ],
    )


@app.post("/runs", response_model=RunOut)
def post_run(
    body: RunCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user_id: str = Header(default="anonymous", alias="X-User-ID"),
    tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
    workspace_id: str = Header(default="default", alias="X-Workspace-ID"),
) -> RunOut:
    try:
        workspace = get_or_create_workspace(db, tenant_id, workspace_id)
        _ensure_task_in_workspace(db, body.task_id, workspace.id)
        run = create_run(db, body, user_id, idempotency_key, settings, limiter)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except IdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _dispatch_run(background_tasks, run.id, run.status)
    return _run_out(run)


@app.post("/runs/{run_id}/retry", response_model=RunOut)
def post_retry_run(
    run_id: int,
    body: RetryRunCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user_id: str = Header(default="anonymous", alias="X-User-ID"),
    tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
    workspace_id: str = Header(default="default", alias="X-Workspace-ID"),
) -> RunOut:
    try:
        workspace = get_or_create_workspace(db, tenant_id, workspace_id)
        source = db.get(Run, run_id)
        if not source or not _run_in_workspace(source, workspace.id):
            raise LookupError("run not found")
        run = retry_run(db, run_id, body, user_id, settings, limiter)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    _dispatch_run(background_tasks, run.id, run.status)
    return _run_out(run)


@app.post("/runs/{run_id}/cancel", response_model=RunOut)
def post_cancel_run(
    run_id: int,
    db: Session = Depends(get_db),
    tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
    workspace_id: str = Header(default="default", alias="X-Workspace-ID"),
) -> RunOut:
    try:
        workspace = get_or_create_workspace(db, tenant_id, workspace_id)
        existing = db.get(Run, run_id)
        if not existing or not _run_in_workspace(existing, workspace.id):
            raise LookupError("run not found")
        run = cancel_run(db, run_id, process_registry)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _run_out(run)


@app.get("/runs", response_model=list[RunCatalogItemOut])
def list_runs(
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
    tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
    workspace_id: str = Header(default="default", alias="X-Workspace-ID"),
) -> list[RunCatalogItemOut]:
    workspace = get_or_create_workspace(db, tenant_id, workspace_id)
    runs = db.execute(
        select(Run).join(Task).where(Task.workspace_id == workspace.id).order_by(Run.created_at.desc(), Run.id.desc()).limit(limit)
    ).scalars().all()
    return [_run_catalog_item(run) for run in runs]


@app.get("/evaluations/history", response_model=list[EvaluationHistoryItemOut])
def get_evaluation_history(
    db: Session = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
    tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
    workspace_id: str = Header(default="default", alias="X-Workspace-ID"),
) -> list[EvaluationHistoryItemOut]:
    workspace = get_or_create_workspace(db, tenant_id, workspace_id)
    return list_evaluation_history(db, workspace_id=workspace.id, limit=limit)


@app.get("/evaluations/{evaluation_id}/matrix", response_model=EvaluationMatrixOut)
def get_evaluation_result_matrix(
    evaluation_id: int,
    db: Session = Depends(get_db),
    tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
    workspace_id: str = Header(default="default", alias="X-Workspace-ID"),
) -> EvaluationMatrixOut:
    try:
        workspace = get_or_create_workspace(db, tenant_id, workspace_id)
        return get_evaluation_matrix(db, evaluation_id=evaluation_id, workspace_id=workspace.id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/evaluations/{task_id}")
def delete_evaluation(
    task_id: int,
    db: Session = Depends(get_db),
    tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
    workspace_id: str = Header(default="default", alias="X-Workspace-ID"),
) -> dict[str, int | str]:
    try:
        workspace = get_or_create_workspace(db, tenant_id, workspace_id)
        result = delete_evaluation_task(db, task_id=task_id, workspace_id=workspace.id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "deleted", **result}


@app.get("/runs/{run_id}", response_model=RunOut)
def get_run(
    run_id: int,
    db: Session = Depends(get_db),
    tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
    workspace_id: str = Header(default="default", alias="X-Workspace-ID"),
) -> RunOut:
    run = db.get(Run, run_id)
    workspace = get_or_create_workspace(db, tenant_id, workspace_id)
    if not run or not _run_in_workspace(run, workspace.id):
        raise HTTPException(status_code=404, detail="run not found")
    cache.set(f"run:{run_id}", run.status)
    return _run_out(run)


@app.get("/runs/{run_id}/source", response_model=RunSourceOut)
def get_run_source(
    run_id: int,
    db: Session = Depends(get_db),
    tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
    workspace_id: str = Header(default="default", alias="X-Workspace-ID"),
) -> RunSourceOut:
    run = db.get(Run, run_id)
    workspace = get_or_create_workspace(db, tenant_id, workspace_id)
    if not run or not _run_in_workspace(run, workspace.id):
        raise HTTPException(status_code=404, detail="run not found")
    if not run.artifacts_dir:
        raise HTTPException(status_code=404, detail="source snapshot not found")

    repo_root = (Path(run.artifacts_dir).resolve() / "repo").resolve()
    runs_root = settings.harness_runs_root.resolve()
    if runs_root not in repo_root.parents and repo_root != runs_root:
        raise HTTPException(status_code=400, detail="artifact path escaped root")
    if not repo_root.is_dir():
        raise HTTPException(status_code=404, detail="source snapshot not found")

    files: list[SourceFileOut] = []
    total_bytes = 0
    for path in sorted(repo_root.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        relative = path.relative_to(repo_root).as_posix()
        if not _include_source_snapshot_file(relative, path):
            continue
        size = path.stat().st_size
        if size > _SOURCE_MAX_FILE_BYTES or total_bytes + size > _SOURCE_MAX_TOTAL_BYTES:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        files.append(SourceFileOut(path=relative, content=content))
        total_bytes += size
        if len(files) >= _SOURCE_MAX_FILES:
            break

    return RunSourceOut(
        run_id=run.id,
        harness_run_id=run.harness_run_id,
        artifacts_dir=run.artifacts_dir,
        files=files,
    )


@app.get("/runs/{run_id}/failure-context", response_model=FailureContextOut)
def get_failure_context(
    run_id: int,
    db: Session = Depends(get_db),
    tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
    workspace_id: str = Header(default="default", alias="X-Workspace-ID"),
) -> FailureContextOut:
    try:
        workspace = get_or_create_workspace(db, tenant_id, workspace_id)
        run = db.get(Run, run_id)
        if not run or not _run_in_workspace(run, workspace.id):
            raise LookupError("run not found")
        return FailureContextOut.model_validate(
            build_failure_context(
                db,
                run_id,
                settings.harness_runs_root,
                settings.evaluation_memory_path,
                workspace_id=workspace.id,
            )
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/memory/evaluation", response_model=EvaluationMemoryListOut)
def list_evaluation_memory(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
    workspace_id: str = Header(default="default", alias="X-Workspace-ID"),
) -> EvaluationMemoryListOut:
    workspace = get_or_create_workspace(db, tenant_id, workspace_id)
    items = EvaluationMemoryStore(settings.evaluation_memory_path).list_recent(limit, workspace_id=workspace.id)
    return EvaluationMemoryListOut(count=len(items), items=items)


@app.get("/memory/evaluation/summary", response_model=EvaluationMemorySummaryOut)
def get_evaluation_memory_summary(
    recent_limit: int = Query(default=5, ge=1, le=20),
    db: Session = Depends(get_db),
    tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
    workspace_id: str = Header(default="default", alias="X-Workspace-ID"),
) -> EvaluationMemorySummaryOut:
    workspace = get_or_create_workspace(db, tenant_id, workspace_id)
    return EvaluationMemorySummaryOut.model_validate(
        EvaluationMemoryStore(settings.evaluation_memory_path).summarize(recent_limit=recent_limit, workspace_id=workspace.id)
    )


@app.get("/runs/{run_id}/report", response_class=HTMLResponse)
def get_report(
    run_id: int,
    db: Session = Depends(get_db),
    tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
    workspace_id: str = Header(default="default", alias="X-Workspace-ID"),
):
    workspace = get_or_create_workspace(db, tenant_id, workspace_id)
    return HTMLResponse(
        _artifact(run_id, db, "report.html", workspace.id).read_text(encoding="utf-8"),
        headers=_REPORT_SECURITY_HEADERS,
    )


@app.get("/runs/{run_id}/patch", response_class=PlainTextResponse)
def get_patch(
    run_id: int,
    db: Session = Depends(get_db),
    tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
    workspace_id: str = Header(default="default", alias="X-Workspace-ID"),
):
    workspace = get_or_create_workspace(db, tenant_id, workspace_id)
    return PlainTextResponse(_artifact(run_id, db, "patch.diff", workspace.id).read_text(encoding="utf-8"), media_type="text/plain")


@app.get("/runs/{run_id}/scorecard")
def get_scorecard(
    run_id: int,
    db: Session = Depends(get_db),
    tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
    workspace_id: str = Header(default="default", alias="X-Workspace-ID"),
):
    workspace = get_or_create_workspace(db, tenant_id, workspace_id)
    return JSONResponse(read_json(_artifact(run_id, db, "scorecard.json", workspace.id)))


@app.get("/runs/{run_id}/test-result")
def get_test_result(
    run_id: int,
    db: Session = Depends(get_db),
    tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
    workspace_id: str = Header(default="default", alias="X-Workspace-ID"),
):
    workspace = get_or_create_workspace(db, tenant_id, workspace_id)
    return JSONResponse(read_json(_artifact(run_id, db, "test_result.json", workspace.id)))


@app.get("/runs/{run_id}/trace", response_class=PlainTextResponse)
def get_trace(
    run_id: int,
    db: Session = Depends(get_db),
    tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
    workspace_id: str = Header(default="default", alias="X-Workspace-ID"),
):
    workspace = get_or_create_workspace(db, tenant_id, workspace_id)
    return PlainTextResponse(_artifact(run_id, db, "trace.jsonl", workspace.id).read_text(encoding="utf-8"), media_type="text/plain")


@app.get("/runs/{run_id}/agent-run")
def get_agent_run(
    run_id: int,
    db: Session = Depends(get_db),
    tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
    workspace_id: str = Header(default="default", alias="X-Workspace-ID"),
):
    workspace = get_or_create_workspace(db, tenant_id, workspace_id)
    return JSONResponse(read_json(_artifact(run_id, db, "api_agent_run.json", workspace.id)))


@app.get("/metrics/cost", response_model=CostMetricsOut)
def get_cost_metrics(
    db: Session = Depends(get_db),
    date_from: str | None = Query(default=None, alias="from"),
    date_to: str | None = Query(default=None, alias="to"),
) -> CostMetricsOut:
    try:
        parsed_from = _parse_date(date_from)
        parsed_to = _parse_date(date_to)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="date filters must be ISO-8601 datetime strings") from exc
    return cost_metrics(db, parsed_from, parsed_to)


@app.get("/evaluation/summary", response_model=EvaluationSummaryOut)
def get_evaluation_summary(
    db: Session = Depends(get_db),
    tenant_id: str = Header(default="default", alias="X-Tenant-ID"),
    workspace_id: str = Header(default="default", alias="X-Workspace-ID"),
) -> EvaluationSummaryOut:
    workspace = get_or_create_workspace(db, tenant_id, workspace_id)
    return EvaluationSummaryOut.model_validate(build_evaluation_summary(db, settings.harness_runs_root, workspace_id=workspace.id))



def _id_state(ids: list[int]) -> DemoIdStateOut:
    return DemoIdStateOut(
        count=len(ids),
        min_id=min(ids) if ids else None,
        max_id=max(ids) if ids else None,
        ids=ids,
    )
def _execute_run_in_new_session(run_id: int) -> None:
    db = app.state.session_factory()
    try:
        execute_run(db, run_id, harness_client, settings)
    finally:
        db.close()


def _schedule_run(background_tasks: BackgroundTasks, run_id: int) -> None:
    background_tasks.add_task(_execute_run_in_new_session, run_id)


def _dispatch_run(background_tasks: BackgroundTasks, run_id: int, status: str) -> None:
    if status != "pending":
        return
    if settings.auto_start_runs:
        _schedule_run(background_tasks, run_id)
        return
    run_queue.enqueue(run_id)


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
        workspace_id=run.task.workspace_id if run.task else None,
        status=run.status,
        mode=run.mode,
        model=run.model,
        model_provider=run.model_provider,
        base_url=run.base_url,
        wire_api=run.wire_api,
        reasoning_effort=run.reasoning_effort,
        disable_response_storage=run.disable_response_storage,
        timeout_seconds=run.timeout_seconds,
        source_run_id=run.source_run_id,
        failure_context_path=run.failure_context_path,
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


def _run_catalog_item(run: Run) -> RunCatalogItemOut:
    out = _run_out(run)
    task = run.task
    return RunCatalogItemOut(
        **out.model_dump(),
        task_name=task.name if task else f"task #{run.task_id}",
        task_description=task.description if task else "",
        harness_task_path=task.harness_task_path if task else "",
    )


def _artifact(run_id: int, db: Session, filename: str, workspace_id: int | None = None) -> Path:
    run = db.get(Run, run_id)
    if not run or (workspace_id is not None and not _run_in_workspace(run, workspace_id)):
        raise HTTPException(status_code=404, detail="run not found")
    if not run.artifacts_dir:
        raise HTTPException(status_code=404, detail="artifact not found")
    try:
        return resolve_artifact(settings.harness_runs_root, run.artifacts_dir, filename)
    except ArtifactNotFound as exc:
        raise HTTPException(status_code=404, detail="artifact not found") from exc
    except UnsafeArtifactPath as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _include_source_snapshot_file(relative: str, path: Path) -> bool:
    parts = Path(relative).parts
    if any(part in _SOURCE_IGNORED_DIR_NAMES for part in parts[:-1]):
        return False
    name = path.name.lower()
    if path.name in _SOURCE_IGNORED_FILE_NAMES or name.startswith(".env"):
        return False
    if any(fragment in name for fragment in _SOURCE_SENSITIVE_NAME_FRAGMENTS):
        return False
    return path.suffix in _SOURCE_ALLOWED_SUFFIXES


def _run_in_workspace(run: Run, workspace_id: int) -> bool:
    return bool(run.task and run.task.workspace_id == workspace_id)


def _ensure_task_in_workspace(db: Session, task_id: int, workspace_id: int) -> None:
    task = db.get(Task, task_id)
    if not task or task.workspace_id != workspace_id:
        raise LookupError("task not found")


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _redact_url(value: str) -> str:
    if "@" not in value:
        return value
    scheme, rest = value.split("://", 1) if "://" in value else ("", value)
    host = rest.split("@", 1)[1]
    return f"{scheme}://<redacted>@{host}" if scheme else f"<redacted>@{host}"
