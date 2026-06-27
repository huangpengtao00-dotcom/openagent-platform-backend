from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0003_tenants_workspaces"
down_revision = "0002_failure_context_retry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("slug", sa.String(length=120), nullable=False, unique=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "workspaces",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_workspaces_tenant_slug"),
    )
    op.add_column("tasks", sa.Column("workspace_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("tasks", "workspace_id")
    op.drop_table("workspaces")
    op.drop_table("tenants")
