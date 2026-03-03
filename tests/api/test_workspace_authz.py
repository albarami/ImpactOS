"""Tests for S10-2: Workspace authorization and role policy.

Covers: non-member workspace → 404, member workspace → 200,
insufficient role → 403, created_by set from principal (not body).

Uses unauthed_client fixture to test real auth+authz behavior.
"""

from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_async_session
from src.db.tables import WorkspaceMembershipRow, WorkspaceRow
from src.models.common import utc_now

# Stable dev user IDs (must match src/api/auth.py _DEV_USERS)
ANALYST_USER_ID = UUID("00000000-0000-7000-8000-000000000001")
MANAGER_USER_ID = UUID("00000000-0000-7000-8000-000000000002")
ADMIN_USER_ID = UUID("00000000-0000-7000-8000-000000000003")
DEV_WS_ID = UUID("00000000-0000-7000-8000-000000000010")


@pytest.fixture
async def unauthed_client(db_session: AsyncSession) -> AsyncClient:
    """Client WITHOUT auth override — tests real auth+authz behavior."""
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


async def _seed_workspace_and_membership(
    session: AsyncSession,
    workspace_id: UUID,
    user_id: UUID,
    role: str,
) -> None:
    """Seed a workspace and membership row directly in the DB."""
    now = utc_now()
    ws = WorkspaceRow(
        workspace_id=workspace_id,
        client_name="Test WS",
        engagement_code="ENG-001",
        classification="CONFIDENTIAL",
        description="test",
        created_by=user_id,
        created_at=now,
        updated_at=now,
    )
    session.add(ws)

    membership = WorkspaceMembershipRow(
        workspace_id=workspace_id,
        user_id=user_id,
        role=role,
        created_at=now,
        created_by=user_id,
    )
    session.add(membership)
    await session.flush()


# ===================================================================
# S10-2: Non-member workspace → 404
# ===================================================================


class TestNonMemberWorkspace:
    """Authenticated user accessing a workspace they are NOT a member of."""

    @pytest.mark.anyio
    async def test_non_member_get_workspace_returns_404(
        self,
        unauthed_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """User is authenticated but not a member of this workspace."""
        # Seed workspace owned by admin, no analyst membership
        await _seed_workspace_and_membership(
            db_session, DEV_WS_ID, ADMIN_USER_ID, "admin",
        )

        token = await _login(unauthed_client, "analyst")
        resp = await unauthed_client.get(
            f"/v1/workspaces/{DEV_WS_ID}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_non_member_documents_returns_404(
        self,
        unauthed_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        await _seed_workspace_and_membership(
            db_session, DEV_WS_ID, ADMIN_USER_ID, "admin",
        )

        token = await _login(unauthed_client, "analyst")
        resp = await unauthed_client.get(
            f"/v1/workspaces/{DEV_WS_ID}/documents",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404


# ===================================================================
# S10-2: Member workspace → 200
# ===================================================================


class TestMemberWorkspace:
    """Authenticated user who IS a member of the workspace."""

    @pytest.mark.anyio
    async def test_member_get_workspace_returns_200(
        self,
        unauthed_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        await _seed_workspace_and_membership(
            db_session, DEV_WS_ID, ANALYST_USER_ID, "analyst",
        )

        token = await _login(unauthed_client, "analyst")
        resp = await unauthed_client.get(
            f"/v1/workspaces/{DEV_WS_ID}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200


# ===================================================================
# S10-2: Insufficient role → 403
# ===================================================================


class TestInsufficientRole:
    """Authenticated member with wrong role for sensitive action."""

    @pytest.mark.anyio
    async def test_analyst_cannot_update_workspace_403(
        self,
        unauthed_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        """Analyst role cannot mutate workspace — requires manager+."""
        await _seed_workspace_and_membership(
            db_session, DEV_WS_ID, ANALYST_USER_ID, "analyst",
        )

        token = await _login(unauthed_client, "analyst")
        resp = await unauthed_client.put(
            f"/v1/workspaces/{DEV_WS_ID}",
            headers={"Authorization": f"Bearer {token}"},
            json={"client_name": "Hacked"},
        )
        assert resp.status_code == 403


# ===================================================================
# S10-2: Authorized role succeeds
# ===================================================================


class TestAuthorizedRole:
    """Authenticated member with sufficient role."""

    @pytest.mark.anyio
    async def test_manager_can_update_workspace_200(
        self,
        unauthed_client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        await _seed_workspace_and_membership(
            db_session, DEV_WS_ID, MANAGER_USER_ID, "manager",
        )

        token = await _login(unauthed_client, "manager")
        resp = await unauthed_client.put(
            f"/v1/workspaces/{DEV_WS_ID}",
            headers={"Authorization": f"Bearer {token}"},
            json={"client_name": "Updated"},
        )
        assert resp.status_code == 200


# ===================================================================
# S10-2: created_by from principal, not body
# ===================================================================


class TestCreatedByFromPrincipal:
    """Workspace creation sets created_by from authenticated principal."""

    @pytest.mark.anyio
    async def test_created_by_is_principal_user_id(
        self,
        unauthed_client: AsyncClient,
    ) -> None:
        token = await _login(unauthed_client, "analyst")
        resp = await unauthed_client.post(
            "/v1/workspaces",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "client_name": "New WS",
                "engagement_code": "ENG-NEW",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["created_by"] == str(ANALYST_USER_ID)
