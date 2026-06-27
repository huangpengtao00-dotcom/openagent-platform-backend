from __future__ import annotations

import subprocess
import json
import re
import shlex
from datetime import datetime
from pathlib import Path
from typing import Protocol

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import Settings
from .difficulty_analyzer import CodeDifficultyAnalyzer
from .evaluation_memory import EvaluationMemoryStore
from .failure_context import write_failure_context
from .harness_client import HarnessClient
from .models import Evaluation, Run, RunStatus, Task, Tenant, Usage, Workspace
from .rate_limit import MemoryRateLimiter
from .schemas import (
    CostMetricsOut,
    CostModelOut,
    CustomTaskCreate,
    EvaluationCreate,
    EvaluationDraftCreate,
    EvaluationDraftOut,
    EvaluationHistoryItemOut,
    EvaluationHistoryRunOut,
    EvaluationMatrixCellOut,
    EvaluationMatrixOut,
    EvaluationMatrixTaskOut,
    RetryRunCreate,
    RunCreate,
    TaskCreate,
)
from .time import utc_now


_ALLOWED_CUSTOM_ACCEPTANCE_COMMANDS = {
    ("pytest",),
    ("pytest", "-q"),
    ("python", "-m", "pytest"),
    ("python", "-m", "pytest", "-q"),
    ("python3", "-m", "pytest"),
    ("python3", "-m", "pytest", "-q"),
    ("py", "-m", "pytest"),
    ("py", "-m", "pytest", "-q"),
}
_DEFAULT_TENANT_SLUG = "default"
_DEFAULT_WORKSPACE_SLUG = "default"


class IdempotencyConflict(ValueError):
    pass


class ProcessCanceller(Protocol):
    def cancel(self, run_id: int) -> bool:
        ...


def get_or_create_workspace(db: Session, tenant_slug: str | None = None, workspace_slug: str | None = None) -> Workspace:
    safe_tenant_slug = _slugify(tenant_slug or _DEFAULT_TENANT_SLUG)
    safe_workspace_slug = _slugify(workspace_slug or _DEFAULT_WORKSPACE_SLUG)
    tenant = db.execute(select(Tenant).where(Tenant.slug == safe_tenant_slug)).scalar_one_or_none()
    if tenant is None:
        tenant = Tenant(slug=safe_tenant_slug, name=safe_tenant_slug)
        db.add(tenant)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            tenant = db.execute(select(Tenant).where(Tenant.slug == safe_tenant_slug)).scalar_one()
        db.refresh(tenant)
    workspace = db.execute(
        select(Workspace).where(Workspace.tenant_id == tenant.id, Workspace.slug == safe_workspace_slug)
    ).scalar_one_or_none()
    if workspace is None:
        workspace = Workspace(tenant_id=tenant.id, slug=safe_workspace_slug, name=safe_workspace_slug)
        db.add(workspace)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            workspace = db.execute(
                select(Workspace).where(Workspace.tenant_id == tenant.id, Workspace.slug == safe_workspace_slug)
            ).scalar_one()
        db.refresh(workspace)
    return workspace


def create_custom_task(db: Session, body: CustomTaskCreate, settings: Settings, workspace_id: int | None = None) -> Task:
    source_filename = _safe_repo_filename(body.source_filename)
    test_filename = _safe_repo_filename(body.test_filename)
    if source_filename == test_filename:
        raise PermissionError("custom task source and test filenames must be different")
    acceptance_command = _safe_custom_acceptance_command(body.acceptance_command)
    slug = _slugify(body.name)
    task_root = _unique_custom_task_root(settings.harness_root, slug)
    repo_dir = task_root / "repo"
    repo_dir.mkdir(parents=True, exist_ok=False)
    (repo_dir / source_filename).write_text(body.source_code, encoding="utf-8")
    (repo_dir / test_filename).write_text(body.test_code, encoding="utf-8")
    task_spec = {
        "id": task_root.name,
        "repo": str(repo_dir),
        "goal": body.goal,
        "allowlist": [source_filename],
        "acceptance": [acceptance_command],
        "budget": {"acceptance_timeout_seconds": 30, "context_summary_files": 8},
    }
    task_path = task_root / "task.json"
    task_path.write_text(json.dumps(task_spec, ensure_ascii=False, indent=2), encoding="utf-8")
    return create_task(
        db,
        TaskCreate(name=body.name, description=body.goal, harness_task_path=str(task_path)),
        settings,
        workspace_id=workspace_id,
    )


def create_evaluation_runs(
    db: Session,
    body: EvaluationCreate,
    user_id: str,
    settings: Settings,
    limiter: MemoryRateLimiter,
    workspace_id: int | None = None,
    idempotency_key: str | None = None,
) -> tuple[Evaluation, Task, list[Run], bool]:
    if idempotency_key:
        existing = db.execute(
            select(Evaluation).where(
                Evaluation.workspace_id == workspace_id,
                Evaluation.idempotency_key == idempotency_key,
            )
        ).scalar_one_or_none()
        if existing:
            task = db.get(Task, existing.task_id)
            if not task:
                raise LookupError("evaluation task not found")
            return existing, task, sorted(task.runs, key=lambda item: item.id), False
    acceptance_command = _safe_custom_acceptance_command(body.acceptance_command)
    task = _create_multifile_harness_task(
        db,
        name=body.name,
        goal=body.goal,
        files=[(item.path, item.content) for item in body.files],
        test_files=[(item.path, item.content) for item in body.test_files],
        acceptance_command=acceptance_command,
        context_summary_files=body.context_summary_files,
        llm_timeout_seconds=_evaluation_llm_timeout_seconds(
            [profile.timeout_seconds for profile in body.model_profiles]
        ),
        settings=settings,
        workspace_id=workspace_id,
    )
    evaluation = Evaluation(
        workspace_id=workspace_id,
        task_id=task.id,
        name=body.name,
        goal=body.goal,
        idempotency_key=idempotency_key,
    )
    db.add(evaluation)
    db.commit()
    db.refresh(evaluation)
    runs: list[Run] = []
    for profile in body.model_profiles:
        run = create_run(
            db,
            RunCreate(
                task_id=task.id,
                mode=profile.mode,
                model=profile.model,
                model_provider=profile.model_provider or profile.name,
                base_url=profile.base_url,
                wire_api=profile.wire_api,
                reasoning_effort=profile.reasoning_effort,
                disable_response_storage=profile.disable_response_storage,
                allow_llm_calls=profile.allow_llm_calls,
                timeout_seconds=profile.timeout_seconds,
            ),
            user_id,
            f"evaluation:{task.id}:{_slugify(profile.name)}",
            settings,
            limiter,
        )
        runs.append(run)
    return evaluation, task, runs, True


def get_evaluation_matrix(db: Session, *, evaluation_id: int, workspace_id: int) -> EvaluationMatrixOut:
    evaluation = db.get(Evaluation, evaluation_id)
    if not evaluation or evaluation.workspace_id != workspace_id:
        raise LookupError("evaluation not found")
    task = db.get(Task, evaluation.task_id)
    if not task or task.workspace_id != workspace_id:
        raise LookupError("evaluation task not found")
    runs = sorted(task.runs, key=lambda item: (item.model_provider or item.model, item.id))
    passed = sum(1 for run in runs if run.status == RunStatus.passed.value)
    failed = sum(1 for run in runs if run.status in {RunStatus.failed.value, RunStatus.timeout.value, RunStatus.cancelled.value})
    pending = sum(1 for run in runs if run.status == RunStatus.pending.value)
    running = sum(1 for run in runs if run.status == RunStatus.running.value)
    terminal = passed + failed
    total_tokens = sum((run.usage.total_tokens if run.usage else 0) for run in runs)
    total_cost = sum((run.usage.estimated_cost_usd if run.usage else 0.0) for run in runs)
    model_labels = sorted({run.model_provider or run.model for run in runs})
    return EvaluationMatrixOut(
        evaluation_id=evaluation.id,
        name=evaluation.name,
        goal=evaluation.goal,
        status=_history_status(pending=pending, running=running, passed=passed, failed=failed, total=len(runs)),
        task_count=1,
        model_count=len(model_labels),
        run_count=len(runs),
        passed=passed,
        failed=failed,
        pending=pending,
        running=running,
        pass_rate=(passed / terminal) if terminal else 0.0,
        total_tokens=total_tokens,
        estimated_cost_usd=round(total_cost, 8),
        created_at=evaluation.created_at,
        tasks=[
            EvaluationMatrixTaskOut(
                task_id=task.id,
                task_name=task.name,
                task_description=task.description,
                models=[
                    EvaluationMatrixCellOut(
                        run_id=run.id,
                        status=run.status,
                        model=run.model,
                        model_provider=run.model_provider,
                        failure_type=run.failure_type,
                        error_message=run.error_message,
                        total_tokens=run.usage.total_tokens if run.usage else 0,
                        estimated_cost_usd=round(run.usage.estimated_cost_usd, 8) if run.usage else 0.0,
                        duration_seconds=_run_duration_seconds(run),
                        artifacts_dir=run.artifacts_dir,
                    )
                    for run in runs
                ],
            )
        ],
    )


def build_evaluation_draft(body: EvaluationDraftCreate) -> EvaluationDraftOut:
    source_filename = _safe_repo_relative_path(body.source_filename)
    module_name = Path(source_filename).stem or "app"
    test_filename = f"test_{Path(source_filename).name}" if not Path(source_filename).name.startswith("test_") else Path(source_filename).name
    functions = _extract_python_function_names(body.source_code)
    primary_function = functions[0] if functions else None
    findings = _draft_findings(body.source_code, functions)
    requested_change = (body.instruction or "").strip()
    goal = _draft_goal(body, primary_function, findings, requested_change)
    test_code = _draft_test_code(body, module_name, primary_function, requested_change)
    difficulty = CodeDifficultyAnalyzer().analyze(
        source_code=body.source_code,
        filename=source_filename,
        user_goal=requested_change or goal,
        tests=body.current_test_code,
    )
    name = body.current_name or _draft_name(primary_function, source_filename, requested_change)
    if requested_change and body.current_test_code:
        findings.append("已根据你的补充提示词重新整理草稿，保留源码输入，只调整目标和测试建议。")
    return EvaluationDraftOut(
        name=name,
        goal=goal,
        source_filename=source_filename,
        source_code=body.source_code,
        test_filename=test_filename,
        test_code=test_code,
        acceptance_command="python -m pytest -q",
        difficulty={
            "difficulty_level": difficulty.difficulty_level,
            "difficulty_score": difficulty.difficulty_score,
            "reasons": difficulty.reasons,
            "risk_factors": difficulty.risk_factors,
            "suggested_strategy": difficulty.suggested_strategy,
        },
        difficulty_level=difficulty.difficulty_level,
        difficulty_score=difficulty.difficulty_score,
        difficulty_reasons=difficulty.reasons,
        risk_factors=difficulty.risk_factors,
        suggested_strategy=difficulty.suggested_strategy,
        analysis_steps=[
            "读取用户粘贴的源码，识别可编辑文件、函数入口和明显分支。",
            f"根据代码结构、依赖和边界场景判断任务难度为：{difficulty.difficulty_level}。",
            "推断最小可验收目标，避免把评测任务扩大成泛泛重构。",
            "生成 pytest 骨架，让模型输出可以被 Harness 自动验收。",
            "等待用户确认；用户可手动改，也可继续用提示词让系统重整草稿。",
        ],
        findings=findings,
        suggested_changes=[
            "确认目标是否就是你想让模型修复的行为。",
            "检查测试断言是否覆盖真实失败场景。",
            "如果源码依赖外部服务，建议把测试改成纯函数或 mock 输入。",
        ],
        confidence="规则整理草稿，适合快速开始；接入真实整理模型后可生成更贴近业务的测试。",
    )


def create_task(db: Session, body: TaskCreate, settings: Settings, workspace_id: int | None = None) -> Task:
    task_spec_path = _resolve_harness_task_path(body.harness_task_path, settings.harness_root)
    task = Task(name=body.name, description=body.description, harness_task_path=str(task_spec_path), workspace_id=workspace_id)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def list_evaluation_history(db: Session, *, workspace_id: int, limit: int = 50) -> list[EvaluationHistoryItemOut]:
    tasks = db.execute(
        select(Task).where(Task.workspace_id == workspace_id).order_by(Task.created_at.desc(), Task.id.desc()).limit(limit)
    ).scalars().all()
    history: list[EvaluationHistoryItemOut] = []
    for task in tasks:
        evaluation = sorted(task.evaluations, key=lambda item: (item.created_at, item.id), reverse=True)[0] if task.evaluations else None
        runs = sorted(task.runs, key=lambda item: (item.created_at, item.id), reverse=True)
        if not runs:
            continue
        terminal_runs = [run for run in runs if run.status in {RunStatus.passed.value, RunStatus.failed.value, RunStatus.timeout.value, RunStatus.cancelled.value}]
        passed = sum(1 for run in runs if run.status == RunStatus.passed.value)
        failed = sum(1 for run in runs if run.status in {RunStatus.failed.value, RunStatus.timeout.value, RunStatus.cancelled.value})
        pending = sum(1 for run in runs if run.status == RunStatus.pending.value)
        running = sum(1 for run in runs if run.status == RunStatus.running.value)
        total_tokens = sum((run.usage.total_tokens if run.usage else 0) for run in runs)
        total_cost = sum((run.usage.estimated_cost_usd if run.usage else 0.0) for run in runs)
        latest = runs[0]
        best = next((run for run in runs if run.status == RunStatus.passed.value), None)
        latest_failed = next((run for run in runs if run.status in {RunStatus.failed.value, RunStatus.timeout.value, RunStatus.cancelled.value}), None)
        failure_types: dict[str, int] = {}
        for run in runs:
            if run.status not in {RunStatus.failed.value, RunStatus.timeout.value, RunStatus.cancelled.value}:
                continue
            failure_type = _normalize_failure_type(run.failure_type) or "Unknown"
            failure_types[failure_type] = failure_types.get(failure_type, 0) + 1
        models = sorted({run.model_provider or run.model for run in runs})
        status = _history_status(pending=pending, running=running, passed=passed, failed=failed, total=len(runs))
        history.append(
            EvaluationHistoryItemOut(
                evaluation_id=evaluation.id if evaluation else None,
                task_id=task.id,
                name=evaluation.name if evaluation else task.name,
                description=evaluation.goal if evaluation else task.description,
                created_at=evaluation.created_at if evaluation else task.created_at,
                status=status,
                run_count=len(runs),
                model_count=len(models),
                passed=passed,
                failed=failed,
                pending=pending,
                running=running,
                pass_rate=(passed / len(terminal_runs)) if terminal_runs else 0.0,
                total_tokens=total_tokens,
                estimated_cost_usd=round(total_cost, 8),
                latest_run_id=latest.id,
                best_run_id=best.id if best else None,
                latest_failure_type=latest_failed.failure_type if latest_failed else None,
                latest_error_message=latest_failed.error_message if latest_failed else None,
                failure_types=failure_types,
                models=models,
                runs=[
                    EvaluationHistoryRunOut(
                        run_id=run.id,
                        status=run.status,
                        model=run.model,
                        model_provider=run.model_provider,
                        harness_run_id=run.harness_run_id,
                        failure_type=run.failure_type,
                        error_message=run.error_message,
                        total_tokens=run.usage.total_tokens if run.usage else 0,
                        estimated_cost_usd=run.usage.estimated_cost_usd if run.usage else 0.0,
                        created_at=run.created_at,
                    )
                    for run in runs[:8]
                ],
            )
        )
    return history


def delete_evaluation_task(db: Session, *, task_id: int, workspace_id: int) -> dict[str, int]:
    task = db.get(Task, task_id)
    if not task or task.workspace_id != workspace_id:
        raise LookupError("evaluation task not found")
    running = [run for run in task.runs if run.status in {RunStatus.pending.value, RunStatus.running.value}]
    if running:
        raise PermissionError("evaluation task has pending or running runs; cancel them before deleting")
    run_count = len(task.runs)
    usage_count = 0
    for evaluation in list(task.evaluations):
        db.delete(evaluation)
    for run in list(task.runs):
        if run.usage is not None:
            db.delete(run.usage)
            usage_count += 1
        db.delete(run)
    db.delete(task)
    db.commit()
    return {"task_id": task_id, "deleted_runs": run_count, "deleted_usage": usage_count}


def retry_run(
    db: Session,
    source_run_id: int,
    body: RetryRunCreate,
    user_id: str,
    settings: Settings,
    limiter: MemoryRateLimiter,
) -> Run:
    source = db.get(Run, source_run_id)
    if not source:
        raise LookupError("run not found")
    if source.status not in {RunStatus.failed.value, RunStatus.timeout.value, RunStatus.cancelled.value}:
        raise PermissionError("only failed, timed out, or cancelled runs can be retried")
    failure_context_path = None
    if body.use_failure_context:
        failure_context_path = str(write_failure_context(db, source.id, settings.harness_runs_root, settings.evaluation_memory_path))
    retry_body = RunCreate(
        task_id=source.task_id,
        mode=source.mode,
        model=source.model,
        model_provider=source.model_provider,
        base_url=source.base_url,
        wire_api=_schema_wire_api(source.wire_api),
        reasoning_effort=source.reasoning_effort,
        disable_response_storage=source.disable_response_storage,
        allow_llm_calls=body.allow_llm_calls,
        timeout_seconds=body.timeout_seconds or source.timeout_seconds,
    )
    run = create_run(db, retry_body, user_id, None, settings, limiter)
    run.source_run_id = source.id
    run.failure_context_path = failure_context_path
    db.commit()
    db.refresh(run)
    return run


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
    stored_idempotency_key = _workspace_idempotency_key(task.workspace_id, idempotency_key)
    if idempotency_key:
        existing = db.execute(
            select(Run).where(Run.user_id == user_id, Run.idempotency_key == stored_idempotency_key)
        ).scalar_one_or_none()
        if existing:
            expected_model = body.model or settings.harness_default_model
            if (
                existing.task_id != task.id
                or existing.mode != body.mode
                or existing.model != expected_model
                or existing.model_provider != body.model_provider
                or existing.base_url != body.base_url
                or existing.wire_api != body.wire_api
                or existing.reasoning_effort != body.reasoning_effort
                or existing.disable_response_storage != body.disable_response_storage
                or existing.allow_llm_calls != body.allow_llm_calls
                or existing.timeout_seconds != body.timeout_seconds
            ):
                raise IdempotencyConflict("Idempotency-Key was already used with a different run request")
            return existing
    if body.mode == "api" and body.allow_llm_calls and not settings.allow_real_llm_calls:
        raise PermissionError("real LLM calls are disabled by ALLOW_REAL_LLM_CALLS")
    if body.mode == "api" and body.allow_llm_calls:
        _ensure_real_api_budget_available(db, settings)
    limiter.check(f"runs:{user_id}")
    run = Run(
        task_id=task.id,
        user_id=user_id,
        idempotency_key=stored_idempotency_key,
        status=RunStatus.pending.value,
        mode=body.mode,
        model=body.model or settings.harness_default_model,
        model_provider=body.model_provider,
        base_url=body.base_url,
        wire_api=body.wire_api,
        reasoning_effort=body.reasoning_effort,
        disable_response_storage=body.disable_response_storage,
        allow_llm_calls=body.allow_llm_calls,
        timeout_seconds=body.timeout_seconds,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def execute_run(db: Session, run_id: int, client: HarnessClient, settings: Settings) -> bool:
    claimed_at = utc_now()
    claimed = db.execute(
        update(Run)
        .where(Run.id == run_id, Run.status == RunStatus.pending.value)
        .values(status=RunStatus.running.value, started_at=claimed_at)
    ).rowcount
    db.commit()
    if claimed != 1:
        return False

    run = db.get(Run, run_id)
    if not run:
        return False
    task = db.get(Task, run.task_id)
    if not task:
        run.status = RunStatus.failed.value
        run.failure_type = "task_not_found"
        run.error_message = "task not found"
        run.finished_at = utc_now()
        db.commit()
        return True
    try:
        result = client.run_task(
            task_spec_path=task.harness_task_path,
            mode=run.mode,
            model=run.model,
            runs_root=str(settings.harness_runs_root),
            allow_llm_calls=run.allow_llm_calls,
            model_provider=run.model_provider,
            base_url=run.base_url,
            wire_api=run.wire_api,
            reasoning_effort=run.reasoning_effort,
            disable_response_storage=run.disable_response_storage,
            timeout_seconds=run.timeout_seconds,
            failure_context_path=run.failure_context_path,
            run_id=run.id,
            should_cancel=lambda: _run_is_cancelled(db, run),
        )
        db.refresh(run)
        if run.status == RunStatus.cancelled.value:
            return True
        run.harness_run_id = result.harness_run_id
        run.artifacts_dir = str(result.artifacts_dir)
        run.status = RunStatus.passed.value if result.status == "pass" else RunStatus.failed.value
        failure_type = _normalize_failure_type(result.failure_type)
        run.failure_type = failure_type
        run.error_message = None if run.status == RunStatus.passed.value else (result.error_message or failure_type or "harness failed")
        upsert_usage(db, run, result.usage)
    except subprocess.TimeoutExpired as exc:
        db.refresh(run)
        if run.status == RunStatus.cancelled.value:
            return True
        run.status = RunStatus.timeout.value
        run.failure_type = "timeout"
        run.error_message = str(exc)
    except Exception as exc:
        db.refresh(run)
        if run.status == RunStatus.cancelled.value:
            return True
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
            _record_evaluation_memory(db, run, settings)
    return True


def upsert_usage(db: Session, run: Run, data: dict) -> Usage:
    usage = run.usage or Usage(run_id=run.id)
    usage.model = str(data.get("model") or run.model)
    usage.prompt_tokens = int(data.get("prompt_tokens") or 0)
    usage.completion_tokens = int(data.get("completion_tokens") or 0)
    usage.total_tokens = int(data.get("total_tokens") or 0)
    usage.estimated_cost_usd = float(data.get("estimated_cost_usd") or 0.0)
    db.add(usage)
    return usage


def _record_evaluation_memory(db: Session, run: Run, settings: Settings) -> None:
    memory_path = getattr(settings, "evaluation_memory_path", None)
    if memory_path is None:
        return
    try:
        EvaluationMemoryStore(memory_path).append_from_run(db, run, settings.harness_runs_root)
    except Exception:
        return


def _resolve_harness_task_path(task_path: str, harness_root: Path) -> Path:
    root = Path(harness_root).resolve()
    candidate = Path(task_path)
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.resolve()
    if candidate != root and root not in candidate.parents:
        raise PermissionError(f"harness_task_path must stay inside allowed harness root: {root}")
    return candidate


def _ensure_real_api_budget_available(db: Session, settings: Settings) -> None:
    spent_usd = db.execute(
        select(func.sum(Usage.estimated_cost_usd))
        .join(Run)
        .where(Run.mode == "api", Run.allow_llm_calls.is_(True))
    ).scalar()
    spent_cny = float(spent_usd or 0.0) * settings.usd_to_cny_rate
    limit = settings.real_api_budget_limit_cny
    if spent_cny >= limit:
        raise PermissionError(f"real API retry budget reached {limit:g} CNY")


def _safe_repo_filename(value: str) -> str:
    path = Path(value)
    if path.name != value or path.is_absolute() or value in {"", ".", ".."}:
        raise PermissionError("custom task filename must be a single safe repo filename")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", value):
        raise PermissionError("custom task filename contains unsupported characters")
    return value


def _safe_repo_relative_path(value: str) -> str:
    normalized = value.replace("\\", "/").strip()
    path = Path(normalized)
    if path.is_absolute() or normalized in {"", ".", ".."}:
        raise PermissionError("custom task file path must be relative")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise PermissionError("custom task file path cannot contain empty, current, or parent segments")
    if not re.fullmatch(r"[A-Za-z0-9_./-]+", normalized):
        raise PermissionError("custom task file path contains unsupported characters")
    return path.as_posix()


def _extract_python_function_names(source_code: str) -> list[str]:
    return re.findall(r"(?m)^def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", source_code)[:8]


def _draft_findings(source_code: str, functions: list[str]) -> list[str]:
    findings: list[str] = []
    if functions:
        findings.append(f"识别到函数入口：{', '.join(functions[:4])}。")
    else:
        findings.append("没有识别到顶层函数，建议确认源码是否为单文件 Python 任务。")
    if "TODO" in source_code or "pass" in source_code:
        findings.append("源码里存在 TODO/pass，占位逻辑可能是最适合作为评测目标的地方。")
    if "except" not in source_code and any(token in source_code for token in ["int(", "json", "[", "requests", "http"]):
        findings.append("源码可能缺少异常或边界输入处理，测试建议覆盖缺失值、异常值和错误状态。")
    if "429" in source_code or "retry" in source_code.lower():
        findings.append("源码涉及重试/限流语义，建议重点验证 429、最大重试次数和非重试状态。")
    if "DEFAULT" in source_code or ".copy()" in source_code or "dict" in source_code:
        findings.append("源码涉及配置或字典合并，建议验证嵌套字段保留和默认值不被修改。")
    return findings[:5]


def _draft_goal(body: EvaluationDraftCreate, primary_function: str | None, findings: list[str], requested_change: str) -> str:
    if requested_change:
        return f"根据用户补充要求调整评测：{requested_change}"
    if body.current_goal:
        return body.current_goal
    if primary_function:
        return f"修复 `{primary_function}` 的核心行为，让它通过边界场景和回归测试。重点参考：{findings[0]}"
    return "根据粘贴源码补齐核心行为，让实现通过自动生成的 pytest 验收。"


def _draft_name(primary_function: str | None, source_filename: str, requested_change: str) -> str:
    if requested_change:
        return "按提示词调整后的源码评测"
    if primary_function:
        return f"{primary_function} 行为修复评测"
    return f"{Path(source_filename).stem} 源码评测"


def _draft_test_code(body: EvaluationDraftCreate, module_name: str, primary_function: str | None, requested_change: str) -> str:
    if requested_change and body.current_test_code:
        return "\n\n".join(
            [
                body.current_test_code.strip(),
                "# TODO: 根据上面的补充提示词，把这里改成更贴近业务预期的断言。",
            ]
        ).strip() + "\n"
    if primary_function:
        return (
            f"from {module_name} import {primary_function}\n\n\n"
            f"def test_{primary_function}_handles_normal_case():\n"
            f"    # TODO: 把输入和期望值改成真实业务样例。\n"
            f"    result = {primary_function}()\n"
            f"    assert result is not None\n\n\n"
            f"def test_{primary_function}_handles_edge_case():\n"
            f"    # TODO: 覆盖用户真正关心的失败/边界场景。\n"
            f"    assert callable({primary_function})\n"
        )
    return (
        f"import {module_name}\n\n\n"
        "def test_module_can_be_imported():\n"
        f"    assert {module_name} is not None\n"
    )


def _create_multifile_harness_task(
    db: Session,
    *,
    name: str,
    goal: str,
    files: list[tuple[str, str]],
    test_files: list[tuple[str, str]],
    acceptance_command: str,
    context_summary_files: int,
    llm_timeout_seconds: int | None,
    settings: Settings,
    workspace_id: int | None = None,
) -> Task:
    slug = _slugify(name)
    task_root = _unique_custom_task_root(settings.harness_root, slug)
    repo_dir = task_root / "repo"
    repo_dir.mkdir(parents=True, exist_ok=False)
    seen: set[str] = set()
    allowlist: list[str] = []
    for raw_path, content in files:
        safe_path = _safe_repo_relative_path(raw_path)
        if safe_path in seen:
            raise PermissionError(f"duplicate custom task file path: {safe_path}")
        seen.add(safe_path)
        target = repo_dir / safe_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        allowlist.append(safe_path)
    for raw_path, content in test_files:
        safe_path = _safe_repo_relative_path(raw_path)
        if safe_path in seen:
            raise PermissionError(f"duplicate custom task file path: {safe_path}")
        seen.add(safe_path)
        target = repo_dir / safe_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    if not allowlist:
        raise PermissionError("custom evaluation must include at least one editable source file")
    task_spec = {
        "id": task_root.name,
        "repo": str(repo_dir),
        "goal": goal,
        "allowlist": allowlist,
        "acceptance": [acceptance_command],
        "budget": {
            "acceptance_timeout_seconds": 30,
            "context_summary_files": context_summary_files,
            "llm_timeout_seconds": llm_timeout_seconds,
        },
    }
    task_path = task_root / "task.json"
    task_path.write_text(json.dumps(task_spec, ensure_ascii=False, indent=2), encoding="utf-8")
    return create_task(
        db,
        TaskCreate(name=name, description=goal, harness_task_path=str(task_path)),
        settings,
        workspace_id=workspace_id,
    )


def _evaluation_llm_timeout_seconds(profile_timeouts: list[int | None]) -> int:
    """Reserve a little process time for pytest and artifact collection."""
    max_profile_timeout = max((value or 180 for value in profile_timeouts), default=180)
    return max(60, max_profile_timeout - 30)


def _safe_custom_acceptance_command(value: str) -> str:
    try:
        parts = tuple(shlex.split(value.strip()))
    except ValueError as exc:
        raise PermissionError(f"custom task acceptance command is invalid: {exc}") from exc
    if parts not in _ALLOWED_CUSTOM_ACCEPTANCE_COMMANDS:
        raise PermissionError("custom task acceptance command must be a pytest command")
    return " ".join(parts)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value.strip().lower()).strip("-")
    return (slug or "custom-task")[:60]


def _unique_custom_task_root(harness_root: Path, slug: str) -> Path:
    root = Path(harness_root).resolve() / "custom_tasks"
    root.mkdir(parents=True, exist_ok=True)
    candidate = root / slug
    counter = 2
    while candidate.exists():
        candidate = root / f"{slug}-{counter}"
        counter += 1
    return candidate


def _normalize_failure_type(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"none", "null", "nil"}:
        return None
    return text


def _schema_wire_api(value: str | None):
    return value if value in {"chat_completions", "responses"} else None


def _history_status(*, pending: int, running: int, passed: int, failed: int, total: int) -> str:
    if running > 0 or pending > 0:
        return "running"
    if total > 0 and passed == total:
        return "pass"
    if passed > 0 and failed > 0:
        return "partial"
    if failed > 0:
        return "fail"
    return "empty"


def _run_duration_seconds(run: Run) -> float | None:
    if not run.started_at or not run.finished_at:
        return None
    return max(0.0, (run.finished_at - run.started_at).total_seconds())


def _workspace_idempotency_key(workspace_id: int | None, idempotency_key: str | None) -> str | None:
    if not idempotency_key:
        return None
    return f"workspace:{workspace_id or 'legacy'}:{idempotency_key}"


def _run_is_cancelled(db: Session, run: Run) -> bool:
    db.refresh(run)
    return run.status == RunStatus.cancelled.value


def cost_metrics(db: Session, date_from: datetime | None = None, date_to: datetime | None = None) -> CostMetricsOut:
    label = func.coalesce(Run.model_provider, Run.model, Usage.model)
    query = select(label, func.count(Usage.id), func.sum(Usage.total_tokens), func.sum(Usage.estimated_cost_usd)).join(Run)
    if date_from:
        query = query.where(Run.created_at >= date_from)
    if date_to:
        query = query.where(Run.created_at <= date_to)
    query = query.group_by(label).order_by(label)
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
