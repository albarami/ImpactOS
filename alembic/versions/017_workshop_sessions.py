"""Add workshop_sessions table for live workshop dashboard.

Revision ID: 017_workshop_sessions
Revises: 016_portfolio_optimizations
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "017_workshop_sessions"
down_revision = "016_portfolio_optimizations"
branch_labels = None
depends_on = None

FlexUUID = postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite")
FlexJSON = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "workshop_sessions",
        sa.Column("session_id", FlexUUID, primary_key=True),
        sa.Column(
            "workspace_id",
            FlexUUID,
            sa.ForeignKey(
                "workspaces.workspace_id",
                name="fk_workshop_sessions_workspace_id",
            ),
            nullable=False,
        ),
        sa.Column(
            "baseline_run_id",
            FlexUUID,
            sa.ForeignKey(
                "run_snapshots.run_id",
                name="fk_workshop_sessions_baseline_run_id",
            ),
            nullable=False,
        ),
        sa.Column("base_shocks_json", FlexJSON, nullable=False),
        sa.Column("slider_config_json", FlexJSON, nullable=False),
        sa.Column("transformed_shocks_json", FlexJSON, nullable=False),
        sa.Column("config_hash", sa.String(100), nullable=False),
        sa.Column(
            "committed_run_id",
            FlexUUID,
            sa.ForeignKey(
                "run_snapshots.run_id",
                name="fk_workshop_sessions_committed_run_id",
            ),
            nullable=True,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("preview_summary_json", FlexJSON, nullable=True),
        sa.Column("created_by", FlexUUID, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'committed', 'archived')",
            name="ck_workshop_sessions_status",
        ),
    )

    op.create_unique_constraint(
        "uq_workshop_sessions_ws_config",
        "workshop_sessions",
        ["workspace_id", "config_hash"],
    )

    op.create_index(
        "ix_workshop_sessions_ws_updated",
        "workshop_sessions",
        ["workspace_id", sa.text("updated_at DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_workshop_sessions_ws_updated",
        table_name="workshop_sessions",
    )
    op.drop_constraint(
        "uq_workshop_sessions_ws_config",
        "workshop_sessions",
        type_="unique",
    )
    op.drop_table("workshop_sessions")
