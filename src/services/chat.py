"""Chat service — orchestrates conversation turns (Sprint 25).

Manages session lifecycle, message persistence, and copilot agent invocation.
Enforces confirmation gate at the service level.
"""

from __future__ import annotations

import logging
from uuid import UUID

from src.agents.economist_copilot import CopilotResponse, EconomistCopilot
from src.models.chat import (
    ChatMessageResponse,
    ChatSessionDetail,
    ChatSessionResponse,
    ListSessionsResponse,
    TokenUsage,
    TraceMetadata,
)
from src.models.common import new_uuid7
from src.repositories.chat import ChatMessageRepository, ChatSessionRepository

_logger = logging.getLogger(__name__)


def _session_row_to_response(row) -> ChatSessionResponse:
    """Convert ChatSessionRow to API response."""
    return ChatSessionResponse(
        session_id=str(row.session_id),
        workspace_id=str(row.workspace_id),
        title=row.title,
        created_at=row.created_at.isoformat(),
        updated_at=row.updated_at.isoformat(),
    )


def _message_row_to_response(row) -> ChatMessageResponse:
    """Convert ChatMessageRow to API response."""
    trace = None
    if row.trace_metadata:
        trace = TraceMetadata(**row.trace_metadata)

    token_usage = None
    if row.token_usage:
        token_usage = TokenUsage(**row.token_usage)

    return ChatMessageResponse(
        message_id=str(row.message_id),
        role=row.role,
        content=row.content,
        tool_calls=row.tool_calls,
        trace_metadata=trace,
        prompt_version=row.prompt_version,
        model_provider=row.model_provider,
        model_id=row.model_id,
        token_usage=token_usage,
        created_at=row.created_at.isoformat(),
    )


class ChatService:
    """Orchestrates chat sessions and message turns."""

    def __init__(
        self,
        session_repo: ChatSessionRepository,
        message_repo: ChatMessageRepository,
        copilot: EconomistCopilot | None = None,
        max_tokens: int = 4096,
        model: str = "",
    ) -> None:
        self._session_repo = session_repo
        self._message_repo = message_repo
        self._copilot = copilot
        self._max_tokens = max_tokens
        self._model = model

    async def create_session(
        self,
        workspace_id: UUID,
        title: str | None = None,
    ) -> ChatSessionResponse:
        """Create a new chat session."""
        session_id = new_uuid7()
        row = await self._session_repo.create(
            session_id=session_id,
            workspace_id=workspace_id,
            title=title,
        )
        return _session_row_to_response(row)

    async def get_session(
        self,
        workspace_id: UUID,
        session_id: UUID,
    ) -> ChatSessionDetail | None:
        """Get a session with its messages."""
        session_row = await self._session_repo.get(session_id, workspace_id)
        if session_row is None:
            return None

        message_rows = await self._message_repo.list_for_session(session_id)
        return ChatSessionDetail(
            session=_session_row_to_response(session_row),
            messages=[_message_row_to_response(m) for m in message_rows],
        )

    async def list_sessions(
        self,
        workspace_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> ListSessionsResponse:
        """List sessions for a workspace."""
        rows = await self._session_repo.list_for_workspace(
            workspace_id, limit=limit, offset=offset,
        )
        return ListSessionsResponse(
            sessions=[_session_row_to_response(r) for r in rows],
        )

    async def send_message(
        self,
        workspace_id: UUID,
        session_id: UUID,
        content: str,
        confirm_scenario: bool | None = None,
    ) -> ChatMessageResponse:
        """Send a user message and get an assistant response.

        1. Verify session exists and belongs to workspace
        2. Persist user message
        3. Load conversation history
        4. Call copilot agent (if available)
        5. Persist assistant response with trace metadata
        6. Return assistant response
        """
        # Verify session exists
        session_row = await self._session_repo.get(session_id, workspace_id)
        if session_row is None:
            raise ValueError(f"Session {session_id} not found in workspace {workspace_id}")

        # Persist user message
        user_msg_id = new_uuid7()
        await self._message_repo.create(
            message_id=user_msg_id,
            session_id=session_id,
            role="user",
            content=content,
        )

        # Auto-title from first message
        if session_row.title is None:
            title = content[:100].strip()
            await self._session_repo.update_title(session_id, workspace_id, title)

        # Touch session updated_at
        await self._session_repo.touch(session_id, workspace_id)

        # If no copilot agent, return a stub response
        if self._copilot is None:
            assistant_msg_id = new_uuid7()
            row = await self._message_repo.create(
                message_id=assistant_msg_id,
                session_id=session_id,
                role="assistant",
                content="Copilot is not configured. Please set up LLM API keys.",
            )
            return _message_row_to_response(row)

        # Load conversation history for context
        message_rows = await self._message_repo.list_for_session(session_id)
        history = [
            {"role": m.role, "content": m.content}
            for m in message_rows
            if m.role in ("user", "assistant")
            and str(m.message_id) != str(user_msg_id)  # exclude current user msg
        ]

        # Call copilot
        context = {
            "user_confirmed": confirm_scenario is True,
            "workspace_id": str(workspace_id),
            "max_tokens": self._max_tokens,
            "model": self._model,
        }

        copilot_response: CopilotResponse = await self._copilot.process_turn(
            messages=history,
            user_message=content,
            context=context,
        )

        # Build trace metadata dict for persistence
        trace_dict = None
        if copilot_response.trace_metadata:
            trace_dict = copilot_response.trace_metadata.model_dump(exclude_none=True)

        # Build pending_confirmation into trace if present
        if copilot_response.pending_confirmation:
            trace_dict = trace_dict or {}
            trace_dict["pending_confirmation"] = copilot_response.pending_confirmation

        # Build tool_calls list for persistence
        tool_calls_list = None
        if copilot_response.tool_calls:
            tool_calls_list = [tc.model_dump() for tc in copilot_response.tool_calls]

        # Persist assistant message
        assistant_msg_id = new_uuid7()
        row = await self._message_repo.create(
            message_id=assistant_msg_id,
            session_id=session_id,
            role="assistant",
            content=copilot_response.content,
            tool_calls=tool_calls_list,
            trace_metadata=trace_dict,
            prompt_version=copilot_response.prompt_version,
            model_provider=copilot_response.model_provider,
            model_id=copilot_response.model_id,
            token_usage=copilot_response.token_usage.model_dump(),
        )

        return _message_row_to_response(row)
