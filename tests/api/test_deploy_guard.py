"""Tests for S11-4: Deploy guard evidence and operational guardrails.

Covers: missing non-dev IdP settings → fail-closed 401, auth logging
with decision metadata, secret redaction. Maps to Issue #13 requirements.
"""

import logging
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_async_session
from src.db.tables import WorkspaceRow
from src.models.common import utc_now

ANALYST_ID = UUID("00000000-0000-7000-8000-000000000001")
WS = UUID("00000000-0000-7000-8000-000000000010")


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


def _staging_settings_factory(**overrides):
    """Build a settings factory for staging env with custom overrides."""
    from src.config import settings as settings_mod

    original = settings_mod.get_settings

    def _factory():
        s = original()
        object.__setattr__(s, "ENVIRONMENT", "staging")
        for k, v in overrides.items():
            object.__setattr__(s, k, v)
        return s

    return _factory


# ===================================================================
# S11-4: Missing IdP settings → fail-closed
# ===================================================================


class TestMissingIdPSettingsFailClosed:
    """Non-dev with missing JWT_ISSUER/JWT_AUDIENCE/JWKS_URL → 401."""

    @pytest.mark.anyio
    async def test_missing_jwks_url_401(
        self, unauthed_client: AsyncClient, monkeypatch,
    ) -> None:
        factory = _staging_settings_factory(
            JWKS_URL="", JWT_ISSUER="x", JWT_AUDIENCE="y",
        )
        monkeypatch.setattr("src.config.settings.get_settings", factory)
        monkeypatch.setattr("src.api.auth_deps.get_settings", factory)

        resp = await unauthed_client.get(
            "/v1/workspaces",
            headers={"Authorization": "Bearer some.token.here"},
        )
        assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_missing_issuer_401(
        self, unauthed_client: AsyncClient, monkeypatch,
    ) -> None:
        factory = _staging_settings_factory(
            JWKS_URL="https://x", JWT_ISSUER="", JWT_AUDIENCE="y",
        )
        monkeypatch.setattr("src.config.settings.get_settings", factory)
        monkeypatch.setattr("src.api.auth_deps.get_settings", factory)

        resp = await unauthed_client.get(
            "/v1/workspaces",
            headers={"Authorization": "Bearer some.token.here"},
        )
        assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_missing_audience_401(
        self, unauthed_client: AsyncClient, monkeypatch,
    ) -> None:
        factory = _staging_settings_factory(
            JWKS_URL="https://x", JWT_ISSUER="x", JWT_AUDIENCE="",
        )
        monkeypatch.setattr("src.config.settings.get_settings", factory)
        monkeypatch.setattr("src.api.auth_deps.get_settings", factory)

        resp = await unauthed_client.get(
            "/v1/workspaces",
            headers={"Authorization": "Bearer some.token.here"},
        )
        assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_missing_all_three_401(
        self, unauthed_client: AsyncClient, monkeypatch,
    ) -> None:
        factory = _staging_settings_factory(
            JWKS_URL="", JWT_ISSUER="", JWT_AUDIENCE="",
        )
        monkeypatch.setattr("src.config.settings.get_settings", factory)
        monkeypatch.setattr("src.api.auth_deps.get_settings", factory)

        resp = await unauthed_client.get(
            "/v1/workspaces",
            headers={"Authorization": "Bearer some.token.here"},
        )
        assert resp.status_code == 401


# ===================================================================
# S11-4: Auth decision logging
# ===================================================================


class TestAuthDecisionLogging:

    @pytest.mark.anyio
    async def test_missing_config_logged(
        self,
        unauthed_client: AsyncClient,
        monkeypatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        factory = _staging_settings_factory(
            JWKS_URL="", JWT_ISSUER="", JWT_AUDIENCE="",
        )
        monkeypatch.setattr("src.config.settings.get_settings", factory)
        monkeypatch.setattr("src.api.auth_deps.get_settings", factory)

        with caplog.at_level(logging.ERROR, logger="src.api.auth_deps"):
            await unauthed_client.get(
                "/v1/workspaces",
                headers={"Authorization": "Bearer tok"},
            )

        assert "JWKS_URL" in caplog.text
        assert "JWT_ISSUER" in caplog.text
        assert "JWT_AUDIENCE" in caplog.text


# ===================================================================
# S11-4: Token/secret redaction in logs
# ===================================================================


class TestTokenRedactionInLogs:

    @pytest.mark.anyio
    async def test_token_not_in_deny_logs(
        self,
        unauthed_client: AsyncClient,
        db_session: AsyncSession,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        now = utc_now()
        db_session.add(WorkspaceRow(
            workspace_id=WS, client_name="T", engagement_code="E",
            classification="CONFIDENTIAL", description="",
            created_by=ANALYST_ID, created_at=now, updated_at=now,
        ))
        await db_session.flush()

        login_resp = await unauthed_client.post(
            "/v1/auth/login",
            json={"username": "analyst", "password": "any"},
        )
        token = login_resp.json()["token"]

        with caplog.at_level(logging.DEBUG, logger="src.api.auth_deps"):
            await unauthed_client.get(
                f"/v1/workspaces/{WS}",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert token not in caplog.text
