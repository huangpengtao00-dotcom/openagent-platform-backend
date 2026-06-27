from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("harness_task_path", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("user_id", sa.String(length=120), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("model_provider", sa.String(length=80), nullable=True),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column("wire_api", sa.String(length=40), nullable=True),
        sa.Column("reasoning_effort", sa.String(length=40), nullable=True),
        sa.Column("disable_response_storage", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("allow_llm_calls", sa.Boolean(), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=True),
        sa.Column("harness_run_id", sa.String(length=200), nullable=True),
        sa.Column("artifacts_dir", sa.Text(), nullable=True),
        sa.Column("failure_type", sa.String(length=120), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_runs_user_idempotency"),
    )
    op.create_table(
        "usage",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("runs.id"), nullable=False, unique=True),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False),
        sa.Column("completion_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("usage")
    op.drop_table("runs")
    op.drop_table("tasks")
