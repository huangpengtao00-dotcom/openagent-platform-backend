from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .time import utc_now


class RunStatus(StrEnum):
    pending = "pending"
    running = "running"
    passed = "pass"
    failed = "fail"
    timeout = "timeout"
    cancelled = "cancelled"


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    workspaces: Mapped[list["Workspace"]] = relationship(back_populates="tenant")


class Workspace(Base):
    __tablename__ = "workspaces"
    __table_args__ = (UniqueConstraint("tenant_id", "slug", name="uq_workspaces_tenant_slug"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    tenant: Mapped[Tenant] = relationship(back_populates="workspaces")
    tasks: Mapped[list["Task"]] = relationship(back_populates="workspace")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspaces.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    harness_task_path: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    workspace: Mapped[Workspace | None] = relationship(back_populates="tasks")
    runs: Mapped[list["Run"]] = relationship(back_populates="task")
    evaluations: Mapped[list["Evaluation"]] = relationship(back_populates="task")


class Evaluation(Base):
    __tablename__ = "evaluations"
    __table_args__ = (UniqueConstraint("workspace_id", "idempotency_key", name="uq_evaluations_workspace_idempotency"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspaces.id"), nullable=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    goal: Mapped[str] = mapped_column(Text, default="")
    idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    task: Mapped[Task] = relationship(back_populates="evaluations")


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (UniqueConstraint("user_id", "idempotency_key", name="uq_runs_user_idempotency"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(120), default="anonymous")
    idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=RunStatus.pending.value)
    mode: Mapped[str] = mapped_column(String(20), default="local")
    model: Mapped[str] = mapped_column(String(120), default="scripted")
    model_provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    base_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    wire_api: Mapped[str | None] = mapped_column(String(40), nullable=True)
    reasoning_effort: Mapped[str | None] = mapped_column(String(40), nullable=True)
    disable_response_storage: Mapped[bool] = mapped_column(default=False)
    allow_llm_calls: Mapped[bool] = mapped_column(default=False)
    timeout_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_run_id: Mapped[int | None] = mapped_column(ForeignKey("runs.id"), nullable=True)
    failure_context_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    harness_run_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    artifacts_dir: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    task: Mapped[Task] = relationship(back_populates="runs")
    usage: Mapped["Usage | None"] = relationship(back_populates="run", uselist=False)


class Usage(Base):
    __tablename__ = "usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"), unique=True, nullable=False)
    model: Mapped[str] = mapped_column(String(120), default="")
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    run: Mapped[Run] = relationship(back_populates="usage")
