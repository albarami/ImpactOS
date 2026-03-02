"""Tests for structured output validation and fallback safety (Sprint 9, S9-3).

Covers: invalid JSON from provider never leaks partial content, schema
mismatches are caught before agent consumption, usage is not recorded
for failed calls, and the full call() path rejects bad output
deterministically.

All provider SDK calls are mocked — no network dependency.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from src.agents.llm_client import (
    LLMClient,
    LLMRequest,
    ProviderUnavailableError,
)
from src.models.common import DataClassification

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class StrictSchema(BaseModel):
    sector_code: str
    confidence: float
    explanation: str


def _make_request() -> LLMRequest:
    return LLMRequest(
        system_prompt="You are a mapping assistant.",
        user_prompt="Map: concrete works",
        output_schema=StrictSchema,
        max_tokens=256,
    )


def _mock_anthropic_with_text(text: str) -> MagicMock:
    """Build a mock Anthropic SDK response with the given output text."""
    mock = MagicMock()
    mock.content = [MagicMock(text=text)]
    mock.model = "claude-sonnet-4-20250514"
    mock.usage = MagicMock(input_tokens=10, output_tokens=10)
    return mock


# ===================================================================
# S9-3: Invalid JSON from provider
# ===================================================================


class TestInvalidProviderOutput:
    """Invalid JSON/schema from provider must never produce partial output."""

    @pytest.mark.anyio
    async def test_garbage_text_raises_provider_unavailable(self) -> None:
        """Provider returning garbage text → retries exhausted → ProviderUnavailableError."""
        client = LLMClient(anthropic_key="sk-test", max_retries=2, base_delay=0.0)

        mock_resp = _mock_anthropic_with_text("this is not json at all")

        with patch.object(
            client, "_call_anthropic",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            with pytest.raises(ProviderUnavailableError):
                await client.call(
                    _make_request(),
                    classification=DataClassification.CONFIDENTIAL,
                )

    @pytest.mark.anyio
    async def test_truncated_json_raises_provider_unavailable(self) -> None:
        """Truncated JSON → retries exhausted → ProviderUnavailableError."""
        client = LLMClient(anthropic_key="sk-test", max_retries=2, base_delay=0.0)

        mock_resp = _mock_anthropic_with_text('{"sector_code": "F", "confid')

        with patch.object(
            client, "_call_anthropic",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            with pytest.raises(ProviderUnavailableError):
                await client.call(
                    _make_request(),
                    classification=DataClassification.CONFIDENTIAL,
                )

    @pytest.mark.anyio
    async def test_schema_mismatch_raises_provider_unavailable(self) -> None:
        """Valid JSON but missing required fields → ProviderUnavailableError."""
        client = LLMClient(anthropic_key="sk-test", max_retries=2, base_delay=0.0)

        # Missing 'explanation' field required by StrictSchema
        mock_resp = _mock_anthropic_with_text('{"sector_code": "F", "confidence": 0.9}')

        with patch.object(
            client, "_call_anthropic",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            with pytest.raises(ProviderUnavailableError):
                await client.call(
                    _make_request(),
                    classification=DataClassification.CONFIDENTIAL,
                )

    @pytest.mark.anyio
    async def test_empty_content_raises_provider_unavailable(self) -> None:
        """Provider returning empty string → ProviderUnavailableError."""
        client = LLMClient(anthropic_key="sk-test", max_retries=2, base_delay=0.0)

        mock_resp = _mock_anthropic_with_text("")

        with patch.object(
            client, "_call_anthropic",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            with pytest.raises(ProviderUnavailableError):
                await client.call(
                    _make_request(),
                    classification=DataClassification.CONFIDENTIAL,
                )


# ===================================================================
# S9-3: Usage tracking integrity on failure
# ===================================================================


class TestUsageTrackingOnFailure:
    """Failed calls must not pollute usage tracking."""

    @pytest.mark.anyio
    async def test_failed_call_does_not_record_usage(self) -> None:
        """After ProviderUnavailableError, no usage is recorded."""
        client = LLMClient(anthropic_key="sk-test", max_retries=1, base_delay=0.0)

        mock_resp = _mock_anthropic_with_text("not json")

        with patch.object(
            client, "_call_anthropic",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            with pytest.raises(ProviderUnavailableError):
                await client.call(
                    _make_request(),
                    classification=DataClassification.CONFIDENTIAL,
                )

        assert client.cumulative_usage().total_tokens == 0

    @pytest.mark.anyio
    async def test_successful_call_records_usage(self) -> None:
        """After a successful call, usage is recorded."""
        client = LLMClient(anthropic_key="sk-test")

        valid_json = '{"sector_code": "F", "confidence": 0.9, "explanation": "test"}'
        mock_resp = _mock_anthropic_with_text(valid_json)

        with patch.object(
            client, "_call_anthropic",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            await client.call(
                _make_request(),
                classification=DataClassification.CONFIDENTIAL,
            )

        usage = client.cumulative_usage()
        assert usage.total_tokens == 20  # 10 in + 10 out from mock


# ===================================================================
# S9-3: call() return type guarantee
# ===================================================================


class TestCallReturnTypeGuarantee:
    """call() always returns schema-validated parsed objects or raises."""

    @pytest.mark.anyio
    async def test_successful_call_returns_validated_parsed(self) -> None:
        """Successful call returns LLMResponse with typed parsed object."""
        client = LLMClient(anthropic_key="sk-test")

        valid_json = '{"sector_code": "F", "confidence": 0.9, "explanation": "matched"}'
        mock_resp = _mock_anthropic_with_text(valid_json)

        with patch.object(
            client, "_call_anthropic",
            new_callable=AsyncMock,
            return_value=mock_resp,
        ):
            response = await client.call(
                _make_request(),
                classification=DataClassification.CONFIDENTIAL,
            )

        assert isinstance(response.parsed, StrictSchema)
        assert response.parsed.sector_code == "F"
        assert response.parsed.explanation == "matched"

    @pytest.mark.anyio
    async def test_local_call_returns_validated_parsed(self) -> None:
        """LOCAL path also returns typed, validated parsed object."""
        client = LLMClient()
        response = await client.call(
            _make_request(),
            classification=DataClassification.RESTRICTED,
        )

        assert isinstance(response.parsed, StrictSchema)
        assert isinstance(response.parsed.sector_code, str)
        assert isinstance(response.parsed.confidence, float)
        assert isinstance(response.parsed.explanation, str)
