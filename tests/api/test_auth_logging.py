"""Tests for S10-4: Auth decision logging and secret redaction.

Covers: auth allow/deny logs contain decision metadata
(user_id, workspace_id, role, reason), and that tokens/secrets
never appear in log output.
"""

import logging
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_async_session
from src.db.tables import WorkspaceMembershipRow, WorkspaceRow
from src.models.common import utc_now

ANALYST_USER_ID = UUID("00000000-0000-7000-8000-000000000001")
DEV_WS_ID = UUID("00000000-0000-7000-8000-000000000010")


@pytest.fixture
async def unauthed_client(db_session: AsyncSession) -> AsyncClient:
    from src.api.main import app

    async def _override_session():
        yield db_session

    app.dependency_overrides[get_async_session] = _override_session

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


async def _login(client: AsyncClient, username: str) -> str:
    resp = await client.post("/v1/auth/login", json={
        "username": username, "password": "any",
    })
    return resp.json()["token"]


class TestAuthDecisionLogging:
    """Auth decisions are logged with structured metadata."""

    @pytest.mark.anyio
    async def test_allow_logs_user_workspace_role(
        self,
        unauthed_client: AsyncClient,
        db_session: AsyncSession,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Successful auth logs user_id, workspace_id, role."""
        now = utc_now()
        db_session.add(WorkspaceRow(
            workspace_id=DEV_WS_ID, client_name="T", engagement_code="E",
            classification="CONFIDENTIAL", description="",
            created_by=ANALYST_USER_ID, created_at=now, updated_at=now,
        ))
        db_session.add(WorkspaceMembershipRow(
            workspace_id=DEV_WS_ID, user_id=ANALYST_USER_ID,
            role="analyst", created_at=now, created_by=ANALYST_USER_ID,
        ))
        await db_session.flush()

        token = await _login(unauthed_client, "analyst")
        with caplog.at_level(logging.INFO, logger="src.api.auth_deps"):
            await unauthed_client.get(
                f"/v1/workspaces/{DEV_WS_ID}",
                headers={"Authorization": f"Bearer {token}"},
            )

        log_text = caplog.text
        assert str(ANALYST_USER_ID) in log_text
        assert str(DEV_WS_ID) in log_text
        assert "analyst" in log_text

    @pytest.mark.anyio
    async def test_deny_logs_not_member(
        self,
        unauthed_client: AsyncClient,
        db_session: AsyncSession,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Non-member denial logs user_id, workspace_id, reason."""
        now = utc_now()
        db_session.add(WorkspaceRow(
            workspace_id=DEV_WS_ID, client_name="T", engagement_code="E",
            classification="CONFIDENTIAL", description="",
            created_by=ANALYST_USER_ID, created_at=now, updated_at=now,
        ))
        await db_session.flush()

        token = await _login(unauthed_client, "analyst")
        with caplog.at_level(logging.INFO, logger="src.api.auth_deps"):
            await unauthed_client.get(
                f"/v1/workspaces/{DEV_WS_ID}",
                headers={"Authorization": f"Bearer {token}"},
            )

        log_text = caplog.text
        assert "not_member" in log_text
        assert str(ANALYST_USER_ID) in log_text


class TestSecretRedaction:
    """Tokens and signing keys must never appear in logs."""

    @pytest.mark.anyio
    async def test_token_not_in_auth_logs(
        self,
        unauthed_client: AsyncClient,
        db_session: AsyncSession,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        now = utc_now()
        db_session.add(WorkspaceRow(
            workspace_id=DEV_WS_ID, client_name="T", engagement_code="E",
            classification="CONFIDENTIAL", description="",
            created_by=ANALYST_USER_ID, created_at=now, updated_at=now,
        ))
        db_session.add(WorkspaceMembershipRow(
            workspace_id=DEV_WS_ID, user_id=ANALYST_USER_ID,
            role="analyst", created_at=now, created_by=ANALYST_USER_ID,
        ))
        await db_session.flush()

        token = await _login(unauthed_client, "analyst")
        with caplog.at_level(logging.DEBUG, logger="src.api.auth_deps"):
            await unauthed_client.get(
                f"/v1/workspaces/{DEV_WS_ID}",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert token not in caplog.text

    @pytest.mark.anyio
    async def test_secret_key_not_in_logs(
        self,
        unauthed_client: AsyncClient,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        from src.config.settings import get_settings
        secret = get_settings().SECRET_KEY

        with caplog.at_level(logging.DEBUG, logger="src.api.auth_deps"):
            await unauthed_client.get("/v1/workspaces")

        assert secret not in caplog.text
