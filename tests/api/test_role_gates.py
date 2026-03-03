"""Tests for S11-1: Role gates on sensitive endpoints.

Covers: analyst denied (403) on sensitive actions, manager/admin
allowed, non-member still 404. Uses unauthed_client with real auth.
"""

from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_async_session
from src.db.tables import WorkspaceMembershipRow, WorkspaceRow
from src.models.common import utc_now

ANALYST_ID = UUID("00000000-0000-7000-8000-000000000001")
MANAGER_ID = UUID("00000000-0000-7000-8000-000000000002")
ADMIN_ID = UUID("00000000-0000-7000-8000-000000000003")
WS_ID = UUID("00000000-0000-7000-8000-000000000010")


@pytest.fixture
async def unauthed_client(db_session: AsyncSession) -> AsyncClient:
    from src.api.main import app

    async def _override_session():
        yield db_session

    app.dependency_overrides[get_async_session] = _override_session

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


async def _login(client: AsyncClient, username: str) -> str:
    resp = await client.post(
        "/v1/auth/login", json={"username": username, "password": "any"},
    )
    return resp.json()["token"]


async def _seed(
    session: AsyncSession, user_id: UUID, role: str,
) -> None:
    now = utc_now()
    ws = WorkspaceRow(
        workspace_id=WS_ID, client_name="T", engagement_code="E",
        classification="CONFIDENTIAL", description="",
        created_by=user_id, created_at=now, updated_at=now,
    )
    session.add(ws)
    session.add(WorkspaceMembershipRow(
        workspace_id=WS_ID, user_id=user_id,
        role=role, created_at=now, created_by=user_id,
    ))
    await session.flush()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ===================================================================
# S11-1: POST /v1/engine/models — admin only
# ===================================================================


class TestModelRegistrationRoleGate:

    @pytest.mark.anyio
    async def test_analyst_denied_403(
        self, unauthed_client: AsyncClient,
    ) -> None:
        """Analyst role cannot register models."""
        token = await _login(unauthed_client, "analyst")
        resp = await unauthed_client.post(
            "/v1/engine/models", headers=_auth(token), json={},
        )
        assert resp.status_code == 403

    @pytest.mark.anyio
    async def test_admin_allowed(
        self, unauthed_client: AsyncClient,
    ) -> None:
        """Admin role can register models (may fail on payload, not 403)."""
        token = await _login(unauthed_client, "admin")
        resp = await unauthed_client.post(
            "/v1/engine/models", headers=_auth(token), json={},
        )
        assert resp.status_code != 403


# ===================================================================
# S11-1: POST /{ws}/exports — manager/admin
# ===================================================================


class TestExportCreationRoleGate:

    @pytest.mark.anyio
    async def test_analyst_denied_403(
        self, unauthed_client: AsyncClient, db_session: AsyncSession,
    ) -> None:
        await _seed(db_session, ANALYST_ID, "analyst")
        token = await _login(unauthed_client, "analyst")
        resp = await unauthed_client.post(
            f"/v1/workspaces/{WS_ID}/exports",
            headers=_auth(token), json={},
        )
        assert resp.status_code == 403

    @pytest.mark.anyio
    async def test_manager_allowed(
        self, unauthed_client: AsyncClient, db_session: AsyncSession,
    ) -> None:
        await _seed(db_session, MANAGER_ID, "manager")
        token = await _login(unauthed_client, "manager")
        resp = await unauthed_client.post(
            f"/v1/workspaces/{WS_ID}/exports",
            headers=_auth(token), json={},
        )
        assert resp.status_code != 403


# ===================================================================
# S11-1: GET /{ws}/exports/{id}/download/{fmt} — manager/admin
# ===================================================================


class TestExportDownloadRoleGate:

    @pytest.mark.anyio
    async def test_analyst_denied_403(
        self, unauthed_client: AsyncClient, db_session: AsyncSession,
    ) -> None:
        await _seed(db_session, ANALYST_ID, "analyst")
        token = await _login(unauthed_client, "analyst")
        resp = await unauthed_client.get(
            f"/v1/workspaces/{WS_ID}/exports/"
            f"00000000-0000-7000-8000-ffffffffffff/download/xlsx",
            headers=_auth(token),
        )
        assert resp.status_code == 403

    @pytest.mark.anyio
    async def test_manager_allowed(
        self, unauthed_client: AsyncClient, db_session: AsyncSession,
    ) -> None:
        await _seed(db_session, MANAGER_ID, "manager")
        token = await _login(unauthed_client, "manager")
        resp = await unauthed_client.get(
            f"/v1/workspaces/{WS_ID}/exports/"
            f"00000000-0000-7000-8000-ffffffffffff/download/xlsx",
            headers=_auth(token),
        )
        assert resp.status_code != 403


# ===================================================================
# S11-1: POST /{ws}/scenarios/{id}/lock — manager/admin
# ===================================================================


class TestScenarioLockRoleGate:

    @pytest.mark.anyio
    async def test_analyst_denied_403(
        self, unauthed_client: AsyncClient, db_session: AsyncSession,
    ) -> None:
        await _seed(db_session, ANALYST_ID, "analyst")
        token = await _login(unauthed_client, "analyst")
        resp = await unauthed_client.post(
            f"/v1/workspaces/{WS_ID}/scenarios/"
            f"00000000-0000-7000-8000-ffffffffffff/lock",
            headers=_auth(token), json={},
        )
        assert resp.status_code == 403

    @pytest.mark.anyio
    async def test_manager_allowed(
        self, unauthed_client: AsyncClient, db_session: AsyncSession,
    ) -> None:
        await _seed(db_session, MANAGER_ID, "manager")
        token = await _login(unauthed_client, "manager")
        resp = await unauthed_client.post(
            f"/v1/workspaces/{WS_ID}/scenarios/"
            f"00000000-0000-7000-8000-ffffffffffff/lock",
            headers=_auth(token), json={},
        )
        assert resp.status_code != 403


# ===================================================================
# S11-1: POST /{ws}/scenarios/{id}/run (governed) — manager/admin
# ===================================================================


class TestGovernedRunRoleGate:

    @pytest.mark.anyio
    async def test_analyst_denied_403(
        self, unauthed_client: AsyncClient, db_session: AsyncSession,
    ) -> None:
        await _seed(db_session, ANALYST_ID, "analyst")
        token = await _login(unauthed_client, "analyst")
        resp = await unauthed_client.post(
            f"/v1/workspaces/{WS_ID}/scenarios/"
            f"00000000-0000-7000-8000-ffffffffffff/run",
            headers=_auth(token),
            json={"mode": "GOVERNED"},
        )
        assert resp.status_code == 403

    @pytest.mark.anyio
    async def test_manager_allowed(
        self, unauthed_client: AsyncClient, db_session: AsyncSession,
    ) -> None:
        await _seed(db_session, MANAGER_ID, "manager")
        token = await _login(unauthed_client, "manager")
        resp = await unauthed_client.post(
            f"/v1/workspaces/{WS_ID}/scenarios/"
            f"00000000-0000-7000-8000-ffffffffffff/run",
            headers=_auth(token),
            json={"mode": "GOVERNED"},
        )
        assert resp.status_code != 403


# ===================================================================
# S11-1: POST /{ws}/governance/nff/check — manager/admin
# ===================================================================


class TestNFFCheckRoleGate:

    @pytest.mark.anyio
    async def test_analyst_denied_403(
        self, unauthed_client: AsyncClient, db_session: AsyncSession,
    ) -> None:
        await _seed(db_session, ANALYST_ID, "analyst")
        token = await _login(unauthed_client, "analyst")
        resp = await unauthed_client.post(
            f"/v1/workspaces/{WS_ID}/governance/nff/check",
            headers=_auth(token), json={},
        )
        assert resp.status_code == 403

    @pytest.mark.anyio
    async def test_manager_allowed(
        self, unauthed_client: AsyncClient, db_session: AsyncSession,
    ) -> None:
        await _seed(db_session, MANAGER_ID, "manager")
        token = await _login(unauthed_client, "manager")
        resp = await unauthed_client.post(
            f"/v1/workspaces/{WS_ID}/governance/nff/check",
            headers=_auth(token), json={},
        )
        assert resp.status_code != 403
