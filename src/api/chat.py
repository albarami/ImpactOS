"""Chat API endpoints — workspace-scoped (Sprint 25).

POST   /v1/workspaces/{workspace_id}/chat/sessions              — create session
GET    /v1/workspaces/{workspace_id}/chat/sessions               — list sessions
GET    /v1/workspaces/{workspace_id}/chat/sessions/{session_id}  — get session + messages
POST   /v1/workspaces/{workspace_id}/chat/sessions/{session_id}/messages — send message
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth_deps import WorkspaceMember, require_workspace_member
from src.config.settings import get_settings
from src.db.session import get_async_session
from src.models.chat import (
    ChatMessageResponse,
    ChatSessionDetail,
    ChatSessionResponse,
    CreateSessionRequest,
    ListSessionsResponse,
    SendMessageRequest,
)
from src.repositories.chat import ChatMessageRepository, ChatSessionRepository
from src.services.chat import ChatService

router = APIRouter(prefix="/v1/workspaces", tags=["chat"])


def _get_chat_service(
    session: AsyncSession,
    copilot=None,
) -> ChatService:
    """Build ChatService with repos from DB session."""
    settings = get_settings()
    return ChatService(
        session_repo=ChatSessionRepository(session),
        message_repo=ChatMessageRepository(session),
        copilot=copilot,
        max_tokens=settings.COPILOT_MAX_TOKENS,
        model=settings.COPILOT_MODEL,
    )


@router.post(
    "/{workspace_id}/chat/sessions",
    response_model=ChatSessionResponse,
    status_code=201,
)
async def create_session(
    workspace_id: UUID,
    body: CreateSessionRequest,
    member: WorkspaceMember = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_async_session),
) -> ChatSessionResponse:
    """Create a new chat session in this workspace."""
    svc = _get_chat_service(session)
    return await svc.create_session(workspace_id, title=body.title)


@router.get(
    "/{workspace_id}/chat/sessions",
    response_model=ListSessionsResponse,
)
async def list_sessions(
    workspace_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    member: WorkspaceMember = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_async_session),
) -> ListSessionsResponse:
    """List chat sessions in this workspace (newest first)."""
    svc = _get_chat_service(session)
    return await svc.list_sessions(workspace_id, limit=limit, offset=offset)


@router.get(
    "/{workspace_id}/chat/sessions/{session_id}",
    response_model=ChatSessionDetail,
)
async def get_session(
    workspace_id: UUID,
    session_id: UUID,
    member: WorkspaceMember = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_async_session),
) -> ChatSessionDetail:
    """Get a chat session with all messages."""
    svc = _get_chat_service(session)
    detail = await svc.get_session(workspace_id, session_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    return detail


@router.post(
    "/{workspace_id}/chat/sessions/{session_id}/messages",
    response_model=ChatMessageResponse,
    status_code=201,
)
async def send_message(
    workspace_id: UUID,
    session_id: UUID,
    body: SendMessageRequest,
    member: WorkspaceMember = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_async_session),
) -> ChatMessageResponse:
    """Send a user message and receive assistant response.

    Set confirm_scenario=true to approve a pending scenario before engine run.
    """
    svc = _get_chat_service(session)
    try:
        return await svc.send_message(
            workspace_id=workspace_id,
            session_id=session_id,
            content=body.content,
            confirm_scenario=body.confirm_scenario,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
