"""Tests for classification-based provider routing policy (Sprint 9, S9-2).

Covers: strict classification enforcement — RESTRICTED never reaches
external providers, CONFIDENTIAL/INTERNAL require enterprise keys,
PUBLIC uses configured non-enterprise path. Missing keys produce
ProviderUnavailableError, not silent success.

All provider SDK calls are mocked — no network dependency.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from src.agents.llm_client import (
    LLMClient,
    LLMProvider,
    LLMRequest,
    ProviderUnavailableError,
)
from src.models.common import DataClassification

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class PolicySchema(BaseModel):
    sector_code: str
    confidence: float


def _make_request() -> LLMRequest:
    return LLMRequest(
        system_prompt="You are a test assistant.",
        user_prompt="Test prompt",
        output_schema=PolicySchema,
    )


def _mock_anthropic_response():
    mock = MagicMock()
    mock.content = [MagicMock(text='{"sector_code": "F", "confidence": 0.9}')]
    mock.model = "claude-sonnet-4-20250514"
    mock.usage = MagicMock(input_tokens=10, output_tokens=10)
    return mock


def _mock_openrouter_response():
    mock = MagicMock()
    mock.json.return_value = {
        "choices": [{"message": {"content": '{"sector_code": "F", "confidence": 0.8}'}}],
        "model": "openrouter/auto",
        "usage": {"prompt_tokens": 10, "completion_tokens": 10},
    }
    mock.raise_for_status = MagicMock()
    return mock


# ===================================================================
# S9-2: RESTRICTED classification — hard enforcement
# ===================================================================


class TestRestrictedPolicy:
    """RESTRICTED data must NEVER reach external providers."""

    @pytest.mark.anyio
    async def test_restricted_rejects_external_provider(self) -> None:
        """RESTRICTED classification with cloud-capable keys still uses LOCAL only."""
        client = LLMClient(
            anthropic_key="sk-ant-test",
            openai_key="sk-oai-test",
            openrouter_key="sk-or-test",
        )
        response = await client.call(
            _make_request(),
            classification=DataClassification.RESTRICTED,
        )
        assert response.provider == LLMProvider.LOCAL

    @pytest.mark.anyio
    async def test_restricted_never_calls_anthropic(self) -> None:
        """Even with valid Anthropic key, RESTRICTED never dispatches to Anthropic."""
        client = LLMClient(anthropic_key="sk-ant-test")

        with patch.object(client, "_call_anthropic", new_callable=AsyncMock) as mock_call:
            await client.call(
                _make_request(),
                classification=DataClassification.RESTRICTED,
            )
            mock_call.assert_not_called()

    @pytest.mark.anyio
    async def test_restricted_routes_to_local_only(self) -> None:
        """RESTRICTED → LOCAL always succeeds regardless of key availability."""
        client = LLMClient()
        response = await client.call(
            _make_request(),
            classification=DataClassification.RESTRICTED,
        )
        assert response.provider == LLMProvider.LOCAL
        assert isinstance(response.parsed, PolicySchema)


# ===================================================================
# S9-2: CONFIDENTIAL/INTERNAL — enterprise provider required
# ===================================================================


class TestConfidentialPolicy:
    """CONFIDENTIAL requires enterprise provider (Anthropic/OpenAI)."""

    @pytest.mark.anyio
    async def test_confidential_requires_enterprise_key(self) -> None:
        """CONFIDENTIAL with no enterprise keys → ProviderUnavailableError."""
        client = LLMClient(anthropic_key="", openai_key="", openrouter_key="sk-or-test")
        with pytest.raises(ProviderUnavailableError):
            await client.call(
                _make_request(),
                classification=DataClassification.CONFIDENTIAL,
            )

    @pytest.mark.anyio
    async def test_confidential_routes_to_anthropic(self) -> None:
        """CONFIDENTIAL + Anthropic key → Anthropic provider used."""
        client = LLMClient(anthropic_key="sk-ant-test")

        with patch.object(
            client, "_call_anthropic",
            new_callable=AsyncMock,
            return_value=_mock_anthropic_response(),
        ):
            response = await client.call(
                _make_request(),
                classification=DataClassification.CONFIDENTIAL,
            )

        assert response.provider == LLMProvider.ANTHROPIC


class TestInternalPolicy:
    """INTERNAL follows same policy as CONFIDENTIAL."""

    @pytest.mark.anyio
    async def test_internal_requires_enterprise_key(self) -> None:
        """INTERNAL with no enterprise keys → ProviderUnavailableError."""
        client = LLMClient(anthropic_key="", openai_key="", openrouter_key="sk-or-test")
        with pytest.raises(ProviderUnavailableError):
            await client.call(
                _make_request(),
                classification=DataClassification.INTERNAL,
            )

    @pytest.mark.anyio
    async def test_internal_routes_to_anthropic(self) -> None:
        """INTERNAL + Anthropic key → Anthropic provider used."""
        client = LLMClient(anthropic_key="sk-ant-test")

        with patch.object(
            client, "_call_anthropic",
            new_callable=AsyncMock,
            return_value=_mock_anthropic_response(),
        ):
            response = await client.call(
                _make_request(),
                classification=DataClassification.INTERNAL,
            )

        assert response.provider == LLMProvider.ANTHROPIC


# ===================================================================
# S9-2: PUBLIC — non-enterprise provider path
# ===================================================================


class TestPublicPolicy:
    """PUBLIC uses configured non-enterprise provider path."""

    @pytest.mark.anyio
    async def test_public_routes_to_openrouter(self) -> None:
        """PUBLIC + OpenRouter key → OpenRouter provider used."""
        client = LLMClient(openrouter_key="sk-or-test")

        with patch.object(
            client, "_call_openrouter",
            new_callable=AsyncMock,
            return_value=_mock_openrouter_response(),
        ):
            response = await client.call(
                _make_request(),
                classification=DataClassification.PUBLIC,
            )

        assert response.provider == LLMProvider.OPENROUTER

    @pytest.mark.anyio
    async def test_public_fails_when_no_key(self) -> None:
        """PUBLIC + no OpenRouter key → ProviderUnavailableError."""
        client = LLMClient(anthropic_key="", openai_key="", openrouter_key="")
        with pytest.raises(ProviderUnavailableError):
            await client.call(
                _make_request(),
                classification=DataClassification.PUBLIC,
            )
