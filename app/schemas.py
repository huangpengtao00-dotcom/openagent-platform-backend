from __future__ import annotations

from datetime import datetime
from typing import Literal

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


class TaskOut(BaseModel):
    task_id: int
    name: str
    description: str
    harness_task_path: str
    created_at: datetime

    model_config = {"from_attributes": True}


class RunCreate(BaseModel):
    task_id: int
    mode: Literal["local", "api"] = "local"
    model: str = "scripted"
    allow_llm_calls: bool = False
    timeout_seconds: int | None = Field(default=None, ge=1, le=3600)

    model_config = {"extra": "forbid"}


class RetryRunCreate(BaseModel):
    allow_llm_calls: bool = False
    timeout_seconds: int | None = Field(default=None, ge=1, le=3600)

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
    status: str
    mode: str
    model: str
    timeout_seconds: int | None = None
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


class SourceFileOut(BaseModel):
    path: str
    content: str


class RunSourceOut(BaseModel):
    run_id: int
    harness_run_id: str | None = None
    artifacts_dir: str | None = None
    files: list[SourceFileOut]


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
    tasks: list[EvaluationTaskRowOut]
    retry_comparisons: list[RetryComparisonOut]
