"""020: Chat sessions and messages tables (Sprint 25).

Revision ID: 020_chat_sessions_messages
Revises: 019_run_snapshot_scenario_link
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "020_chat_sessions_messages"
down_revision = "019_run_snapshot_scenario_link"
branch_labels = None
depends_on = None

FlexUUID = postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite")
FlexJSON = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "chat_sessions",
        sa.Column("session_id", FlexUUID, primary_key=True),
        sa.Column(
            "workspace_id",
            FlexUUID,
            sa.ForeignKey("workspaces.workspace_id"),
            nullable=False,
        ),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_chat_sessions_workspace",
        "chat_sessions",
        ["workspace_id", "updated_at"],
    )

    op.create_table(
        "chat_messages",
        sa.Column("message_id", FlexUUID, primary_key=True),
        sa.Column(
            "session_id",
            FlexUUID,
            sa.ForeignKey("chat_sessions.session_id"),
            nullable=False,
        ),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tool_calls", FlexJSON, nullable=True),
        sa.Column("tool_results", FlexJSON, nullable=True),
        sa.Column("trace_metadata", FlexJSON, nullable=True),
        sa.Column("prompt_version", sa.String(50), nullable=True),
        sa.Column("model_provider", sa.String(50), nullable=True),
        sa.Column("model_id", sa.String(100), nullable=True),
        sa.Column("token_usage", FlexJSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_chat_messages_session",
        "chat_messages",
        ["session_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_chat_messages_session", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_index("ix_chat_sessions_workspace", table_name="chat_sessions")
    op.drop_table("chat_sessions")
