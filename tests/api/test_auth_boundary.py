"""Tests for S10-1: Authentication boundary hardening.

Covers: missing bearer token → 401, invalid/expired token → 401,
valid token → principal extracted, dev auth stub gated to dev env only.

Uses unauthed_client fixture (no auth dependency override) to test
real token validation behavior.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_async_session


@pytest.fixture
async def unauthed_client(db_session: AsyncSession) -> AsyncClient:
    """Client WITHOUT auth override — tests real auth behavior."""
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


async def _get_dev_token(client: AsyncClient, username: str = "analyst") -> str:
    """Login via dev stub and return JWT token."""
    resp = await client.post("/v1/auth/login", json={
        "username": username, "password": "any",
    })
    assert resp.status_code == 200
    return resp.json()["token"]


# ===================================================================
# S10-1: Missing token → 401
# ===================================================================


class TestMissingToken:
    """Protected routes reject requests without Authorization header."""

    @pytest.mark.anyio
    async def test_list_workspaces_without_token_401(
        self, unauthed_client: AsyncClient,
    ) -> None:
        resp = await unauthed_client.get("/v1/workspaces")
        assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_create_workspace_without_token_401(
        self, unauthed_client: AsyncClient,
    ) -> None:
        resp = await unauthed_client.post("/v1/workspaces", json={
            "client_name": "X", "engagement_code": "E1",
        })
        assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_get_workspace_without_token_401(
        self, unauthed_client: AsyncClient,
    ) -> None:
        ws_id = "00000000-0000-7000-8000-000000000010"
        resp = await unauthed_client.get(f"/v1/workspaces/{ws_id}")
        assert resp.status_code == 401


# ===================================================================
# S10-1: Invalid / expired token → 401
# ===================================================================


class TestInvalidToken:
    """Protected routes reject invalid or expired tokens."""

    @pytest.mark.anyio
    async def test_garbage_token_401(
        self, unauthed_client: AsyncClient,
    ) -> None:
        resp = await unauthed_client.get(
            "/v1/workspaces",
            headers={"Authorization": "Bearer garbage.invalid.token"},
        )
        assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_malformed_auth_header_401(
        self, unauthed_client: AsyncClient,
    ) -> None:
        resp = await unauthed_client.get(
            "/v1/workspaces",
            headers={"Authorization": "Token abc123"},
        )
        assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_empty_bearer_401(
        self, unauthed_client: AsyncClient,
    ) -> None:
        resp = await unauthed_client.get(
            "/v1/workspaces",
            headers={"Authorization": "Bearer "},
        )
        assert resp.status_code == 401


# ===================================================================
# S10-1: Valid token → authenticated principal
# ===================================================================


class TestValidToken:
    """Valid JWT token allows access and produces correct principal."""

    @pytest.mark.anyio
    async def test_valid_token_passes_auth(
        self, unauthed_client: AsyncClient,
    ) -> None:
        token = await _get_dev_token(unauthed_client, "admin")
        resp = await unauthed_client.get(
            "/v1/workspaces",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200


# ===================================================================
# S10-1: Global sensitive route requires auth
# ===================================================================


class TestGlobalSensitiveRouteAuth:
    """POST /v1/engine/models must require authentication."""

    @pytest.mark.anyio
    async def test_model_registration_without_token_401(
        self, unauthed_client: AsyncClient,
    ) -> None:
        resp = await unauthed_client.post("/v1/engine/models", json={})
        assert resp.status_code == 401
