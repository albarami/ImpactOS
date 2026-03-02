"""Tests for LLM provider observability and telemetry (Sprint 9, S9-4).

Covers: structured logging for provider/model/retry/token metadata,
latency tracking, classification in logs, secret redaction.

All provider SDK calls are mocked — no network dependency.
"""

import logging
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


class ObsSchema(BaseModel):
    sector_code: str
    confidence: float


def _make_request() -> LLMRequest:
    return LLMRequest(
        system_prompt="You are a test assistant.",
        user_prompt="Test prompt",
        output_schema=ObsSchema,
    )


def _mock_anthropic_ok() -> MagicMock:
    mock = MagicMock()
    mock.content = [MagicMock(text='{"sector_code": "F", "confidence": 0.9}')]
    mock.model = "claude-sonnet-4-20250514"
    mock.usage = MagicMock(input_tokens=50, output_tokens=30)
    return mock


# ===================================================================
# S9-4: Structured call telemetry
# ===================================================================


class TestCallTelemetry:
    """call() emits structured telemetry after each invocation."""

    @pytest.mark.anyio
    async def test_successful_call_emits_telemetry(self) -> None:
        """Successful call emits log with provider, model, tokens, classification."""
        client = LLMClient(anthropic_key="sk-ant-secret-key-123")

        with patch.object(
            client, "_call_anthropic",
            new_callable=AsyncMock,
            return_value=_mock_anthropic_ok(),
        ):
            response = await client.call(
                _make_request(),
                classification=DataClassification.CONFIDENTIAL,
            )

        # Response should carry telemetry metadata
        assert response.provider == LLMProvider.ANTHROPIC
        assert response.model == "claude-sonnet-4-20250514"
        assert response.usage.input_tokens == 50
        assert response.usage.output_tokens == 30

    @pytest.mark.anyio
    async def test_call_logs_provider_and_model(self, caplog: pytest.LogCaptureFixture) -> None:
        """Structured log entry contains provider and model after call."""
        client = LLMClient(anthropic_key="sk-ant-test")

        with patch.object(
            client, "_call_anthropic",
            new_callable=AsyncMock,
            return_value=_mock_anthropic_ok(),
        ):
            with caplog.at_level(logging.INFO, logger="src.agents.llm_client"):
                await client.call(
                    _make_request(),
                    classification=DataClassification.CONFIDENTIAL,
                )

        combined = " ".join(caplog.text.split())
        assert "ANTHROPIC" in combined
        assert "claude-sonnet-4-20250514" in combined

    @pytest.mark.anyio
    async def test_call_logs_classification(self, caplog: pytest.LogCaptureFixture) -> None:
        """Log entry includes the data classification level."""
        client = LLMClient(anthropic_key="sk-ant-test")

        with patch.object(
            client, "_call_anthropic",
            new_callable=AsyncMock,
            return_value=_mock_anthropic_ok(),
        ):
            with caplog.at_level(logging.INFO, logger="src.agents.llm_client"):
                await client.call(
                    _make_request(),
                    classification=DataClassification.CONFIDENTIAL,
                )

        combined = " ".join(caplog.text.split())
        assert "CONFIDENTIAL" in combined

    @pytest.mark.anyio
    async def test_call_logs_token_usage(self, caplog: pytest.LogCaptureFixture) -> None:
        """Log entry includes token counts."""
        client = LLMClient(anthropic_key="sk-ant-test")

        with patch.object(
            client, "_call_anthropic",
            new_callable=AsyncMock,
            return_value=_mock_anthropic_ok(),
        ):
            with caplog.at_level(logging.INFO, logger="src.agents.llm_client"):
                await client.call(
                    _make_request(),
                    classification=DataClassification.CONFIDENTIAL,
                )

        combined = " ".join(caplog.text.split())
        # Token counts should appear somewhere in log
        assert "50" in combined  # input_tokens
        assert "30" in combined  # output_tokens

    @pytest.mark.anyio
    async def test_retry_failure_logs_attempt_count(self, caplog: pytest.LogCaptureFixture) -> None:
        """Failed retry attempts are logged with attempt number."""
        client = LLMClient(anthropic_key="sk-ant-test", max_retries=2, base_delay=0.0)

        async def always_fail(*args, **kwargs):
            raise ConnectionError("test failure")

        with patch.object(client, "_call_anthropic", side_effect=always_fail):
            with caplog.at_level(logging.WARNING, logger="src.agents.llm_client"):
                with pytest.raises(ProviderUnavailableError):
                    await client.call(
                        _make_request(),
                        classification=DataClassification.CONFIDENTIAL,
                    )

        combined = " ".join(caplog.text.split())
        assert "1/2" in combined  # attempt 1 of 2
        assert "2/2" in combined  # attempt 2 of 2

    @pytest.mark.anyio
    async def test_call_logs_latency(self, caplog: pytest.LogCaptureFixture) -> None:
        """Successful call log includes latency measurement."""
        client = LLMClient(anthropic_key="sk-ant-test")

        with patch.object(
            client, "_call_anthropic",
            new_callable=AsyncMock,
            return_value=_mock_anthropic_ok(),
        ):
            with caplog.at_level(logging.INFO, logger="src.agents.llm_client"):
                await client.call(
                    _make_request(),
                    classification=DataClassification.CONFIDENTIAL,
                )

        combined = " ".join(caplog.text.split())
        assert "latency" in combined.lower() or "ms" in combined.lower()


# ===================================================================
# S9-4: Secret redaction
# ===================================================================


class TestSecretRedaction:
    """API keys, auth headers, and raw secrets must never appear in logs."""

    @pytest.mark.anyio
    async def test_api_key_not_in_success_logs(self, caplog: pytest.LogCaptureFixture) -> None:
        """Successful call logs do not contain API key values."""
        secret_key = "sk-ant-super-secret-key-12345"
        client = LLMClient(anthropic_key=secret_key)

        with patch.object(
            client, "_call_anthropic",
            new_callable=AsyncMock,
            return_value=_mock_anthropic_ok(),
        ):
            with caplog.at_level(logging.DEBUG, logger="src.agents.llm_client"):
                await client.call(
                    _make_request(),
                    classification=DataClassification.CONFIDENTIAL,
                )

        all_log_text = caplog.text
        assert secret_key not in all_log_text
        assert "super-secret" not in all_log_text

    @pytest.mark.anyio
    async def test_api_key_not_in_failure_logs(self, caplog: pytest.LogCaptureFixture) -> None:
        """Failure/retry logs do not contain API key values."""
        secret_key = "sk-ant-super-secret-key-67890"
        client = LLMClient(
            anthropic_key=secret_key,
            max_retries=2,
            base_delay=0.0,
        )

        async def always_fail(*args, **kwargs):
            raise ConnectionError("upstream timeout")

        with patch.object(client, "_call_anthropic", side_effect=always_fail):
            with caplog.at_level(logging.DEBUG, logger="src.agents.llm_client"):
                with pytest.raises(ProviderUnavailableError):
                    await client.call(
                        _make_request(),
                        classification=DataClassification.CONFIDENTIAL,
                    )

        all_log_text = caplog.text
        assert secret_key not in all_log_text
        assert "super-secret" not in all_log_text

    @pytest.mark.anyio
    async def test_openrouter_bearer_token_not_in_logs(
        self, caplog: pytest.LogCaptureFixture,
    ) -> None:
        """OpenRouter bearer token never appears in logs."""
        or_key = "sk-or-very-secret-router-token"
        client = LLMClient(openrouter_key=or_key, max_retries=1, base_delay=0.0)

        async def always_fail(*args, **kwargs):
            raise ConnectionError("timeout")

        with patch.object(client, "_call_openrouter", side_effect=always_fail):
            with caplog.at_level(logging.DEBUG, logger="src.agents.llm_client"):
                with pytest.raises(ProviderUnavailableError):
                    await client.call(
                        _make_request(),
                        classification=DataClassification.PUBLIC,
                    )

        all_log_text = caplog.text
        assert or_key not in all_log_text


# ===================================================================
# S9-4: Token usage accumulation
# ===================================================================


class TestTokenUsageAccumulation:
    """Token usage correctly accumulates across multiple calls."""

    @pytest.mark.anyio
    async def test_cumulative_usage_after_two_calls(self) -> None:
        """Two successful calls accumulate tokens."""
        client = LLMClient(anthropic_key="sk-ant-test")

        with patch.object(
            client, "_call_anthropic",
            new_callable=AsyncMock,
            return_value=_mock_anthropic_ok(),
        ):
            await client.call(_make_request(), classification=DataClassification.CONFIDENTIAL)
            await client.call(_make_request(), classification=DataClassification.CONFIDENTIAL)

        usage = client.cumulative_usage()
        assert usage.input_tokens == 100  # 50 * 2
        assert usage.output_tokens == 60   # 30 * 2
        assert usage.total_tokens == 160

    @pytest.mark.anyio
    async def test_reset_clears_accumulated_usage(self) -> None:
        """reset_usage() clears all accumulated token usage."""
        client = LLMClient(anthropic_key="sk-ant-test")

        with patch.object(
            client, "_call_anthropic",
            new_callable=AsyncMock,
            return_value=_mock_anthropic_ok(),
        ):
            await client.call(_make_request(), classification=DataClassification.CONFIDENTIAL)

        client.reset_usage()
        assert client.cumulative_usage().total_tokens == 0
