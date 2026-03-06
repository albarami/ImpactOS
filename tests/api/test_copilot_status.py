"""Tests for GET /api/copilot/status — copilot runtime readiness probe.

This endpoint exercises _build_copilot() and reports whether the
copilot runtime can be constructed from current settings.  It is
unauthenticated (a health-style probe for staging smoke tests).
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from unittest.mock import patch, MagicMock


class TestCopilotStatusEndpoint:
    """GET /api/copilot/status returns copilot runtime readiness."""

    @pytest.mark.anyio
    async def test_copilot_status_returns_200(self, client: AsyncClient) -> None:
        """Endpoint exists and returns 200."""
        response = await client.get("/api/copilot/status")
        assert response.status_code == 200

    @pytest.mark.anyio
    async def test_copilot_status_has_required_fields(self, client: AsyncClient) -> None:
        """Response contains enabled, ready, providers, and detail."""
        response = await client.get("/api/copilot/status")
        data = response.json()

        assert "enabled" in data
        assert "ready" in data
        assert "providers" in data
        assert "detail" in data
        assert isinstance(data["enabled"], bool)
        assert isinstance(data["ready"], bool)
        assert isinstance(data["providers"], list)

    @pytest.mark.anyio
    async def test_copilot_disabled_returns_not_ready(self, client: AsyncClient) -> None:
        """When COPILOT_ENABLED=false, enabled=false and ready=false."""
        import src.api.main as main_mod

        original = main_mod.settings.COPILOT_ENABLED
        try:
            main_mod.settings.COPILOT_ENABLED = False
            response = await client.get("/api/copilot/status")
            data = response.json()

            assert data["enabled"] is False
            assert data["ready"] is False
        finally:
            main_mod.settings.COPILOT_ENABLED = original

    @pytest.mark.anyio
    async def test_copilot_enabled_reports_provider_availability(
        self, client: AsyncClient
    ) -> None:
        """When enabled, providers list reflects actual key availability."""
        response = await client.get("/api/copilot/status")
        data = response.json()

        if data["enabled"] and data["ready"]:
            # Should have at least one provider
            assert len(data["providers"]) > 0
