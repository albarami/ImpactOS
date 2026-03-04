"""Add sg_provenance JSON column to model_versions.

Revision ID: 013_sg_provenance
Revises: 012_runseries_columns
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "013_sg_provenance"
down_revision = "012_runseries_columns"
branch_labels = None
depends_on = None

# Match ORM FlexJSON: JSONB on Postgres, JSON on SQLite
FlexJSON = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.add_column(
        "model_versions",
        sa.Column("sg_provenance", FlexJSON, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("model_versions", "sg_provenance")
