from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class TaskCreate(BaseModel):
    name: str
    description: str = ""
    harness_task_path: str

    model_config = {"extra": "forbid"}


class CustomTaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    goal: str = Field(min_length=1, max_length=2000)
    source_filename: str = Field(min_length=1, max_length=120)
    source_code: str = Field(min_length=1, max_length=20000)
    test_filename: str = Field(min_length=1, max_length=120)
    test_code: str = Field(min_length=1, max_length=20000)
    acceptance_command: str = Field(default="python -m pytest -q", min_length=1, max_length=200)

    model_config = {"extra": "forbid"}


class CustomTaskFileIn(BaseModel):
    path: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=30000)

    model_config = {"extra": "forbid"}


class EvaluationModelProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    mode: Literal["local", "api"] = "api"
    model: str = Field(min_length=1, max_length=120)
    model_provider: str | None = Field(default=None, max_length=80)
    base_url: str | None = Field(default=None, max_length=500)
    wire_api: Literal["chat_completions", "responses"] | None = None
    reasoning_effort: str | None = Field(default=None, max_length=40)
    disable_response_storage: bool = False
    allow_llm_calls: bool = False
    timeout_seconds: int | None = Field(default=180, ge=1, le=3600)

    model_config = {"extra": "forbid"}


class EvaluationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    goal: str = Field(min_length=1, max_length=3000)
    files: list[CustomTaskFileIn] = Field(min_length=1, max_length=20)
    test_files: list[CustomTaskFileIn] = Field(min_length=1, max_length=20)
    model_profiles: list[EvaluationModelProfileIn] = Field(min_length=1, max_length=8)
    acceptance_command: str = Field(default="python -m pytest -q", min_length=1, max_length=200)
    context_summary_files: int = Field(default=12, ge=1, le=80)

    model_config = {"extra": "forbid"}


class EvaluationDraftCreate(BaseModel):
    source_code: str = Field(min_length=1, max_length=30000)
    source_filename: str = Field(default="app.py", min_length=1, max_length=160)
    instruction: str | None = Field(default=None, max_length=2000)
    current_name: str | None = Field(default=None, max_length=120)
    current_goal: str | None = Field(default=None, max_length=3000)
    current_test_code: str | None = Field(default=None, max_length=30000)

    model_config = {"extra": "forbid"}


class EvaluationDraftOut(BaseModel):
    name: str
    goal: str
    source_filename: str
    source_code: str
    test_filename: str
    test_code: str
    acceptance_command: str
    difficulty: dict[str, Any]
    difficulty_level: Literal["easy", "medium", "hard"]
    difficulty_score: int
    difficulty_reasons: list[str] = Field(default_factory=list)
    risk_factors: list[str] = Field(default_factory=list)
    suggested_strategy: dict[str, Any] = Field(default_factory=dict)
    analysis_steps: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    suggested_changes: list[str] = Field(default_factory=list)
    confidence: str


class TaskOut(BaseModel):
    task_id: int
    workspace_id: int | None = None
    name: str
    description: str
    harness_task_path: str
    created_at: datetime

    model_config = {"from_attributes": True}


class RunCreate(BaseModel):
    task_id: int
    mode: Literal["local", "api"] = "local"
    model: str = "scripted"
    model_provider: str | None = Field(default=None, max_length=80)
    base_url: str | None = Field(default=None, max_length=500)
    wire_api: Literal["chat_completions", "responses"] | None = None
    reasoning_effort: str | None = Field(default=None, max_length=40)
    disable_response_storage: bool = False
    allow_llm_calls: bool = False
    timeout_seconds: int | None = Field(default=None, ge=1, le=3600)

    model_config = {"extra": "forbid"}


class RetryRunCreate(BaseModel):
    allow_llm_calls: bool = False
    timeout_seconds: int | None = Field(default=None, ge=1, le=3600)
    use_failure_context: bool = False

    model_config = {"extra": "forbid"}


class UsageOut(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    model: str

    model_config = {"from_attributes": True}


class RunOut(BaseModel):
    run_id: int
    task_id: int
    workspace_id: int | None = None
    status: str
    mode: str
    model: str
    model_provider: str | None = None
    base_url: str | None = None
    wire_api: str | None = None
    reasoning_effort: str | None = None
    disable_response_storage: bool = False
    timeout_seconds: int | None = None
    source_run_id: int | None = None
    failure_context_path: str | None = None
    harness_run_id: str | None = None
    artifacts_dir: str | None = None
    failure_type: str | None = None
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    usage: UsageOut | None = None
    artifacts: dict[str, str] = Field(default_factory=dict)

    model_config = {"from_attributes": True}


class RunCatalogItemOut(RunOut):
    task_name: str
    task_description: str
    harness_task_path: str


class EvaluationCreateOut(BaseModel):
    evaluation_id: int | None = None
    task: TaskOut
    runs: list[RunOut]
    next_steps: list[str] = Field(default_factory=list)


class RuntimeStatusOut(BaseModel):
    status: str
    app_env: str
    database: str
    harness_root: str
    harness_exists: bool
    harness_runs_root: str
    harness_executor: str
    harness_docker_image: str
    allow_real_llm_calls: bool
    real_api_budget_limit_cny: float
    auto_start_runs: bool
    queue_backend_configured: str
    queue_backend_active: str
    queue_key: str
    queue_depth: int | None = None
    redis_enabled: bool
    redis_url: str
    redis_available: bool


class DemoIdStateOut(BaseModel):
    count: int
    min_id: int | None = None
    max_id: int | None = None
    ids: list[int] = Field(default_factory=list)


class DemoStateOut(BaseModel):
    status: str
    database: str
    generated_at: datetime
    tasks: DemoIdStateOut
    runs: DemoIdStateOut
    latest_runs: list[RunCatalogItemOut] = Field(default_factory=list)


class SourceFileOut(BaseModel):
    path: str
    content: str


class RunSourceOut(BaseModel):
    run_id: int
    harness_run_id: str | None = None
    artifacts_dir: str | None = None
    files: list[SourceFileOut]


class FailureContextOut(BaseModel):
    source_run_id: int
    status: str
    failure_type: str | None = None
    error_message: str | None = None
    harness_run_id: str | None = None
    artifacts_dir: str
    task: dict[str, Any]
    artifacts: dict[str, Any]
    memory_hints: list[dict[str, Any]] = Field(default_factory=list)
    retry_guidance: dict[str, Any]


class EvaluationMemoryListOut(BaseModel):
    count: int
    items: list[dict[str, Any]]


class EvaluationMemorySummaryOut(BaseModel):
    total_records: int
    passed_records: int
    failed_records: int
    retry_records: int
    retry_successes: int
    fail_to_pass_rate: float
    failure_types: dict[str, int]
    top_tasks: list[dict[str, Any]]
    recent_items: list[dict[str, Any]]


class CostModelOut(BaseModel):
    model: str
    runs: int
    tokens: int
    estimated_cost_usd: float


class CostMetricsOut(BaseModel):
    total_runs: int
    total_tokens: int
    estimated_cost_usd: float
    by_model: list[CostModelOut]


class EvaluationTotalsOut(BaseModel):
    total: int
    passed: int
    failed: int
    pass_rate: float
    avg_score: float
    total_patch_lines: int
    total_changed_files: int
    tests_passed: int
    failure_types: dict[str, int]
    tokens: int
    total_cost_usd: float
    duration_seconds: float


class EvaluationProfileOut(BaseModel):
    profile: str
    total: int
    passed: int
    failed: int
    pass_rate: float
    avg_score: float
    patch_lines: int
    changed_files: int
    tokens: int
    estimated_cost_usd: float
    duration_seconds: float


class ModelRecommendationOut(BaseModel):
    category: str
    profile: str
    reason: str
    score: float


class EvaluationTaskRowOut(BaseModel):
    run_id: int
    task_id: str
    harness_run_id: str | None = None
    profile: str
    attempt_index: int
    status: str
    score: int
    patch_lines: int
    changed_files: int
    tests_passed: bool
    failure_type: str
    tokens: int
    estimated_cost_usd: float
    duration_seconds: float | None = None
    report_link: str | None = None


class RetryComparisonOut(BaseModel):
    task_id: str
    first_attempt_status: str
    retry_status: str
    fail_to_pass: bool
    retry_cost: float
    retry_patch_lines: int
    failure_type_changed: bool
    first_failure_type: str
    retry_failure_type: str


class EvaluationSummaryOut(BaseModel):
    summary: EvaluationTotalsOut
    profiles: list[EvaluationProfileOut]
    recommendations: list[ModelRecommendationOut] = Field(default_factory=list)
    tasks: list[EvaluationTaskRowOut]
    retry_comparisons: list[RetryComparisonOut]


class EvaluationHistoryRunOut(BaseModel):
    run_id: int
    status: str
    model: str
    model_provider: str | None = None
    harness_run_id: str | None = None
    failure_type: str | None = None
    error_message: str | None = None
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    created_at: datetime


class EvaluationHistoryItemOut(BaseModel):
    evaluation_id: int | None = None
    task_id: int
    name: str
    description: str
    created_at: datetime
    status: str
    run_count: int
    model_count: int
    passed: int
    failed: int
    pending: int
    running: int
    pass_rate: float
    total_tokens: int
    estimated_cost_usd: float
    latest_run_id: int | None = None
    best_run_id: int | None = None
    latest_failure_type: str | None = None
    latest_error_message: str | None = None
    failure_types: dict[str, int] = Field(default_factory=dict)
    models: list[str] = Field(default_factory=list)
    runs: list[EvaluationHistoryRunOut] = Field(default_factory=list)


class EvaluationMatrixCellOut(BaseModel):
    run_id: int
    status: str
    model: str
    model_provider: str | None = None
    failure_type: str | None = None
    error_message: str | None = None
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    duration_seconds: float | None = None
    artifacts_dir: str | None = None


class EvaluationMatrixTaskOut(BaseModel):
    task_id: int
    task_name: str
    task_description: str
    models: list[EvaluationMatrixCellOut] = Field(default_factory=list)


class EvaluationMatrixOut(BaseModel):
    evaluation_id: int
    name: str
    goal: str
    status: str
    task_count: int
    model_count: int
    run_count: int
    passed: int
    failed: int
    pending: int
    running: int
    pass_rate: float
    total_tokens: int
    estimated_cost_usd: float
    created_at: datetime
    tasks: list[EvaluationMatrixTaskOut] = Field(default_factory=list)
