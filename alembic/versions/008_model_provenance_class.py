"""Sprint 7: add provenance_class to model_versions

Revision ID: 008
Revises: 007
Create Date: 2026-03-02
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "model_versions",
        sa.Column(
            "provenance_class",
            sa.String(30),
            nullable=False,
            server_default=sa.text("'unknown'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("model_versions", "provenance_class")
