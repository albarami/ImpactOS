"""Tests for LLM client abstraction (MVP-8).

Covers: provider routing by workspace classification, structured JSON output
with Pydantic validation, retry with exponential backoff, token tracking,
provider availability checks.
"""

import pytest
from pydantic import BaseModel

from src.agents.llm_client import (
    LLMClient,
    LLMProvider,
    LLMRequest,
    LLMResponse,
    ProviderRouter,
    TokenUsage,
)
from src.models.common import DataClassification

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class MockOutput(BaseModel):
    sector_code: str
    confidence: float


# ===================================================================
# Provider routing by classification
# ===================================================================


class TestProviderRouting:
    """Route LLM calls by workspace data classification."""

    def test_restricted_routes_to_local(self) -> None:
        router = ProviderRouter()
        provider = router.select(DataClassification.RESTRICTED)
        assert provider == LLMProvider.LOCAL

    def test_confidential_routes_to_anthropic(self) -> None:
        router = ProviderRouter()
        provider = router.select(DataClassification.CONFIDENTIAL)
        assert provider == LLMProvider.ANTHROPIC

    def test_internal_routes_to_anthropic(self) -> None:
        router = ProviderRouter()
        provider = router.select(DataClassification.INTERNAL)
        assert provider == LLMProvider.ANTHROPIC

    def test_public_routes_to_openrouter(self) -> None:
        router = ProviderRouter()
        provider = router.select(DataClassification.PUBLIC)
        assert provider == LLMProvider.OPENROUTER

    def test_custom_routing_table(self) -> None:
        custom = {
            DataClassification.PUBLIC: LLMProvider.OPENAI,
            DataClassification.INTERNAL: LLMProvider.OPENAI,
            DataClassification.CONFIDENTIAL: LLMProvider.ANTHROPIC,
            DataClassification.RESTRICTED: LLMProvider.LOCAL,
        }
        router = ProviderRouter(routing_table=custom)
        assert router.select(DataClassification.PUBLIC) == LLMProvider.OPENAI


# ===================================================================
# LLM request/response models
# ===================================================================


class TestLLMRequestResponse:
    """LLMRequest and LLMResponse structures."""

    def test_request_creation(self) -> None:
        req = LLMRequest(
            system_prompt="You are a mapping assistant.",
            user_prompt="Map this: concrete works",
            output_schema=MockOutput,
            max_tokens=500,
        )
        assert req.system_prompt == "You are a mapping assistant."
        assert req.output_schema == MockOutput
        assert req.max_tokens == 500

    def test_request_defaults(self) -> None:
        req = LLMRequest(
            system_prompt="test",
            user_prompt="test",
            output_schema=MockOutput,
        )
        assert req.max_tokens == 1024
        assert req.temperature == 0.0

    def test_response_creation(self) -> None:
        resp = LLMResponse(
            content='{"sector_code": "F", "confidence": 0.9}',
            parsed=MockOutput(sector_code="F", confidence=0.9),
            provider=LLMProvider.ANTHROPIC,
            model="claude-sonnet-4-20250514",
            usage=TokenUsage(input_tokens=100, output_tokens=50),
        )
        assert resp.parsed.sector_code == "F"
        assert resp.usage.total_tokens == 150


# ===================================================================
# Token usage tracking
# ===================================================================


class TestTokenUsage:
    """Track token usage across calls."""

    def test_total_tokens(self) -> None:
        usage = TokenUsage(input_tokens=100, output_tokens=50)
        assert usage.total_tokens == 150

    def test_zero_tokens(self) -> None:
        usage = TokenUsage(input_tokens=0, output_tokens=0)
        assert usage.total_tokens == 0


# ===================================================================
# LLM client — structured output
# ===================================================================


class TestLLMClientStructuredOutput:
    """Validate structured JSON parsing with Pydantic."""

    def test_parse_valid_json(self) -> None:
        client = LLMClient()
        parsed = client.parse_structured_output(
            raw='{"sector_code": "F", "confidence": 0.92}',
            schema=MockOutput,
        )
        assert parsed.sector_code == "F"
        assert parsed.confidence == 0.92

    def test_parse_invalid_json_raises(self) -> None:
        client = LLMClient()
        with pytest.raises(ValueError):
            client.parse_structured_output(
                raw="not json at all",
                schema=MockOutput,
            )

    def test_parse_missing_field_raises(self) -> None:
        client = LLMClient()
        with pytest.raises(ValueError):
            client.parse_structured_output(
                raw='{"sector_code": "F"}',
                schema=MockOutput,
            )

    def test_parse_with_extra_fields(self) -> None:
        """Extra fields ignored — only schema fields matter."""
        client = LLMClient()
        parsed = client.parse_structured_output(
            raw='{"sector_code": "F", "confidence": 0.8, "extra": true}',
            schema=MockOutput,
        )
        assert parsed.sector_code == "F"

    def test_extract_json_from_markdown(self) -> None:
        """Handle LLM wrapping JSON in markdown code blocks."""
        client = LLMClient()
        raw = '```json\n{"sector_code": "F", "confidence": 0.85}\n```'
        parsed = client.parse_structured_output(raw=raw, schema=MockOutput)
        assert parsed.sector_code == "F"


# ===================================================================
# Provider availability
# ===================================================================


class TestProviderAvailability:
    """Check provider availability based on API key presence."""

    def test_no_keys_only_local(self) -> None:
        client = LLMClient(
            anthropic_key="",
            openai_key="",
            openrouter_key="",
        )
        avail = client.available_providers()
        assert LLMProvider.LOCAL in avail
        assert LLMProvider.ANTHROPIC not in avail

    def test_anthropic_key_available(self) -> None:
        client = LLMClient(anthropic_key="sk-test-key")
        avail = client.available_providers()
        assert LLMProvider.ANTHROPIC in avail
        assert LLMProvider.LOCAL in avail

    def test_all_keys_all_providers(self) -> None:
        client = LLMClient(
            anthropic_key="sk-ant",
            openai_key="sk-oai",
            openrouter_key="sk-or",
        )
        avail = client.available_providers()
        assert len(avail) == 4  # LOCAL + 3 cloud providers

    def test_is_available_for_classification(self) -> None:
        client = LLMClient(anthropic_key="sk-test")
        assert client.is_available_for(DataClassification.CONFIDENTIAL) is True

    def test_not_available_for_classification(self) -> None:
        client = LLMClient(anthropic_key="", openai_key="", openrouter_key="")
        assert client.is_available_for(DataClassification.CONFIDENTIAL) is False


# ===================================================================
# Retry configuration
# ===================================================================


class TestRetryConfig:
    """Retry with exponential backoff configuration."""

    def test_default_retry_config(self) -> None:
        client = LLMClient()
        assert client.max_retries == 3
        assert client.base_delay == 1.0

    def test_custom_retry_config(self) -> None:
        client = LLMClient(max_retries=5, base_delay=2.0)
        assert client.max_retries == 5
        assert client.base_delay == 2.0

    def test_backoff_delays(self) -> None:
        client = LLMClient(max_retries=3, base_delay=1.0)
        delays = client.compute_backoff_delays()
        assert delays[0] == 1.0
        assert delays[1] == 2.0
        assert delays[2] == 4.0


# ===================================================================
# Cumulative token tracking
# ===================================================================


class TestCumulativeTracking:
    """Track cumulative token usage across multiple calls."""

    def test_record_usage(self) -> None:
        client = LLMClient()
        client.record_usage(TokenUsage(input_tokens=100, output_tokens=50))
        client.record_usage(TokenUsage(input_tokens=200, output_tokens=100))
        total = client.cumulative_usage()
        assert total.input_tokens == 300
        assert total.output_tokens == 150
        assert total.total_tokens == 450

    def test_empty_cumulative(self) -> None:
        client = LLMClient()
        total = client.cumulative_usage()
        assert total.total_tokens == 0

    def test_reset_usage(self) -> None:
        client = LLMClient()
        client.record_usage(TokenUsage(input_tokens=100, output_tokens=50))
        client.reset_usage()
        total = client.cumulative_usage()
        assert total.total_tokens == 0


# ===================================================================
# Multi-turn messages (Sprint 26 — S26-BL-1)
# ===================================================================


class TestMultiTurnMessages:
    """LLMRequest multi-turn history support."""

    def test_llm_request_defaults_messages_none(self) -> None:
        """messages defaults to None when not provided."""
        req = LLMRequest(
            system_prompt="s",
            user_prompt="u",
        )
        assert req.messages is None

    def test_llm_request_with_messages(self) -> None:
        """messages field accepts a list of role/content dicts."""
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
            {"role": "user", "content": "follow-up"},
        ]
        req = LLMRequest(
            system_prompt="s",
            user_prompt="follow-up",
            messages=msgs,
        )
        assert req.messages is not None
        assert len(req.messages) == 3
        assert req.messages[0]["role"] == "user"

    def test_llm_request_output_schema_optional(self) -> None:
        """output_schema can be None (unstructured mode)."""
        req = LLMRequest(
            system_prompt="s",
            user_prompt="u",
            output_schema=None,
        )
        assert req.output_schema is None

    def test_llm_request_structured_defaults_true(self) -> None:
        """structured flag defaults to True for backward compat."""
        req = LLMRequest(
            system_prompt="s",
            user_prompt="u",
        )
        assert req.structured is True

    def test_llm_request_structured_explicit_false(self) -> None:
        """structured flag can be set to False."""
        req = LLMRequest(
            system_prompt="s",
            user_prompt="u",
            structured=False,
        )
        assert req.structured is False

    def test_llm_request_backward_compat_with_schema(self) -> None:
        """Existing callers passing output_schema positionally still work."""
        req = LLMRequest(
            system_prompt="s",
            user_prompt="u",
            output_schema=MockOutput,
        )
        assert req.output_schema is MockOutput
        assert req.structured is True
        assert req.messages is None


# ===================================================================
# Unstructured mode (Sprint 26 — S26-BL-5)
# ===================================================================


class TestUnstructuredMode:
    """Unstructured conversation mode — skip JSON parsing."""

    def test_normalize_response_unstructured_skips_parsing(self) -> None:
        """When structured=False, parsed is None even with valid JSON."""

        class _FakeAnthropicBlock:
            def __init__(self, text: str):
                self.text = text

        class _FakeUsage:
            input_tokens = 10
            output_tokens = 20

        class _FakeResponse:
            content = [_FakeAnthropicBlock('{"sector_code": "F", "confidence": 0.9}')]
            model = "claude-test"
            usage = _FakeUsage()

        client = LLMClient()
        result = client._normalize_response(
            _FakeResponse(),
            provider=LLMProvider.ANTHROPIC,
            schema=MockOutput,
            structured=False,
        )
        assert result.parsed is None
        assert result.content == '{"sector_code": "F", "confidence": 0.9}'
        assert result.provider == LLMProvider.ANTHROPIC

    def test_normalize_response_structured_still_parses(self) -> None:
        """When structured=True with a schema, parsing works as before."""

        class _FakeAnthropicBlock:
            def __init__(self, text: str):
                self.text = text

        class _FakeUsage:
            input_tokens = 10
            output_tokens = 20

        class _FakeResponse:
            content = [_FakeAnthropicBlock('{"sector_code": "F", "confidence": 0.9}')]
            model = "claude-test"
            usage = _FakeUsage()

        client = LLMClient()
        result = client._normalize_response(
            _FakeResponse(),
            provider=LLMProvider.ANTHROPIC,
            schema=MockOutput,
            structured=True,
        )
        assert result.parsed is not None
        assert result.parsed.sector_code == "F"
        assert result.parsed.confidence == 0.9

    def test_normalize_response_no_schema_skips_parsing(self) -> None:
        """When schema is None, parsed is None regardless of structured flag."""

        class _FakeAnthropicBlock:
            def __init__(self, text: str):
                self.text = text

        class _FakeUsage:
            input_tokens = 5
            output_tokens = 15

        class _FakeResponse:
            content = [_FakeAnthropicBlock("Just a text response")]
            model = "claude-test"
            usage = _FakeUsage()

        client = LLMClient()
        result = client._normalize_response(
            _FakeResponse(),
            provider=LLMProvider.ANTHROPIC,
            schema=None,
            structured=True,
        )
        assert result.parsed is None
        assert result.content == "Just a text response"

    def test_response_with_parsed_none(self) -> None:
        """LLMResponse accepts parsed=None for unstructured mode."""
        resp = LLMResponse(
            content="Hello, this is a conversation.",
            parsed=None,
            provider=LLMProvider.LOCAL,
            model="local-deterministic",
            usage=TokenUsage(input_tokens=0, output_tokens=0),
        )
        assert resp.parsed is None
        assert resp.content == "Hello, this is a conversation."

    def test_call_local_unstructured(self) -> None:
        """LOCAL provider returns empty content and None parsed for unstructured."""
        client = LLMClient()
        req = LLMRequest(
            system_prompt="s",
            user_prompt="u",
            output_schema=None,
            structured=False,
        )
        result = client._call_local(req)
        assert result.parsed is None
        assert result.content == ""
        assert result.provider == LLMProvider.LOCAL

    def test_call_local_structured_still_works(self) -> None:
        """LOCAL provider still generates schema defaults for structured mode."""
        client = LLMClient()
        req = LLMRequest(
            system_prompt="s",
            user_prompt="u",
            output_schema=MockOutput,
            structured=True,
        )
        result = client._call_local(req)
        assert result.parsed is not None
        assert result.parsed.sector_code == "UNKNOWN"
        assert result.parsed.confidence == 0.0
