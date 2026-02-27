"""Workforce/Saudization satellite — 4 new tables.

Revision ID: 003
Revises: 002
Create Date: 2026-02-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- Employment Coefficients (versioned, same pattern as constraint_sets) --
    op.create_table(
        "employment_coefficients",
        sa.Column("row_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("employment_coefficients_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("model_version_id", UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("output_unit", sa.String(20), nullable=False),
        sa.Column("base_year", sa.Integer, nullable=False),
        sa.Column("coefficients", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "employment_coefficients_id", "version",
            name="uq_employment_coefficients_version",
        ),
    )

    # -- Sector-Occupation Bridge (versioned) --
    op.create_table(
        "sector_occupation_bridges",
        sa.Column("row_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("bridge_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("model_version_id", UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("entries", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("bridge_id", "version", name="uq_bridge_version"),
    )

    # -- Saudization Rules (versioned, no model_version_id) --
    op.create_table(
        "saudization_rules",
        sa.Column("row_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("rules_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("tier_assignments", JSONB, nullable=False),
        sa.Column("sector_targets", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("rules_id", "version", name="uq_rules_version"),
    )

    # -- Workforce Results (immutable, idempotent) --
    op.create_table(
        "workforce_results",
        sa.Column("workforce_result_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("run_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("employment_coefficients_id", UUID(as_uuid=True), nullable=False),
        sa.Column("employment_coefficients_version", sa.Integer, nullable=False),
        sa.Column("bridge_id", UUID(as_uuid=True), nullable=True),
        sa.Column("bridge_version", sa.Integer, nullable=True),
        sa.Column("rules_id", UUID(as_uuid=True), nullable=True),
        sa.Column("rules_version", sa.Integer, nullable=True),
        sa.Column("results", JSONB, nullable=False),
        sa.Column("confidence_summary", JSONB, nullable=False),
        sa.Column("data_quality_notes", JSONB, nullable=False),
        sa.Column("satellite_coefficients_hash", sa.String(100), nullable=False),
        sa.Column("delta_x_source", sa.String(20), nullable=False),
        sa.Column("feasibility_result_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "run_id", "employment_coefficients_id",
            "employment_coefficients_version", "delta_x_source",
            name="uq_workforce_result_idempotent",
        ),
    )


def downgrade() -> None:
    op.drop_table("workforce_results")
    op.drop_table("saudization_rules")
    op.drop_table("sector_occupation_bridges")
    op.drop_table("employment_coefficients")
