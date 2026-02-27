"""Tests for FastAPI health and version endpoints."""

import pytest
from httpx import AsyncClient


class TestHealthEndpoint:
    """GET /health returns status ok."""

    @pytest.mark.anyio
    async def test_health_returns_200(self, client: AsyncClient) -> None:
        response = await client.get("/health")
        assert response.status_code == 200

    @pytest.mark.anyio
    async def test_health_response_body(self, client: AsyncClient) -> None:
        response = await client.get("/health")
        data = response.json()
        assert data["status"] == "ok"
        assert "environment" in data


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
