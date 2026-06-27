from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0004_evaluations"
down_revision = "0003_tenants_workspaces"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evaluations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id"), nullable=True),
        sa.Column("task_id", sa.Integer(), sa.ForeignKey("tasks.id"), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("workspace_id", "idempotency_key", name="uq_evaluations_workspace_idempotency"),
    )


def downgrade() -> None:
    op.drop_table("evaluations")
