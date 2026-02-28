"""Tests for FastAPI health and version endpoints.

S0-4: Enhanced health check with DB connectivity and component checks.
"""

import pytest
from httpx import AsyncClient


class TestHealthEndpoint:
    """GET /health returns status with component checks."""

    @pytest.mark.anyio
    async def test_health_returns_200(self, client: AsyncClient) -> None:
        response = await client.get("/health")
        assert response.status_code == 200

    @pytest.mark.anyio
    async def test_health_response_body(self, client: AsyncClient) -> None:
        response = await client.get("/health")
        data = response.json()
        # Status may be "ok" or "degraded" depending on DB connectivity in tests
        assert data["status"] in ("ok", "degraded")
        assert "environment" in data
        assert "version" in data
        assert "checks" in data
        assert data["checks"]["api"] is True


class TestVersionEndpoint:
    """GET /api/version returns application version info."""

    @pytest.mark.anyio
    async def test_version_returns_200(self, client: AsyncClient) -> None:
        response = await client.get("/api/version")
        assert response.status_code == 200

    @pytest.mark.anyio
    async def test_version_response_body(self, client: AsyncClient) -> None:
        response = await client.get("/api/version")
        data = response.json()
        assert data["name"] == "ImpactOS"
        assert "version" in data
        assert "environment" in data
