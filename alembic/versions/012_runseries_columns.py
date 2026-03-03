"""Add RunSeries columns to result_sets.

Revision ID: 012_runseries_columns
Revises: 011
"""
from alembic import op
import sqlalchemy as sa

revision = "012_runseries_columns"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("result_sets", sa.Column("year", sa.Integer(), nullable=True))
    op.add_column("result_sets", sa.Column("series_kind", sa.String(20), nullable=True))
    op.add_column("result_sets", sa.Column("baseline_run_id", sa.dialects.postgresql.UUID(), nullable=True))

    # CHECK constraints
    op.execute(
        "ALTER TABLE result_sets ADD CONSTRAINT chk_series_kind "
        "CHECK (series_kind IN ('annual', 'peak', 'delta') OR series_kind IS NULL)"
    )
    op.execute(
        "ALTER TABLE result_sets ADD CONSTRAINT chk_year_required "
        "CHECK ((series_kind IS NULL AND year IS NULL) "
        "OR (series_kind IS NOT NULL AND year IS NOT NULL))"
    )
    op.execute(
        "ALTER TABLE result_sets ADD CONSTRAINT chk_baseline_delta "
        "CHECK ((series_kind = 'delta' AND baseline_run_id IS NOT NULL) "
        "OR (series_kind != 'delta' AND baseline_run_id IS NULL) "
        "OR (series_kind IS NULL AND baseline_run_id IS NULL))"
    )

    # Partial unique indexes
    op.create_index("uq_resultset_legacy", "result_sets",
                    ["run_id", "metric_type"],
                    unique=True, postgresql_where=sa.text("series_kind IS NULL"))
    op.create_index("uq_resultset_annual", "result_sets",
                    ["run_id", "metric_type", "year"],
                    unique=True, postgresql_where=sa.text("series_kind = 'annual'"))
    op.create_index("uq_resultset_peak", "result_sets",
                    ["run_id", "metric_type"],
                    unique=True, postgresql_where=sa.text("series_kind = 'peak'"))
    op.create_index("uq_resultset_delta", "result_sets",
                    ["run_id", "metric_type", "year", "baseline_run_id"],
                    unique=True, postgresql_where=sa.text("series_kind = 'delta'"))


def downgrade() -> None:
    op.drop_index("uq_resultset_delta", "result_sets")
    op.drop_index("uq_resultset_peak", "result_sets")
    op.drop_index("uq_resultset_annual", "result_sets")
    op.drop_index("uq_resultset_legacy", "result_sets")
    op.execute("ALTER TABLE result_sets DROP CONSTRAINT IF EXISTS chk_baseline_delta")
    op.execute("ALTER TABLE result_sets DROP CONSTRAINT IF EXISTS chk_year_required")
    op.execute("ALTER TABLE result_sets DROP CONSTRAINT IF EXISTS chk_series_kind")
    op.drop_column("result_sets", "baseline_run_id")
    op.drop_column("result_sets", "series_kind")
    op.drop_column("result_sets", "year")
