"""Knowledge Flywheel libraries — 5 new tables.

Revision ID: 004
Revises: 003
Create Date: 2026-02-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mapping_library_entries",
        sa.Column("row_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("entry_id", sa.Uuid, unique=True, nullable=False, index=True),
        sa.Column("workspace_id", sa.Uuid, nullable=False, index=True),
        sa.Column("pattern", sa.Text, nullable=False),
        sa.Column("sector_code", sa.String(100), nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("usage_count", sa.Integer, default=0, nullable=False),
        sa.Column("source_engagement_id", sa.Uuid, nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tags", sa.JSON, nullable=False),
        sa.Column("created_by", sa.Uuid, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
    )

    op.create_table(
        "mapping_library_versions",
        sa.Column("row_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("library_version_id", sa.Uuid, nullable=False, index=True),
        sa.Column("workspace_id", sa.Uuid, nullable=False, index=True),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("entry_ids", sa.JSON, nullable=False),
        sa.Column("entry_count", sa.Integer, default=0, nullable=False),
        sa.Column("published_by", sa.Uuid, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "workspace_id", "version",
            name="uq_mapping_library_ws_version",
        ),
    )

    op.create_table(
        "assumption_library_entries",
        sa.Column("row_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("entry_id", sa.Uuid, unique=True, nullable=False, index=True),
        sa.Column("workspace_id", sa.Uuid, nullable=False, index=True),
        sa.Column("assumption_type", sa.String(50), nullable=False),
        sa.Column("sector_code", sa.String(100), nullable=False),
        sa.Column("default_value", sa.Float, nullable=False),
        sa.Column("range_low", sa.Float, nullable=False),
        sa.Column("range_high", sa.Float, nullable=False),
        sa.Column("unit", sa.String(50), nullable=False),
        sa.Column("justification", sa.Text, server_default=""),
        sa.Column("source", sa.String(500), server_default=""),
        sa.Column("source_engagement_id", sa.Uuid, nullable=True),
        sa.Column("usage_count", sa.Integer, default=0, nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confidence", sa.String(20), nullable=False),
        sa.Column("created_by", sa.Uuid, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence_refs", sa.JSON, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
    )

    op.create_table(
        "assumption_library_versions",
        sa.Column("row_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("library_version_id", sa.Uuid, nullable=False, index=True),
        sa.Column("workspace_id", sa.Uuid, nullable=False, index=True),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("entry_ids", sa.JSON, nullable=False),
        sa.Column("entry_count", sa.Integer, default=0, nullable=False),
        sa.Column("published_by", sa.Uuid, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "workspace_id", "version",
            name="uq_assumption_library_ws_version",
        ),
    )

    op.create_table(
        "scenario_patterns",
        sa.Column("row_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("pattern_id", sa.Uuid, unique=True, nullable=False, index=True),
        sa.Column("workspace_id", sa.Uuid, nullable=False, index=True),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("description", sa.Text, server_default=""),
        sa.Column("sector_focus", sa.JSON, nullable=False),
        sa.Column("typical_shock_types", sa.JSON, nullable=False),
        sa.Column("typical_assumptions", sa.JSON, nullable=False),
        sa.Column("recommended_sensitivities", sa.JSON, nullable=False),
        sa.Column("recommended_contrarian_angles", sa.JSON, nullable=False),
        sa.Column("source_engagement_ids", sa.JSON, nullable=False),
        sa.Column("usage_count", sa.Integer, default=0, nullable=False),
        sa.Column("tags", sa.JSON, nullable=False),
        sa.Column("created_by", sa.Uuid, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("scenario_patterns")
    op.drop_table("assumption_library_versions")
    op.drop_table("assumption_library_entries")
    op.drop_table("mapping_library_versions")
    op.drop_table("mapping_library_entries")
