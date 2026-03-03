"""Sprint 10: workspace memberships for authN/authZ rollout

Revision ID: 010
Revises: 009
Create Date: 2026-03-03
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workspace_memberships",
        sa.Column(
            "workspace_id", sa.Uuid(),
            sa.ForeignKey("workspaces.workspace_id"),
            nullable=False,
        ),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(50), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
        ),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.PrimaryKeyConstraint("workspace_id", "user_id"),
    )
    op.create_index(
        "ix_workspace_memberships_user_id",
        "workspace_memberships",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_workspace_memberships_user_id", "workspace_memberships",
    )
    op.drop_table("workspace_memberships")
