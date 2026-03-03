"""Sprint 14: add extended model_data fields for Phase 2-E prerequisites.

Revision ID: 011
Revises: 010
Create Date: 2026-03-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "011"
down_revision: str | None = "010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    jsonb = postgresql.JSONB(astext_type=sa.Text())
    op.add_column("model_data", sa.Column("final_demand_f_json", jsonb, nullable=True))
    op.add_column("model_data", sa.Column("imports_vector_json", jsonb, nullable=True))
    op.add_column(
        "model_data",
        sa.Column("compensation_of_employees_json", jsonb, nullable=True),
    )
    op.add_column(
        "model_data",
        sa.Column("gross_operating_surplus_json", jsonb, nullable=True),
    )
    op.add_column(
        "model_data",
        sa.Column("taxes_less_subsidies_json", jsonb, nullable=True),
    )
    op.add_column(
        "model_data",
        sa.Column("household_consumption_shares_json", jsonb, nullable=True),
    )
    op.add_column("model_data", sa.Column("deflator_series_json", jsonb, nullable=True))


def downgrade() -> None:
    op.drop_column("model_data", "deflator_series_json")
    op.drop_column("model_data", "household_consumption_shares_json")
    op.drop_column("model_data", "taxes_less_subsidies_json")
    op.drop_column("model_data", "gross_operating_surplus_json")
    op.drop_column("model_data", "compensation_of_employees_json")
    op.drop_column("model_data", "imports_vector_json")
    op.drop_column("model_data", "final_demand_f_json")
