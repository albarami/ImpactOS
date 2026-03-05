"""019: Add scenario_spec_id + scenario_spec_version to run_snapshots.

Sprint 24 carryover I-2: link runs to their source scenario
so variance bridge can detect PHASING/IMPORT_SHARE/FEASIBILITY drivers.

Revision ID: 019_run_snapshot_scenario_link
Revises: 018_variance_bridge_analyses
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "019_run_snapshot_scenario_link"
down_revision = "018_variance_bridge_analyses"
branch_labels = None
depends_on = None

FlexUUID = postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite")


def upgrade() -> None:
    op.add_column(
        "run_snapshots",
        sa.Column("scenario_spec_id", FlexUUID, nullable=True),
    )
    op.add_column(
        "run_snapshots",
        sa.Column("scenario_spec_version", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_run_snapshots_scenario_spec_id",
        "run_snapshots",
        ["scenario_spec_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_run_snapshots_scenario_spec_id",
        table_name="run_snapshots",
    )
    op.drop_column("run_snapshots", "scenario_spec_version")
    op.drop_column("run_snapshots", "scenario_spec_id")
