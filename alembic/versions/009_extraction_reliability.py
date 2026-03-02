"""Sprint 8: extraction reliability — failure metadata + idempotency

Revision ID: 009
Revises: 008
Create Date: 2026-03-02
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_extraction_jobs_workspace_id",
        "extraction_jobs",
        ["workspace_id"],
    )
    op.add_column(
        "extraction_jobs",
        sa.Column(
            "error_code", sa.String(100), nullable=True,
        ),
    )
    op.add_column(
        "extraction_jobs",
        sa.Column(
            "provider_name", sa.String(100), nullable=True,
        ),
    )
    op.add_column(
        "extraction_jobs",
        sa.Column(
            "fallback_provider_name", sa.String(100), nullable=True,
        ),
    )
    op.add_column(
        "extraction_jobs",
        sa.Column(
            "attempt_count", sa.Integer(),
            nullable=False, server_default=sa.text("1"),
        ),
    )
    op.add_column(
        "extraction_jobs",
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "extraction_jobs",
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_index("ix_extraction_jobs_workspace_id", "extraction_jobs")
    op.drop_column("extraction_jobs", "completed_at")
    op.drop_column("extraction_jobs", "started_at")
    op.drop_column("extraction_jobs", "attempt_count")
    op.drop_column("extraction_jobs", "fallback_provider_name")
    op.drop_column("extraction_jobs", "provider_name")
    op.drop_column("extraction_jobs", "error_code")
