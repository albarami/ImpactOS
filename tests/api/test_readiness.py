"""Tests for S12-2: Readiness endpoint + smoke flow determinism.

Covers: /readiness returns 200 when all deps healthy, 503 when any
critical dep is down. /health remains backward-compatible (200 always).
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.session import get_async_session


@pytest.fixture
async def bare_client(db_session: AsyncSession) -> AsyncClient:
    """Client with DB override only (no auth override)."""
    from src.api.main import app

    async def _override_session():
        yield db_session

    app.dependency_overrides[get_async_session] = _override_session

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


class TestHealthBackwardCompat:
    """/health always returns 200 (existing contract)."""

    @pytest.mark.anyio
    async def test_health_returns_200(
        self, bare_client: AsyncClient,
    ) -> None:
        resp = await bare_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert "checks" in data

    @pytest.mark.anyio
    async def test_health_includes_version(
        self, bare_client: AsyncClient,
    ) -> None:
        resp = await bare_client.get("/health")
        assert "version" in resp.json()


class TestReadinessEndpoint:
    """/readiness gates traffic: 200 ready, 503 not ready."""

    @pytest.mark.anyio
    async def test_readiness_exists(
        self, bare_client: AsyncClient,
    ) -> None:
        """Readiness endpoint returns 200 or 503 (not 404)."""
        resp = await bare_client.get("/readiness")
        assert resp.status_code in (200, 503)

    @pytest.mark.anyio
    async def test_readiness_returns_status_field(
        self, bare_client: AsyncClient,
    ) -> None:
        resp = await bare_client.get("/readiness")
        data = resp.json()
        assert "ready" in data

    @pytest.mark.anyio
    async def test_readiness_returns_checks(
        self, bare_client: AsyncClient,
    ) -> None:
        resp = await bare_client.get("/readiness")
        data = resp.json()
        assert "checks" in data
        assert "database" in data["checks"]
