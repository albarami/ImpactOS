"""Tests for S11-3: Complete auth matrix coverage.

Verifies consistent 401/403/404 semantics across all protected route
families. Each route family has: unauthenticated → 401, non-member → 404,
and role-gated sensitive actions → 403 for insufficient role.
"""

from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_extensions import uuid7

from src.db.session import get_async_session
from src.db.tables import WorkspaceMembershipRow, WorkspaceRow
from src.models.common import utc_now

ANALYST_ID = UUID("00000000-0000-7000-8000-000000000001")
MANAGER_ID = UUID("00000000-0000-7000-8000-000000000002")
ADMIN_ID = UUID("00000000-0000-7000-8000-000000000003")
WS = UUID("00000000-0000-7000-8000-000000000010")
FAKE_ID = str(uuid7())


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


async def _login(c: AsyncClient, user: str) -> str:
    r = await c.post("/v1/auth/login", json={"username": user, "password": "x"})
    return r.json()["token"]


async def _seed_member(
    s: AsyncSession, uid: UUID, role: str,
) -> None:
    now = utc_now()
    try:
        s.add(WorkspaceRow(
            workspace_id=WS, client_name="T", engagement_code="E",
            classification="CONFIDENTIAL", description="",
            created_by=uid, created_at=now, updated_at=now,
        ))
        await s.flush()
    except Exception:
        pass
    s.add(WorkspaceMembershipRow(
        workspace_id=WS, user_id=uid,
        role=role, created_at=now, created_by=uid,
    ))
    await s.flush()


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ===================================================================
# 401: unauthenticated requests across all route families
# ===================================================================


_UNAUTH_ROUTES = [
    ("GET", f"/v1/workspaces/{WS}"),
    ("GET", f"/v1/workspaces/{WS}/documents"),
    ("POST", f"/v1/workspaces/{WS}/compiler/compile"),
    ("GET", f"/v1/workspaces/{WS}/scenarios"),
    ("POST", f"/v1/workspaces/{WS}/engine/runs"),
    ("POST", f"/v1/workspaces/{WS}/exports"),
    ("POST", f"/v1/workspaces/{WS}/governance/nff/check"),
    ("GET", f"/v1/workspaces/{WS}/libraries/mapping/entries"),
    ("POST", f"/v1/workspaces/{WS}/depth/plans"),
    ("GET", f"/v1/workspaces/{WS}/models/versions"),
    ("POST", "/v1/engine/models"),
]


class TestUnauthenticated401:
    """Every protected endpoint returns 401 without a token."""

    @pytest.mark.anyio
    @pytest.mark.parametrize("method,path", _UNAUTH_ROUTES)
    async def test_no_token_401(
        self, unauthed_client: AsyncClient, method: str, path: str,
    ) -> None:
        resp = await unauthed_client.request(method, path, json={})
        assert resp.status_code == 401, f"{method} {path} → {resp.status_code}"


# ===================================================================
# 404: authenticated but non-member
# ===================================================================


_NON_MEMBER_ROUTES = [
    ("GET", f"/v1/workspaces/{WS}"),
    ("GET", f"/v1/workspaces/{WS}/documents"),
    ("POST", f"/v1/workspaces/{WS}/compiler/compile"),
    ("GET", f"/v1/workspaces/{WS}/scenarios"),
    ("POST", f"/v1/workspaces/{WS}/engine/runs"),
    ("POST", f"/v1/workspaces/{WS}/exports"),
    ("POST", f"/v1/workspaces/{WS}/governance/nff/check"),
    ("GET", f"/v1/workspaces/{WS}/libraries/mapping/entries"),
    ("POST", f"/v1/workspaces/{WS}/depth/plans"),
    ("GET", f"/v1/workspaces/{WS}/models/versions"),
]


class TestNonMember404:
    """Authenticated user not in workspace gets 404 (no data leakage)."""

    @pytest.mark.anyio
    @pytest.mark.parametrize("method,path", _NON_MEMBER_ROUTES)
    async def test_non_member_404(
        self,
        unauthed_client: AsyncClient,
        db_session: AsyncSession,
        method: str,
        path: str,
    ) -> None:
        # Workspace exists but analyst has no membership
        now = utc_now()
        try:
            db_session.add(WorkspaceRow(
                workspace_id=WS, client_name="T", engagement_code="E",
                classification="CONFIDENTIAL", description="",
                created_by=ADMIN_ID, created_at=now, updated_at=now,
            ))
            await db_session.flush()
        except Exception:
            pass

        token = await _login(unauthed_client, "analyst")
        resp = await unauthed_client.request(
            method, path, headers=_h(token), json={},
        )
        assert resp.status_code == 404, f"{method} {path} → {resp.status_code}"


# ===================================================================
# 403: insufficient role on sensitive actions
# ===================================================================


_ROLE_GATED_ROUTES = [
    ("PUT", f"/v1/workspaces/{WS}"),
    ("POST", f"/v1/workspaces/{WS}/exports"),
    ("GET", f"/v1/workspaces/{WS}/exports/{FAKE_ID}/download/xlsx"),
    ("POST", f"/v1/workspaces/{WS}/scenarios/{FAKE_ID}/lock"),
    ("POST", f"/v1/workspaces/{WS}/scenarios/{FAKE_ID}/run"),
    ("POST", f"/v1/workspaces/{WS}/governance/nff/check"),
]


class TestInsufficientRole403:
    """Analyst member denied on manager/admin-gated endpoints."""

    @pytest.mark.anyio
    @pytest.mark.parametrize("method,path", _ROLE_GATED_ROUTES)
    async def test_analyst_denied_403(
        self,
        unauthed_client: AsyncClient,
        db_session: AsyncSession,
        method: str,
        path: str,
    ) -> None:
        await _seed_member(db_session, ANALYST_ID, "analyst")
        token = await _login(unauthed_client, "analyst")
        resp = await unauthed_client.request(
            method, path, headers=_h(token), json={},
        )
        assert resp.status_code == 403, f"{method} {path} → {resp.status_code}"


class TestGlobalRoleGate403:
    """Analyst denied on global admin-gated endpoint."""

    @pytest.mark.anyio
    async def test_analyst_denied_model_registration(
        self, unauthed_client: AsyncClient,
    ) -> None:
        token = await _login(unauthed_client, "analyst")
        resp = await unauthed_client.post(
            "/v1/engine/models", headers=_h(token), json={},
        )
        assert resp.status_code == 403


# ===================================================================
# Public endpoints remain accessible without auth
# ===================================================================


class TestPublicEndpoints:
    """Health and version endpoints require no authentication."""

    @pytest.mark.anyio
    async def test_health_no_auth(self, unauthed_client: AsyncClient) -> None:
        resp = await unauthed_client.get("/health")
        assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_version_no_auth(
        self, unauthed_client: AsyncClient,
    ) -> None:
        resp = await unauthed_client.get("/api/version")
        assert resp.status_code == 200
