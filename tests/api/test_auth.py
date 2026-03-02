"""Tests for B-13: Auth dev stub."""

import pytest
from httpx import AsyncClient

from src.api.auth import _revoked_tokens


@pytest.fixture(autouse=True)
def _clear_revoked_tokens() -> None:
    """Clear the in-memory token denylist between tests.

    Tokens generated within the same second with the same payload
    are identical, so a revocation from a prior test can leak.
    """
    _revoked_tokens.clear()


class TestLogin:
    @pytest.mark.anyio
    async def test_login_analyst(self, client: AsyncClient) -> None:
        resp = await client.post("/v1/auth/login", json={
            "username": "analyst",
            "password": "any",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "analyst"
        assert data["role"] == "analyst"
        assert "token" in data
        assert "user_id" in data
        assert data["user_id"] == "00000000-0000-7000-8000-000000000001"
        assert "workspace_ids" in data

    @pytest.mark.anyio
    async def test_login_manager(self, client: AsyncClient) -> None:
        resp = await client.post("/v1/auth/login", json={
            "username": "manager",
            "password": "any",
        })
        assert resp.status_code == 200
        assert resp.json()["role"] == "manager"

    @pytest.mark.anyio
    async def test_login_admin(self, client: AsyncClient) -> None:
        resp = await client.post("/v1/auth/login", json={
            "username": "admin",
            "password": "any",
        })
        assert resp.status_code == 200
        assert resp.json()["role"] == "admin"

    @pytest.mark.anyio
    async def test_login_unknown_user(self, client: AsyncClient) -> None:
        resp = await client.post("/v1/auth/login", json={
            "username": "nobody",
            "password": "any",
        })
        assert resp.status_code == 401


class TestMe:
    @pytest.mark.anyio
    async def test_me_with_valid_token(self, client: AsyncClient) -> None:
        login_resp = await client.post("/v1/auth/login", json={
            "username": "analyst",
            "password": "any",
        })
        token = login_resp.json()["token"]
        resp = await client.get(
            "/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "analyst"
        assert data["role"] == "analyst"

    @pytest.mark.anyio
    async def test_me_without_token(self, client: AsyncClient) -> None:
        resp = await client.get("/v1/auth/me")
        assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_me_with_invalid_token(self, client: AsyncClient) -> None:
        resp = await client.get(
            "/v1/auth/me",
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert resp.status_code == 401


class TestLogout:
    @pytest.mark.anyio
    async def test_logout_invalidates_token(self, client: AsyncClient) -> None:
        login_resp = await client.post("/v1/auth/login", json={
            "username": "analyst",
            "password": "any",
        })
        token = login_resp.json()["token"]

        logout_resp = await client.post(
            "/v1/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert logout_resp.status_code == 200

        me_resp = await client.get(
            "/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me_resp.status_code == 401
