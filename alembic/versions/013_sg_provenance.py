"""Add sg_provenance JSON column to model_versions.

Revision ID: 013_sg_provenance
Revises: 012_runseries_columns
"""
import sqlalchemy as sa

from alembic import op

revision = "013_sg_provenance"
down_revision = "012_runseries_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "model_versions",
        sa.Column("sg_provenance", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("model_versions", "sg_provenance")
