"""Add path_analyses table for SPA + chokepoint analytics persistence.

Revision ID: 015_path_analyses
Revises: 014_assumption_workspace_id
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "015_path_analyses"
down_revision = "014_assumption_workspace_id"
branch_labels = None
depends_on = None

# Portable type variants
FlexUUID = postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite")
FlexJSON = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "path_analyses",
        sa.Column("analysis_id", FlexUUID, primary_key=True),
        sa.Column(
            "run_id",
            FlexUUID,
            sa.ForeignKey("run_snapshots.run_id", name="fk_path_analyses_run_id"),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            FlexUUID,
            sa.ForeignKey("workspaces.workspace_id", name="fk_path_analyses_workspace_id"),
            nullable=False,
        ),
        sa.Column("analysis_version", sa.String(20), nullable=False),
        sa.Column("config_json", FlexJSON, nullable=False),
        sa.Column("config_hash", sa.String(100), nullable=False),
        sa.Column("max_depth", sa.Integer(), nullable=False),
        sa.Column("top_k", sa.Integer(), nullable=False),
        sa.Column("top_paths_json", FlexJSON, nullable=False),
        sa.Column("chokepoints_json", FlexJSON, nullable=False),
        sa.Column("depth_contributions_json", FlexJSON, nullable=False),
        sa.Column("coverage_ratio", sa.Float(), nullable=False),
        sa.Column("result_checksum", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # Unique constraint: one analysis per (run, config_hash)
    op.create_unique_constraint(
        "uq_path_analyses_run_config",
        "path_analyses",
        ["run_id", "config_hash"],
    )

    # Indexes
    op.create_index(
        "ix_path_analyses_workspace_id",
        "path_analyses",
        ["workspace_id"],
    )
    op.create_index(
        "ix_path_analyses_run_created",
        "path_analyses",
        ["run_id", sa.text("created_at DESC")],
    )

    # CHECK constraint: coverage_ratio BETWEEN 0 AND 1 — Postgres only
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER TABLE path_analyses ADD CONSTRAINT ck_path_analyses_coverage "
            "CHECK (coverage_ratio BETWEEN 0 AND 1)"
        )


def downgrade() -> None:
    # Drop CHECK constraint (Postgres only)
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE path_analyses DROP CONSTRAINT IF EXISTS ck_path_analyses_coverage")

    # Drop indexes
    op.drop_index("ix_path_analyses_run_created", table_name="path_analyses")
    op.drop_index("ix_path_analyses_workspace_id", table_name="path_analyses")

    # Drop unique constraint
    op.drop_constraint("uq_path_analyses_run_config", "path_analyses", type_="unique")

    # Drop table
    op.drop_table("path_analyses")
