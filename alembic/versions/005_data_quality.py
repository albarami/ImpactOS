"""Data Quality Automation — 1 new table (MVP-13).

Revision ID: 005
Revises: 004
Create Date: 2026-02-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "run_quality_summaries",
        sa.Column("row_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("summary_id", sa.Uuid, unique=True, nullable=False, index=True),
        sa.Column("run_id", sa.Uuid, nullable=False, index=True),
        sa.Column("workspace_id", sa.Uuid, nullable=False, index=True),
        sa.Column("overall_run_score", sa.Float, nullable=False),
        sa.Column("overall_run_grade", sa.String(5), nullable=False),
        sa.Column("coverage_pct", sa.Float, nullable=False),
        sa.Column("mapping_coverage_pct", sa.Float, nullable=True),
        sa.Column("publication_gate_pass", sa.Boolean, nullable=False),
        sa.Column("publication_gate_mode", sa.String(30), nullable=False),
        sa.Column(
            "summary_version", sa.String(20), nullable=False, server_default="1.0.0",
        ),
        sa.Column("summary_hash", sa.String(128), nullable=False, server_default=""),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", name="uq_run_quality_summary_run_id"),
    )


def downgrade() -> None:
    op.drop_table("run_quality_summaries")
