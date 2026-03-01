"""Tests for G4: /health must check DB + Redis + object storage.

Currently /health only returns checks for "api" and "database".
These tests verify that the checks dict also includes "redis" and
"object_storage" keys.

These tests will FAIL until src/api/main.py health_check() is updated
to probe Redis and object storage connectivity.
"""

import pytest
from httpx import AsyncClient


class TestHealthDependencies:
    """G4: /health must check DB + Redis + object storage."""

    @pytest.mark.anyio
    async def test_health_includes_all_check_keys(self, client: AsyncClient) -> None:
        """GET /health checks dict must contain api, database, redis, object_storage."""
        response = await client.get("/health")
        assert response.status_code == 200

        data = response.json()
        checks = data["checks"]

        required_keys = {"api", "database", "redis", "object_storage"}
        missing = required_keys - set(checks.keys())
        assert not missing, f"Missing health check keys: {missing}"

    @pytest.mark.anyio
    async def test_health_object_storage_check_present(self, client: AsyncClient) -> None:
        """GET /health checks dict must have 'object_storage' key."""
        response = await client.get("/health")
        assert response.status_code == 200

        data = response.json()
        checks = data["checks"]

        assert "object_storage" in checks, (
            "Health check missing 'object_storage' key. "
            f"Current keys: {list(checks.keys())}"
        )

    @pytest.mark.anyio
    async def test_health_redis_check_present(self, client: AsyncClient) -> None:
        """GET /health checks dict must have 'redis' key."""
        response = await client.get("/health")
        assert response.status_code == 200

        data = response.json()
        checks = data["checks"]

        assert "redis" in checks, (
            "Health check missing 'redis' key. "
            f"Current keys: {list(checks.keys())}"
        )
