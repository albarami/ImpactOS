"""Sprint 5: export artifact refs + scenario lock persistence

Revision ID: 007
Revises: fa33e2cd9dda
Create Date: 2026-03-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "007"
down_revision: Union[str, None] = "fa33e2cd9dda"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FlexJSON = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.add_column(
        "exports",
        sa.Column("artifact_refs_json", FlexJSON, nullable=True),
    )
    op.add_column(
        "scenario_specs",
        sa.Column(
            "is_locked",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("scenario_specs", "is_locked")
    op.drop_column("exports", "artifact_refs_json")
