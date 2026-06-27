from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0002_failure_context_retry"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("source_run_id", sa.Integer(), nullable=True))
    op.add_column("runs", sa.Column("failure_context_path", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "failure_context_path")
    op.drop_column("runs", "source_run_id")
