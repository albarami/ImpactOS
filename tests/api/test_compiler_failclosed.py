"""Tests for Issue #17: compile endpoint non-dev fail-closed wiring.

Verifies that trigger_compilation passes real environment/llm_client/classification
to AICompiler, and translates ProviderUnavailableError to 503 with structured detail.
"""

from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient
from uuid_extensions import uuid7


@pytest.fixture
def workspace_id() -> str:
    return str(uuid7())


class TestCompileEndpointFailClosed:
    """Compile endpoint returns 503 with reason_code when fail-closed triggers."""

    @pytest.mark.anyio
    async def test_non_dev_compile_returns_503_with_reason_code(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """Non-dev compile hitting split guard returns 503 with structured detail."""
        with patch("src.api.compiler.get_settings") as mock_settings:
            mock_s = MagicMock()
            mock_s.ENVIRONMENT.value = "staging"
            mock_s.ANTHROPIC_API_KEY = ""
            mock_s.OPENAI_API_KEY = ""
            mock_s.OPENROUTER_API_KEY = ""
            mock_settings.return_value = mock_s

            resp = await client.post(
                f"/v1/workspaces/{workspace_id}/compiler/compile",
                json={
                    "scenario_name": "Test",
                    "base_model_version_id": str(uuid7()),
                    "base_year": 2020,
                    "start_year": 2025,
                    "end_year": 2030,
                    "line_items": [
                        {
                            "line_item_id": str(uuid7()),
                            "raw_text": "concrete works",
                            "total_value": 1000000,
                        },
                    ],
                },
            )

        assert resp.status_code == 503
        detail = resp.json()["detail"]
        assert "reason_code" in detail
        assert detail["reason_code"] in (
            "SPLIT_NO_LLM_BACKING",
            "ASSUMPTION_NO_LLM_BACKING",
            "PROVIDER_UNAVAILABLE",
        )
        assert "agent_name" in detail
        assert "environment" in detail

    @pytest.mark.anyio
    async def test_503_detail_contains_no_secrets(
        self, client: AsyncClient, workspace_id: str,
    ) -> None:
        """503 response must not leak API keys or tokens."""
        with patch("src.api.compiler.get_settings") as mock_settings:
            mock_s = MagicMock()
            mock_s.ENVIRONMENT.value = "staging"
            mock_s.ANTHROPIC_API_KEY = "sk-ant-secret123"
            mock_s.OPENAI_API_KEY = "sk-openai-secret456"
            mock_s.OPENROUTER_API_KEY = ""
            mock_settings.return_value = mock_s

            resp = await client.post(
                f"/v1/workspaces/{workspace_id}/compiler/compile",
                json={
                    "scenario_name": "Test",
                    "base_model_version_id": str(uuid7()),
                    "base_year": 2020,
                    "start_year": 2025,
                    "end_year": 2030,
                    "line_items": [
                        {
                            "line_item_id": str(uuid7()),
                            "raw_text": "concrete works",
                            "total_value": 1000000,
                        },
                    ],
                },
            )

        body_text = resp.text
        assert "sk-ant" not in body_text
        assert "sk-openai" not in body_text
        assert "secret" not in body_text.lower()
