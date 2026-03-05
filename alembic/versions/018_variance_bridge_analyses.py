"""018: Variance bridge analyses table (Sprint 23).

Revision ID: 018_variance_bridge_analyses
Revises: 017_workshop_sessions
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "018_variance_bridge_analyses"
down_revision = "017_workshop_sessions"
branch_labels = None
depends_on = None

FlexUUID = postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite")
FlexJSON = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "variance_bridge_analyses",
        sa.Column("analysis_id", FlexUUID, primary_key=True),
        sa.Column(
            "workspace_id",
            FlexUUID,
            sa.ForeignKey("workspaces.workspace_id"),
            nullable=False,
        ),
        sa.Column(
            "run_a_id",
            FlexUUID,
            sa.ForeignKey("run_snapshots.run_id"),
            nullable=False,
        ),
        sa.Column(
            "run_b_id",
            FlexUUID,
            sa.ForeignKey("run_snapshots.run_id"),
            nullable=False,
        ),
        sa.Column("metric_type", sa.String(100), nullable=False),
        sa.Column(
            "analysis_version",
            sa.String(50),
            nullable=False,
            server_default="bridge_v1",
        ),
        sa.Column("config_json", FlexJSON, nullable=False),
        sa.Column("config_hash", sa.String(100), nullable=False),
        sa.Column("result_json", FlexJSON, nullable=False),
        sa.Column("result_checksum", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workspace_id", "config_hash", name="uq_vba_ws_config"),
    )
    op.create_index(
        "ix_variance_bridge_analyses_workspace_id",
        "variance_bridge_analyses",
        ["workspace_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_variance_bridge_analyses_workspace_id",
        table_name="variance_bridge_analyses",
    )
    op.drop_table("variance_bridge_analyses")
