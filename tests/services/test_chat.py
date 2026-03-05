"""Tests for ChatService (Sprint 25)."""

import pytest
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db.session import Base
import src.db.tables  # noqa: F401
from src.db.tables import WorkspaceRow
from src.models.common import utc_now
from src.repositories.chat import ChatMessageRepository, ChatSessionRepository
from src.services.chat import ChatService
from src.agents.economist_copilot import CopilotResponse
from src.models.chat import TokenUsage, TraceMetadata


@pytest.fixture
async def db_session():
    """Create in-memory SQLite session with workspace."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        ws_id = uuid4()
        now = utc_now()
        ws = WorkspaceRow(
            workspace_id=ws_id,
            client_name="Test Client",
            engagement_code="T-SVC",
            classification="INTERNAL",
            description="test workspace",
            created_by=uuid4(),
            created_at=now,
            updated_at=now,
        )
        session.add(ws)
        await session.flush()
        yield session, ws_id
    await engine.dispose()


@pytest.fixture
def mock_copilot():
    """Create a mock EconomistCopilot."""
    copilot = AsyncMock()
    copilot.process_turn = AsyncMock(return_value=CopilotResponse(
        content="I understand your question about tourism impacts.",
        prompt_version="copilot_v1",
        model_provider="anthropic",
        model_id="claude-sonnet-4-20250514",
        token_usage=TokenUsage(input_tokens=100, output_tokens=50),
    ))
    return copilot


class TestChatService:
    """Service-level tests for chat orchestration."""

    async def test_create_session(self, db_session):
        session, ws_id = db_session
        svc = ChatService(
            ChatSessionRepository(session),
            ChatMessageRepository(session),
        )
        result = await svc.create_session(ws_id, title="Test Session")
        assert result.title == "Test Session"
        assert result.workspace_id == str(ws_id)

    async def test_list_sessions(self, db_session):
        session, ws_id = db_session
        svc = ChatService(
            ChatSessionRepository(session),
            ChatMessageRepository(session),
        )
        await svc.create_session(ws_id, title="S1")
        await svc.create_session(ws_id, title="S2")
        result = await svc.list_sessions(ws_id)
        assert len(result.sessions) == 2

    async def test_get_session_with_messages(self, db_session):
        session, ws_id = db_session
        svc = ChatService(
            ChatSessionRepository(session),
            ChatMessageRepository(session),
        )
        created = await svc.create_session(ws_id)
        sid = UUID(created.session_id)
        # Send a message (no copilot = stub response)
        await svc.send_message(ws_id, sid, "Hello")
        detail = await svc.get_session(ws_id, sid)
        assert detail is not None
        assert len(detail.messages) == 2  # user + assistant stub

    async def test_send_message_persists_user_message(self, db_session, mock_copilot):
        session, ws_id = db_session
        svc = ChatService(
            ChatSessionRepository(session),
            ChatMessageRepository(session),
            copilot=mock_copilot,
        )
        created = await svc.create_session(ws_id)
        sid = UUID(created.session_id)
        await svc.send_message(ws_id, sid, "What is the impact of tourism?")
        detail = await svc.get_session(ws_id, sid)
        assert detail is not None
        # Should have user message + assistant response
        roles = [m.role for m in detail.messages]
        assert "user" in roles
        assert "assistant" in roles

    async def test_send_message_returns_prompt_version(self, db_session, mock_copilot):
        session, ws_id = db_session
        svc = ChatService(
            ChatSessionRepository(session),
            ChatMessageRepository(session),
            copilot=mock_copilot,
        )
        created = await svc.create_session(ws_id)
        sid = UUID(created.session_id)
        result = await svc.send_message(ws_id, sid, "Test")
        assert result.prompt_version == "copilot_v1"

    async def test_send_message_returns_trace_metadata(self, db_session):
        """When copilot returns trace metadata, it must be in the response."""
        session, ws_id = db_session
        copilot = AsyncMock()
        copilot.process_turn = AsyncMock(return_value=CopilotResponse(
            content="Results show GDP impact of SAR 1.2bn",
            trace_metadata=TraceMetadata(
                run_id="run-123",
                scenario_spec_id="spec-456",
                model_version_id="mv-789",
                confidence="HIGH",
            ),
            prompt_version="copilot_v1",
            model_provider="anthropic",
            model_id="claude-sonnet-4-20250514",
            token_usage=TokenUsage(input_tokens=200, output_tokens=100),
        ))
        svc = ChatService(
            ChatSessionRepository(session),
            ChatMessageRepository(session),
            copilot=copilot,
        )
        created = await svc.create_session(ws_id)
        sid = UUID(created.session_id)
        result = await svc.send_message(ws_id, sid, "Run the analysis")
        assert result.trace_metadata is not None
        assert result.trace_metadata.run_id == "run-123"
        assert result.trace_metadata.confidence == "HIGH"

    async def test_send_message_auto_titles_session(self, db_session, mock_copilot):
        session, ws_id = db_session
        svc = ChatService(
            ChatSessionRepository(session),
            ChatMessageRepository(session),
            copilot=mock_copilot,
        )
        created = await svc.create_session(ws_id)  # no title
        sid = UUID(created.session_id)
        await svc.send_message(ws_id, sid, "Impact of Umrah visa changes")
        detail = await svc.get_session(ws_id, sid)
        assert detail is not None
        assert detail.session.title == "Impact of Umrah visa changes"

    async def test_session_not_found_raises(self, db_session, mock_copilot):
        session, ws_id = db_session
        svc = ChatService(
            ChatSessionRepository(session),
            ChatMessageRepository(session),
            copilot=mock_copilot,
        )
        with pytest.raises(ValueError, match="not found"):
            await svc.send_message(ws_id, uuid4(), "Hello")

    async def test_session_workspace_isolation(self, db_session):
        session, ws_id = db_session
        svc = ChatService(
            ChatSessionRepository(session),
            ChatMessageRepository(session),
        )
        created = await svc.create_session(ws_id)
        sid = UUID(created.session_id)
        # Try to get session from different workspace
        other_ws = uuid4()
        result = await svc.get_session(other_ws, sid)
        assert result is None

    async def test_no_copilot_returns_stub(self, db_session):
        """Without copilot configured, returns a stub message."""
        session, ws_id = db_session
        svc = ChatService(
            ChatSessionRepository(session),
            ChatMessageRepository(session),
            copilot=None,
        )
        created = await svc.create_session(ws_id)
        sid = UUID(created.session_id)
        result = await svc.send_message(ws_id, sid, "Hello")
        assert "not configured" in result.content.lower()

    async def test_chat_service_passes_max_tokens_in_context(self, db_session):
        """ChatService passes max_tokens from constructor into copilot context."""
        session, ws_id = db_session
        copilot = AsyncMock()
        copilot.process_turn = AsyncMock(return_value=CopilotResponse(
            content="Analysis complete.",
            prompt_version="copilot_v1",
            model_provider="anthropic",
            model_id="claude-sonnet-4-20250514",
            token_usage=TokenUsage(input_tokens=50, output_tokens=30),
        ))

        svc = ChatService(
            ChatSessionRepository(session),
            ChatMessageRepository(session),
            copilot=copilot,
            max_tokens=8192,
        )
        created = await svc.create_session(ws_id)
        sid = UUID(created.session_id)
        await svc.send_message(ws_id, sid, "Test")

        # Verify context passed to copilot
        call_args = copilot.process_turn.call_args
        ctx = call_args.kwargs.get("context", call_args[0][2] if len(call_args[0]) > 2 else {})
        assert ctx.get("max_tokens") == 8192

    async def test_chat_service_passes_model_in_context(self, db_session):
        """ChatService passes model from constructor into copilot context."""
        session, ws_id = db_session
        copilot = AsyncMock()
        copilot.process_turn = AsyncMock(return_value=CopilotResponse(
            content="Analysis complete.",
            prompt_version="copilot_v1",
            model_provider="anthropic",
            model_id="claude-sonnet-4-20250514",
            token_usage=TokenUsage(input_tokens=50, output_tokens=30),
        ))

        svc = ChatService(
            ChatSessionRepository(session),
            ChatMessageRepository(session),
            copilot=copilot,
            model="claude-sonnet-4-20250514",
        )
        created = await svc.create_session(ws_id)
        sid = UUID(created.session_id)
        await svc.send_message(ws_id, sid, "Test")

        call_args = copilot.process_turn.call_args
        ctx = call_args.kwargs.get("context", call_args[0][2] if len(call_args[0]) > 2 else {})
        assert ctx.get("model") == "claude-sonnet-4-20250514"

    async def test_chat_service_defaults_when_no_settings(self, db_session):
        """ChatService constructor defaults work without explicit settings."""
        session, ws_id = db_session
        copilot = AsyncMock()
        copilot.process_turn = AsyncMock(return_value=CopilotResponse(
            content="Ok.",
            prompt_version="copilot_v1",
            model_provider="anthropic",
            model_id="claude-sonnet-4-20250514",
            token_usage=TokenUsage(input_tokens=10, output_tokens=5),
        ))

        # No max_tokens or model passed — should use defaults
        svc = ChatService(
            ChatSessionRepository(session),
            ChatMessageRepository(session),
            copilot=copilot,
        )
        created = await svc.create_session(ws_id)
        sid = UUID(created.session_id)
        await svc.send_message(ws_id, sid, "Test")

        call_args = copilot.process_turn.call_args
        ctx = call_args.kwargs.get("context", call_args[0][2] if len(call_args[0]) > 2 else {})
        assert ctx.get("max_tokens") == 4096  # default
        assert ctx.get("model") == ""  # default empty

    async def test_copilot_uses_max_tokens_from_context(self, db_session):
        """Copilot's process_turn receives max_tokens from the context."""
        session, ws_id = db_session
        copilot = AsyncMock()
        copilot.process_turn = AsyncMock(return_value=CopilotResponse(
            content="Done.",
            prompt_version="copilot_v1",
            model_provider="anthropic",
            model_id="claude-sonnet-4-20250514",
            token_usage=TokenUsage(input_tokens=10, output_tokens=5),
        ))

        svc = ChatService(
            ChatSessionRepository(session),
            ChatMessageRepository(session),
            copilot=copilot,
            max_tokens=16384,
        )
        created = await svc.create_session(ws_id)
        sid = UUID(created.session_id)
        await svc.send_message(ws_id, sid, "Analyze everything")

        call_args = copilot.process_turn.call_args
        ctx = call_args.kwargs.get("context", call_args[0][2] if len(call_args[0]) > 2 else {})
        assert ctx["max_tokens"] == 16384

    async def test_chat_service_sends_history_to_copilot(self, db_session):
        """Chat service passes prior messages as history to copilot."""
        session, ws_id = db_session
        copilot = AsyncMock()

        # First turn response
        first_response = CopilotResponse(
            content="Tourism affects sectors I and G.",
            prompt_version="copilot_v1",
            model_provider="anthropic",
            model_id="claude-sonnet-4-20250514",
            token_usage=TokenUsage(input_tokens=50, output_tokens=30),
        )
        # Second turn response
        second_response = CopilotResponse(
            content="Sector I includes accommodation and food.",
            prompt_version="copilot_v1",
            model_provider="anthropic",
            model_id="claude-sonnet-4-20250514",
            token_usage=TokenUsage(input_tokens=100, output_tokens=60),
        )
        copilot.process_turn = AsyncMock(side_effect=[first_response, second_response])

        svc = ChatService(
            ChatSessionRepository(session),
            ChatMessageRepository(session),
            copilot=copilot,
        )
        created = await svc.create_session(ws_id)
        sid = UUID(created.session_id)

        # Send first message
        await svc.send_message(ws_id, sid, "What sectors does tourism affect?")

        # Send second message — history should include first exchange
        await svc.send_message(ws_id, sid, "Tell me more about sector I.")

        # Verify the second call received history
        second_call = copilot.process_turn.call_args_list[1]
        history_arg = second_call.kwargs.get("messages", second_call[0][0] if second_call[0] else [])

        # History should include at least the first user msg and first assistant response
        # (the second user message is passed separately as user_message)
        assert len(history_arg) >= 2
        roles = [m["role"] for m in history_arg]
        assert "user" in roles
        assert "assistant" in roles
