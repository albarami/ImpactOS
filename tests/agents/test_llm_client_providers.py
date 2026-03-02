"""Tests for LLM provider adapter execution path (Sprint 9, S9-1).

Covers: real provider call dispatch via LLMClient.call(), normalized
LLMResponse from each provider, retry on failure, deterministic
LOCAL path, ProviderUnavailableError when all retries exhausted.

All provider SDK calls are mocked — no network dependency in tests.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from src.agents.llm_client import (
    LLMClient,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    ProviderUnavailableError,
    TokenUsage,
)
from src.models.common import DataClassification


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class MockSchema(BaseModel):
    sector_code: str
    confidence: float


def _make_request() -> LLMRequest:
    return LLMRequest(
        system_prompt="You are a mapping assistant.",
        user_prompt="Map: concrete works",
        output_schema=MockSchema,
        max_tokens=256,
    )


# ===================================================================
# S9-1: LOCAL provider adapter
# ===================================================================


class TestLocalProviderAdapter:
    """LOCAL provider returns deterministic, schema-valid LLMResponse."""

    @pytest.mark.anyio
    async def test_call_local_returns_normalized_response(self) -> None:
        """LOCAL adapter returns LLMResponse with all required fields."""
        client = LLMClient()
        request = _make_request()
        response = await client.call(request, classification=DataClassification.RESTRICTED)

        assert isinstance(response, LLMResponse)
        assert response.provider == LLMProvider.LOCAL
        assert response.model == "local-deterministic"
        assert isinstance(response.parsed, MockSchema)
        assert isinstance(response.usage, TokenUsage)

    @pytest.mark.anyio
    async def test_local_works_without_keys(self) -> None:
        """LOCAL needs no API keys or network."""
        client = LLMClient(anthropic_key="", openai_key="", openrouter_key="")
        request = _make_request()
        response = await client.call(request, classification=DataClassification.RESTRICTED)

        assert response.provider == LLMProvider.LOCAL
        assert response.usage.total_tokens == 0

    @pytest.mark.anyio
    async def test_local_response_passes_schema_validation(self) -> None:
        """LOCAL output is valid against the requested schema."""
        client = LLMClient()
        request = _make_request()
        response = await client.call(request, classification=DataClassification.RESTRICTED)

        assert hasattr(response.parsed, "sector_code")
        assert hasattr(response.parsed, "confidence")
        assert 0.0 <= response.parsed.confidence <= 1.0


# ===================================================================
# S9-1: Anthropic provider adapter
# ===================================================================


class TestAnthropicProviderAdapter:
    """Anthropic adapter returns normalized LLMResponse via mocked SDK."""

    @pytest.mark.anyio
    async def test_call_anthropic_returns_normalized_response(self) -> None:
        """Mocked Anthropic SDK call returns normalized LLMResponse."""
        client = LLMClient(anthropic_key="sk-ant-test")

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"sector_code": "F", "confidence": 0.92}')]
        mock_response.model = "claude-sonnet-4-20250514"
        mock_response.usage = MagicMock(input_tokens=50, output_tokens=30)

        with patch.object(client, "_call_anthropic", new_callable=AsyncMock, return_value=mock_response):
            response = await client.call(
                _make_request(),
                classification=DataClassification.CONFIDENTIAL,
            )

        assert isinstance(response, LLMResponse)
        assert response.provider == LLMProvider.ANTHROPIC
        assert isinstance(response.parsed, MockSchema)
        assert response.parsed.sector_code == "F"


# ===================================================================
# S9-1: OpenAI provider adapter
# ===================================================================


class TestOpenAIProviderAdapter:
    """OpenAI adapter returns normalized LLMResponse via mocked SDK."""

    @pytest.mark.anyio
    async def test_call_openai_returns_normalized_response(self) -> None:
        """Mocked OpenAI SDK call returns normalized LLMResponse."""
        # Use custom routing: INTERNAL→OPENAI to test the OpenAI adapter path
        routing = {
            DataClassification.RESTRICTED: LLMProvider.LOCAL,
            DataClassification.CONFIDENTIAL: LLMProvider.ANTHROPIC,
            DataClassification.INTERNAL: LLMProvider.OPENAI,
            DataClassification.PUBLIC: LLMProvider.OPENROUTER,
        }
        client = LLMClient(openai_key="sk-oai-test", routing_table=routing)

        mock_choice = MagicMock()
        mock_choice.message = MagicMock(content='{"sector_code": "H", "confidence": 0.85}')
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_response.model = "gpt-4o"
        mock_response.usage = MagicMock(prompt_tokens=40, completion_tokens=25)

        with patch.object(client, "_call_openai", new_callable=AsyncMock, return_value=mock_response):
            response = await client.call(
                _make_request(),
                classification=DataClassification.INTERNAL,
            )

        assert isinstance(response, LLMResponse)
        assert response.provider == LLMProvider.OPENAI
        assert isinstance(response.parsed, MockSchema)
        assert response.parsed.sector_code == "H"


# ===================================================================
# S9-1: OpenRouter provider adapter
# ===================================================================


class TestOpenRouterProviderAdapter:
    """OpenRouter adapter returns normalized LLMResponse via mocked httpx."""

    @pytest.mark.anyio
    async def test_call_openrouter_returns_normalized_response(self) -> None:
        """Mocked httpx call returns normalized LLMResponse."""
        client = LLMClient(openrouter_key="sk-or-test")

        mock_json = {
            "choices": [{"message": {"content": '{"sector_code": "J", "confidence": 0.78}'}}],
            "model": "openrouter/auto",
            "usage": {"prompt_tokens": 35, "completion_tokens": 20},
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = mock_json
        mock_resp.raise_for_status = MagicMock()

        with patch.object(client, "_call_openrouter", new_callable=AsyncMock, return_value=mock_resp):
            response = await client.call(
                _make_request(),
                classification=DataClassification.PUBLIC,
            )

        assert isinstance(response, LLMResponse)
        assert response.provider == LLMProvider.OPENROUTER
        assert isinstance(response.parsed, MockSchema)
        assert response.parsed.sector_code == "J"


# ===================================================================
# S9-1: Retry behavior
# ===================================================================


class TestRetryBehavior:
    """Provider call failure triggers retry policy."""

    @pytest.mark.anyio
    async def test_call_retries_on_provider_failure(self) -> None:
        """Provider fails twice, succeeds on third attempt."""
        client = LLMClient(anthropic_key="sk-ant-test", max_retries=3, base_delay=0.0)

        call_count = 0

        async def flaky_call(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("transient failure")
            mock = MagicMock()
            mock.content = [MagicMock(text='{"sector_code": "F", "confidence": 0.9}')]
            mock.model = "claude-sonnet-4-20250514"
            mock.usage = MagicMock(input_tokens=50, output_tokens=30)
            return mock

        with patch.object(client, "_call_anthropic", side_effect=flaky_call):
            response = await client.call(
                _make_request(),
                classification=DataClassification.CONFIDENTIAL,
            )

        assert call_count == 3
        assert isinstance(response, LLMResponse)

    @pytest.mark.anyio
    async def test_call_all_retries_exhausted_raises(self) -> None:
        """All retries fail → ProviderUnavailableError."""
        client = LLMClient(anthropic_key="sk-ant-test", max_retries=3, base_delay=0.0)

        async def always_fail(*args, **kwargs):
            raise ConnectionError("persistent failure")

        with patch.object(client, "_call_anthropic", side_effect=always_fail):
            with pytest.raises(ProviderUnavailableError):
                await client.call(
                    _make_request(),
                    classification=DataClassification.CONFIDENTIAL,
                )
