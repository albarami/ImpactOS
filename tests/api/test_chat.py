"""Tests for chat API endpoints (Sprint 25).

POST   /v1/workspaces/{ws}/chat/sessions
GET    /v1/workspaces/{ws}/chat/sessions
GET    /v1/workspaces/{ws}/chat/sessions/{sid}
POST   /v1/workspaces/{ws}/chat/sessions/{sid}/messages
"""

import pytest
from uuid import UUID
from uuid_extensions import uuid7

from src.db.tables import WorkspaceRow
from src.models.common import utc_now

pytestmark = pytest.mark.anyio

WS = "00000000-0000-7000-8000-000000000099"


async def _seed_ws(session, ws_id=WS):
    """Seed a workspace row if it doesn't exist."""
    from sqlalchemy import select
    result = await session.execute(
        select(WorkspaceRow).where(
            WorkspaceRow.workspace_id == UUID(ws_id)
        )
    )
    if result.scalar_one_or_none() is None:
        now = utc_now()
        session.add(WorkspaceRow(
            workspace_id=UUID(ws_id),
            client_name="Test",
            engagement_code="E-CHAT",
            classification="INTERNAL",
            description="",
            created_by=uuid7(),
            created_at=now,
            updated_at=now,
        ))
        await session.flush()


class TestCreateSession:
    async def test_create_session_201(self, client, db_session):
        """POST creates session and returns 201."""
        await _seed_ws(db_session)
        resp = await client.post(
            f"/v1/workspaces/{WS}/chat/sessions",
            json={"title": "My test session"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "My test session"
        assert data["workspace_id"] == WS
        assert "session_id" in data
        assert "created_at" in data
        assert "updated_at" in data

    async def test_create_session_no_title(self, client, db_session):
        """POST without title creates session with null title."""
        await _seed_ws(db_session)
        resp = await client.post(
            f"/v1/workspaces/{WS}/chat/sessions",
            json={},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] is None

    async def test_create_session_401_no_token(self, db_session):
        """POST without auth token returns 401."""
        from httpx import ASGITransport, AsyncClient
        from src.api.main import app

        # Create a fresh client without auth overrides
        app.dependency_overrides.clear()
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as unauthed_client:
                resp = await unauthed_client.post(
                    f"/v1/workspaces/{WS}/chat/sessions",
                    json={"title": "test"},
                )
                assert resp.status_code == 401
        finally:
            # Restore overrides (the client fixture will handle cleanup)
            pass


class TestListSessions:
    async def test_list_sessions_200(self, client, db_session):
        """GET returns session list."""
        await _seed_ws(db_session)
        # Create a few sessions
        await client.post(
            f"/v1/workspaces/{WS}/chat/sessions",
            json={"title": "Session 1"},
        )
        await client.post(
            f"/v1/workspaces/{WS}/chat/sessions",
            json={"title": "Session 2"},
        )
        resp = await client.get(f"/v1/workspaces/{WS}/chat/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert "sessions" in data
        assert len(data["sessions"]) == 2

    async def test_list_sessions_empty(self, client, db_session):
        """GET returns empty list when no sessions exist."""
        await _seed_ws(db_session)
        resp = await client.get(f"/v1/workspaces/{WS}/chat/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["sessions"] == []

    async def test_list_sessions_pagination(self, client, db_session):
        """GET respects limit and offset parameters."""
        await _seed_ws(db_session)
        for i in range(5):
            await client.post(
                f"/v1/workspaces/{WS}/chat/sessions",
                json={"title": f"Session {i}"},
            )
        resp = await client.get(
            f"/v1/workspaces/{WS}/chat/sessions?limit=2&offset=0",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["sessions"]) == 2


class TestGetSession:
    async def test_get_session_200(self, client, db_session):
        """GET returns session with messages."""
        await _seed_ws(db_session)
        # Create session
        create_resp = await client.post(
            f"/v1/workspaces/{WS}/chat/sessions",
            json={"title": "Detail session"},
        )
        sid = create_resp.json()["session_id"]
        # Send a message so we have messages in the response
        await client.post(
            f"/v1/workspaces/{WS}/chat/sessions/{sid}/messages",
            json={"content": "Hello copilot"},
        )
        resp = await client.get(
            f"/v1/workspaces/{WS}/chat/sessions/{sid}",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "session" in data
        assert "messages" in data
        assert data["session"]["session_id"] == sid
        # Should have user message + stub assistant response
        assert len(data["messages"]) >= 2

    async def test_get_session_404_not_found(self, client, db_session):
        """GET with invalid session_id returns 404."""
        await _seed_ws(db_session)
        fake_sid = str(uuid7())
        resp = await client.get(
            f"/v1/workspaces/{WS}/chat/sessions/{fake_sid}",
        )
        assert resp.status_code == 404


class TestSendMessage:
    async def test_send_message_201(self, client, db_session):
        """POST sends message and returns assistant response."""
        await _seed_ws(db_session)
        create_resp = await client.post(
            f"/v1/workspaces/{WS}/chat/sessions",
            json={"title": "Msg session"},
        )
        sid = create_resp.json()["session_id"]
        resp = await client.post(
            f"/v1/workspaces/{WS}/chat/sessions/{sid}/messages",
            json={"content": "What is GDP impact?"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["role"] == "assistant"
        assert "content" in data
        assert "message_id" in data
        assert "created_at" in data

    async def test_send_message_404_invalid_session(self, client, db_session):
        """POST to nonexistent session returns 404."""
        await _seed_ws(db_session)
        fake_sid = str(uuid7())
        resp = await client.post(
            f"/v1/workspaces/{WS}/chat/sessions/{fake_sid}/messages",
            json={"content": "Hello"},
        )
        assert resp.status_code == 404

    async def test_send_message_with_confirm_scenario(self, client, db_session):
        """POST with confirm_scenario field accepted."""
        await _seed_ws(db_session)
        create_resp = await client.post(
            f"/v1/workspaces/{WS}/chat/sessions",
            json={},
        )
        sid = create_resp.json()["session_id"]
        resp = await client.post(
            f"/v1/workspaces/{WS}/chat/sessions/{sid}/messages",
            json={"content": "Run it", "confirm_scenario": True},
        )
        assert resp.status_code == 201


class TestWorkspaceIsolation:
    async def test_workspace_isolation(self, client, db_session):
        """Session from workspace A not accessible from workspace B."""
        await _seed_ws(db_session, WS)
        other_ws = str(uuid7())
        await _seed_ws(db_session, other_ws)

        # Create session in WS
        create_resp = await client.post(
            f"/v1/workspaces/{WS}/chat/sessions",
            json={"title": "WS A session"},
        )
        sid = create_resp.json()["session_id"]

        # Try to access from other workspace — should 404
        resp = await client.get(
            f"/v1/workspaces/{other_ws}/chat/sessions/{sid}",
        )
        assert resp.status_code == 404
