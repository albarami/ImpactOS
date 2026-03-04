"""Add portfolio_optimizations table for portfolio optimization persistence.

Revision ID: 016_portfolio_optimizations
Revises: 015_path_analyses
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "016_portfolio_optimizations"
down_revision = "015_path_analyses"
branch_labels = None
depends_on = None

# Portable type variants
FlexUUID = postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite")
FlexJSON = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "portfolio_optimizations",
        sa.Column("portfolio_id", FlexUUID, primary_key=True),
        sa.Column(
            "workspace_id",
            FlexUUID,
            sa.ForeignKey(
                "workspaces.workspace_id",
                name="fk_portfolio_optimizations_workspace_id",
            ),
            nullable=False,
        ),
        sa.Column("model_version_id", FlexUUID, nullable=False),
        sa.Column("optimization_version", sa.String(20), nullable=False),
        sa.Column("config_json", FlexJSON, nullable=False),
        sa.Column("config_hash", sa.String(71), nullable=False),
        sa.Column("objective_metric", sa.String(50), nullable=False),
        sa.Column("cost_metric", sa.String(50), nullable=False),
        sa.Column("budget", sa.Float(), nullable=False),
        sa.Column("min_selected", sa.Integer(), nullable=False),
        sa.Column("max_selected", sa.Integer(), nullable=True),
        sa.Column("candidate_run_ids_json", FlexJSON, nullable=False),
        sa.Column("selected_run_ids_json", FlexJSON, nullable=False),
        sa.Column("result_json", FlexJSON, nullable=False),
        sa.Column("result_checksum", sa.String(71), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # Unique constraint: one optimization per (workspace, config_hash)
    op.create_unique_constraint(
        "uq_portfolio_optimizations_ws_config",
        "portfolio_optimizations",
        ["workspace_id", "config_hash"],
    )

    # Composite index: workspace + created_at DESC
    op.create_index(
        "ix_portfolio_optimizations_ws_created",
        "portfolio_optimizations",
        ["workspace_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    # Drop index
    op.drop_index(
        "ix_portfolio_optimizations_ws_created",
        table_name="portfolio_optimizations",
    )

    # Drop unique constraint
    op.drop_constraint(
        "uq_portfolio_optimizations_ws_config",
        "portfolio_optimizations",
        type_="unique",
    )

    # Drop table
    op.drop_table("portfolio_optimizations")
