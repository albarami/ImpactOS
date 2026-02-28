"""Feasibility layer — constraint_sets + feasibility_results tables.

Revision ID: 002
Revises: 001
Create Date: 2026-02-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- Constraint Sets (versioned, same pattern as scenario_specs) --
    op.create_table(
        "constraint_sets",
        sa.Column("row_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("constraint_set_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("model_version_id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("constraints", JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", UUID(as_uuid=True), nullable=True),
        sa.UniqueConstraint("constraint_set_id", "version", name="uq_constraint_set_version"),
    )

    # -- Feasibility Results (immutable, supplementary analysis) --
    op.create_table(
        "feasibility_results",
        sa.Column("feasibility_result_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("unconstrained_run_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("constraint_set_id", UUID(as_uuid=True), nullable=False),
        sa.Column("constraint_set_version", sa.Integer, nullable=False),
        sa.Column("feasible_delta_x", JSONB, nullable=False),
        sa.Column("unconstrained_delta_x", JSONB, nullable=False),
        sa.Column("gap_vs_unconstrained", JSONB, nullable=False),
        sa.Column("total_feasible_output", sa.Float, nullable=False),
        sa.Column("total_unconstrained_output", sa.Float, nullable=False),
        sa.Column("total_gap", sa.Float, nullable=False),
        sa.Column("binding_constraints", JSONB, nullable=False),
        sa.Column("slack_constraint_ids", JSONB, nullable=False),
        sa.Column("enabler_recommendations", JSONB, nullable=False),
        sa.Column("confidence_summary", JSONB, nullable=False),
        sa.Column("satellite_coefficients_hash", sa.String(100), nullable=False),
        sa.Column("satellite_coefficients_snapshot", JSONB, nullable=False),
        sa.Column("solver_type", sa.String(50), nullable=False),
        sa.Column("solver_version", sa.String(50), nullable=False),
        sa.Column("lp_status", sa.String(50), nullable=True),
        sa.Column("fallback_used", sa.Boolean, server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("feasibility_results")
    op.drop_table("constraint_sets")
