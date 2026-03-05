"""Tests for chat session and message repositories — Sprint 25."""

import asyncio
from datetime import timedelta

import pytest
from uuid_extensions import uuid7

from src.db.tables import WorkspaceRow
from src.models.common import utc_now
from src.repositories.chat import ChatMessageRepository, ChatSessionRepository

pytestmark = pytest.mark.anyio

WS_ID = uuid7()
OTHER_WS_ID = uuid7()


async def _seed_workspace(session, workspace_id):
    ws = WorkspaceRow(
        workspace_id=workspace_id,
        client_name="Test",
        engagement_code="T-001",
        classification="INTERNAL",
        description="test",
        created_by=uuid7(),
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    session.add(ws)
    await session.flush()


@pytest.fixture
async def seeded(db_session):
    await _seed_workspace(db_session, WS_ID)
    await _seed_workspace(db_session, OTHER_WS_ID)
    return db_session


# ---------------------------------------------------------------------------
# ChatSessionRepository tests
# ---------------------------------------------------------------------------


class TestChatSessionRepository:
    async def test_create_session_round_trip(self, seeded):
        repo = ChatSessionRepository(seeded)
        sid = uuid7()
        row = await repo.create(
            session_id=sid,
            workspace_id=WS_ID,
            title="My first chat",
        )
        assert row.session_id == sid
        assert row.workspace_id == WS_ID
        assert row.title == "My first chat"
        assert row.created_at is not None
        assert row.updated_at is not None

        fetched = await repo.get(sid, WS_ID)
        assert fetched is not None
        assert fetched.session_id == sid
        assert fetched.title == "My first chat"
        assert fetched.workspace_id == WS_ID

    async def test_session_workspace_isolation(self, seeded):
        repo = ChatSessionRepository(seeded)
        sid = uuid7()
        await repo.create(
            session_id=sid,
            workspace_id=WS_ID,
            title="WS A session",
        )
        # Should find in correct workspace
        assert await repo.get(sid, WS_ID) is not None
        # Should NOT find in different workspace
        assert await repo.get(sid, OTHER_WS_ID) is None

    async def test_list_sessions_for_workspace(self, seeded):
        repo = ChatSessionRepository(seeded)
        sid1 = uuid7()
        sid2 = uuid7()
        await repo.create(
            session_id=sid1,
            workspace_id=WS_ID,
            title="Session 1",
        )
        # Small delay so updated_at differs for ordering
        await asyncio.sleep(0.01)
        await repo.create(
            session_id=sid2,
            workspace_id=WS_ID,
            title="Session 2",
        )

        sessions = await repo.list_for_workspace(WS_ID)
        assert len(sessions) == 2
        # Ordered by updated_at desc, so session 2 should come first
        assert sessions[0].session_id == sid2
        assert sessions[1].session_id == sid1

    async def test_update_session_title(self, seeded):
        repo = ChatSessionRepository(seeded)
        sid = uuid7()
        await repo.create(
            session_id=sid,
            workspace_id=WS_ID,
            title="Original title",
        )
        await repo.update_title(sid, WS_ID, "Updated title")

        fetched = await repo.get(sid, WS_ID)
        assert fetched is not None
        assert fetched.title == "Updated title"


# ---------------------------------------------------------------------------
# ChatMessageRepository tests
# ---------------------------------------------------------------------------


class TestChatMessageRepository:
    async def _create_session(self, db_session, workspace_id=WS_ID):
        """Helper to create a chat session for message tests."""
        repo = ChatSessionRepository(db_session)
        sid = uuid7()
        await repo.create(session_id=sid, workspace_id=workspace_id)
        return sid

    async def test_create_message_round_trip(self, seeded):
        session_id = await self._create_session(seeded)
        repo = ChatMessageRepository(seeded)
        mid = uuid7()
        row = await repo.create(
            message_id=mid,
            session_id=session_id,
            role="user",
            content="Hello, what is the GDP impact?",
            prompt_version="v1.0",
            model_provider="anthropic",
            model_id="claude-opus-4-20250514",
            token_usage={"input_tokens": 100, "output_tokens": 50},
        )
        assert row.message_id == mid
        assert row.role == "user"
        assert row.content == "Hello, what is the GDP impact?"
        assert row.prompt_version == "v1.0"
        assert row.model_provider == "anthropic"
        assert row.model_id == "claude-opus-4-20250514"
        assert row.token_usage == {"input_tokens": 100, "output_tokens": 50}
        assert row.created_at is not None

        messages = await repo.list_for_session(session_id)
        assert len(messages) == 1
        assert messages[0].message_id == mid

    async def test_messages_ordered_by_created_at(self, seeded):
        session_id = await self._create_session(seeded)
        repo = ChatMessageRepository(seeded)

        mids = []
        for i in range(3):
            mid = uuid7()
            mids.append(mid)
            await repo.create(
                message_id=mid,
                session_id=session_id,
                role="user" if i % 2 == 0 else "assistant",
                content=f"Message {i}",
            )
            await asyncio.sleep(0.01)

        messages = await repo.list_for_session(session_id)
        assert len(messages) == 3
        # Should be in ascending created_at order
        assert messages[0].message_id == mids[0]
        assert messages[1].message_id == mids[1]
        assert messages[2].message_id == mids[2]
        assert messages[0].content == "Message 0"
        assert messages[1].content == "Message 1"
        assert messages[2].content == "Message 2"

    async def test_message_with_trace_metadata(self, seeded):
        session_id = await self._create_session(seeded)
        repo = ChatMessageRepository(seeded)

        trace = {
            "run_id": str(uuid7()),
            "scenario_spec_id": str(uuid7()),
            "scenario_spec_version": 3,
            "model_version_id": str(uuid7()),
            "io_table": "ksa_2019_71",
            "multiplier_type": "type_ii",
            "assumptions": ["import_share_default", "phasing_linear"],
            "confidence": "HIGH",
            "confidence_reasons": ["verified data", "audited model"],
        }

        mid = uuid7()
        await repo.create(
            message_id=mid,
            session_id=session_id,
            role="assistant",
            content="The GDP impact is 1.2B SAR.",
            trace_metadata=trace,
        )

        messages = await repo.list_for_session(session_id)
        assert len(messages) == 1
        msg = messages[0]
        assert msg.trace_metadata is not None
        assert msg.trace_metadata["run_id"] == trace["run_id"]
        assert msg.trace_metadata["scenario_spec_version"] == 3
        assert msg.trace_metadata["assumptions"] == [
            "import_share_default",
            "phasing_linear",
        ]
        assert msg.trace_metadata["confidence"] == "HIGH"
        assert msg.trace_metadata["confidence_reasons"] == [
            "verified data",
            "audited model",
        ]

    async def test_message_with_tool_calls(self, seeded):
        session_id = await self._create_session(seeded)
        repo = ChatMessageRepository(seeded)

        tool_calls = [
            {
                "tool_name": "run_scenario",
                "arguments": {"shocks": [{"sector": "A", "value": 100}]},
                "result": {"run_id": str(uuid7()), "status": "completed"},
            },
            {
                "tool_name": "get_multiplier",
                "arguments": {"sector": "A", "type": "type_ii"},
                "result": {"value": 1.85},
            },
        ]

        mid = uuid7()
        await repo.create(
            message_id=mid,
            session_id=session_id,
            role="assistant",
            content="I ran the scenario for you.",
            tool_calls=tool_calls,
        )

        messages = await repo.list_for_session(session_id)
        assert len(messages) == 1
        msg = messages[0]
        assert msg.tool_calls is not None
        assert len(msg.tool_calls) == 2
        assert msg.tool_calls[0]["tool_name"] == "run_scenario"
        assert msg.tool_calls[1]["tool_name"] == "get_multiplier"
        assert msg.tool_calls[1]["result"]["value"] == 1.85
