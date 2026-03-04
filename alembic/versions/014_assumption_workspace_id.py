"""Add workspace_id column to assumptions table.

Revision ID: 014_assumption_workspace_id
Revises: 013_sg_provenance
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "014_assumption_workspace_id"
down_revision = "013_sg_provenance"
branch_labels = None
depends_on = None

# UUID type: native Postgres UUID, String(36) on SQLite
FlexUUID = postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite")


def upgrade() -> None:
    op.add_column(
        "assumptions",
        sa.Column("workspace_id", FlexUUID, nullable=True),
    )
    op.create_foreign_key(
        "fk_assumptions_workspace_id",
        "assumptions",
        "workspaces",
        ["workspace_id"],
        ["workspace_id"],
    )
    op.create_index(
        "ix_assumptions_workspace_id",
        "assumptions",
        ["workspace_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_assumptions_workspace_id", table_name="assumptions")
    op.drop_constraint("fk_assumptions_workspace_id", "assumptions", type_="foreignkey")
    op.drop_column("assumptions", "workspace_id")
