"""Chat repositories — session and message persistence (Sprint 25)."""

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.tables import ChatMessageRow, ChatSessionRow
from src.models.common import utc_now


class ChatSessionRepository:
    """CRUD operations for chat sessions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        session_id: UUID,
        workspace_id: UUID,
        title: str | None = None,
    ) -> ChatSessionRow:
        now = utc_now()
        row = ChatSessionRow(
            session_id=session_id,
            workspace_id=workspace_id,
            title=title,
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(
        self, session_id: UUID, workspace_id: UUID,
    ) -> ChatSessionRow | None:
        result = await self._session.execute(
            select(ChatSessionRow).where(
                ChatSessionRow.session_id == session_id,
                ChatSessionRow.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_workspace(
        self,
        workspace_id: UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ChatSessionRow]:
        result = await self._session.execute(
            select(ChatSessionRow)
            .where(ChatSessionRow.workspace_id == workspace_id)
            .order_by(ChatSessionRow.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def update_title(
        self, session_id: UUID, workspace_id: UUID, title: str,
    ) -> None:
        await self._session.execute(
            update(ChatSessionRow)
            .where(
                ChatSessionRow.session_id == session_id,
                ChatSessionRow.workspace_id == workspace_id,
            )
            .values(title=title, updated_at=utc_now())
        )
        await self._session.flush()

    async def touch(self, session_id: UUID, workspace_id: UUID) -> None:
        """Update updated_at timestamp."""
        await self._session.execute(
            update(ChatSessionRow)
            .where(
                ChatSessionRow.session_id == session_id,
                ChatSessionRow.workspace_id == workspace_id,
            )
            .values(updated_at=utc_now())
        )
        await self._session.flush()


class ChatMessageRepository:
    """CRUD operations for chat messages."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        message_id: UUID,
        session_id: UUID,
        role: str,
        content: str,
        tool_calls: list | None = None,
        tool_results: list | None = None,
        trace_metadata: dict | None = None,
        prompt_version: str | None = None,
        model_provider: str | None = None,
        model_id: str | None = None,
        token_usage: dict | None = None,
    ) -> ChatMessageRow:
        row = ChatMessageRow(
            message_id=message_id,
            session_id=session_id,
            role=role,
            content=content,
            tool_calls=tool_calls,
            tool_results=tool_results,
            trace_metadata=trace_metadata,
            prompt_version=prompt_version,
            model_provider=model_provider,
            model_id=model_id,
            token_usage=token_usage,
            created_at=utc_now(),
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def list_for_session(
        self, session_id: UUID,
    ) -> list[ChatMessageRow]:
        result = await self._session.execute(
            select(ChatMessageRow)
            .where(ChatMessageRow.session_id == session_id)
            .order_by(ChatMessageRow.created_at.asc())
        )
        return list(result.scalars().all())
