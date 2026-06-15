from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TaskCreate(BaseModel):
    name: str
    description: str = ""
    harness_task_path: str


class TaskOut(BaseModel):
    task_id: int
    name: str
    description: str
    harness_task_path: str
    created_at: datetime

    model_config = {"from_attributes": True}


class RunCreate(BaseModel):
    task_id: int
    mode: str = "local"
    model: str = "scripted"
    allow_llm_calls: bool = False
    timeout_seconds: int | None = Field(default=None, ge=1, le=3600)


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
    artifacts: dict[str, str] = {}

    model_config = {"from_attributes": True}


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
