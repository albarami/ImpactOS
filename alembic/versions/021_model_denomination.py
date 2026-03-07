"""Add model_denomination to model_versions and run_snapshots.

Revision ID: 021_model_denomination
Revises: 020_chat_sessions_messages
Create Date: 2026-03-07
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "021_model_denomination"
down_revision = "020_chat_sessions_messages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "model_versions",
        sa.Column("model_denomination", sa.String(30), nullable=False, server_default="UNKNOWN"),
    )
    op.add_column(
        "run_snapshots",
        sa.Column("model_denomination", sa.String(30), nullable=False, server_default="UNKNOWN"),
    )


def downgrade() -> None:
    op.drop_column("run_snapshots", "model_denomination")
    op.drop_column("model_versions", "model_denomination")
