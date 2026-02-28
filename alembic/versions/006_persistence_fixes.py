"""S0-1 Persistence fixes — workspace scoping + batch status alignment.

Adds workspace_id to run_snapshots, result_sets, and batches tables.
Adds status column to batches table (was missing from migration 001).

Revision ID: 006
Revises: 005
Create Date: 2026-02-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # batches: add status + workspace_id (alignment with ORM)
    op.add_column(
        "batches",
        sa.Column("status", sa.String(50), server_default="COMPLETED", nullable=False),
    )
    op.add_column(
        "batches",
        sa.Column("workspace_id", sa.Uuid, nullable=True),
    )

    # run_snapshots: add workspace_id (Amendment 3 — workspace scoping)
    op.add_column(
        "run_snapshots",
        sa.Column("workspace_id", sa.Uuid, nullable=True, index=True),
    )

    # result_sets: add workspace_id (Amendment 3 — workspace scoping)
    op.add_column(
        "result_sets",
        sa.Column("workspace_id", sa.Uuid, nullable=True, index=True),
    )


def downgrade() -> None:
    op.drop_column("result_sets", "workspace_id")
    op.drop_column("run_snapshots", "workspace_id")
    op.drop_column("batches", "workspace_id")
    op.drop_column("batches", "status")
