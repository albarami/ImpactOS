"""Tests for Economist Copilot agent and versioned prompt (Sprint 25 + Sprint 26)."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.agents.prompts.economist_copilot_v1 import (
    COPILOT_PROMPT_VERSION,
    build_system_prompt,
    get_tool_definitions,
)
from src.agents.economist_copilot import (
    ConfirmationRequiredError,
    CopilotResponse,
    EconomistCopilot,
    InvalidToolCallError,
    parse_tool_calls,
    validate_tool_call,
)
from src.agents.llm_client import LLMProvider, LLMResponse, TokenUsage


# ── Prompt tests ────────────────────────────────────────────────────────


class TestVersionedPrompt:
    """Tests for the versioned prompt artifact."""

    def test_prompt_version_is_string(self):
        assert isinstance(COPILOT_PROMPT_VERSION, str)
        assert len(COPILOT_PROMPT_VERSION) > 0

    def test_prompt_contains_critical_rules(self):
        prompt = build_system_prompt()
        assert "NEVER produce economic numbers" in prompt or "NEVER produce economic numbers yourself" in prompt

    def test_prompt_contains_confirmation_gate(self):
        prompt = build_system_prompt()
        assert "CONFIRMATION GATE" in prompt or "confirmation gate" in prompt.lower()

    def test_prompt_contains_tool_definitions(self):
        prompt = build_system_prompt()
        assert "lookup_data" in prompt
        assert "build_scenario" in prompt
        assert "run_engine" in prompt
        assert "narrate_results" in prompt

    def test_prompt_contains_isic_sectors(self):
        prompt = build_system_prompt()
        assert "A:" in prompt or "A: Agriculture" in prompt
        assert "B:" in prompt  # Mining
        assert "F:" in prompt  # Construction
        assert "I:" in prompt  # Accommodation

    def test_prompt_contains_shock_types(self):
        prompt = build_system_prompt()
        assert "FINAL_DEMAND_SHOCK" in prompt
        assert "IMPORT_SUBSTITUTION" in prompt
        assert "LOCAL_CONTENT" in prompt
        assert "CONSTRAINT_OVERRIDE" in prompt

    def test_prompt_with_workspace_context(self):
        prompt = build_system_prompt({"workspace_description": "NEOM mega-city analysis"})
        assert "NEOM mega-city analysis" in prompt

    def test_prompt_without_context(self):
        prompt = build_system_prompt()
        assert "Economic impact assessment" in prompt  # default

    def test_prompt_agent_math_boundary(self):
        prompt = build_system_prompt()
        # Must enforce agent-to-math boundary
        assert "deterministic engine" in prompt.lower() or "ResultSet" in prompt

    def test_prompt_trace_metadata_required(self):
        prompt = build_system_prompt()
        assert "run_id" in prompt
        assert "scenario_spec_id" in prompt
        assert "model_version_id" in prompt
        assert "confidence" in prompt


class TestToolDefinitions:
    """Tests for tool definition metadata."""

    def test_tool_definitions_count(self):
        tools = get_tool_definitions()
        assert len(tools) == 4

    def test_tool_names(self):
        tools = get_tool_definitions()
        names = {t["name"] for t in tools}
        assert names == {"lookup_data", "build_scenario", "run_engine", "narrate_results"}

    def test_gated_tools_require_confirmation(self):
        tools = get_tool_definitions()
        gated = {t["name"] for t in tools if t.get("requires_confirmation")}
        assert "build_scenario" in gated
        assert "run_engine" in gated
        assert "lookup_data" not in gated
        assert "narrate_results" not in gated


# ── Tool parsing tests ──────────────────────────────────────────────────


class TestToolParsing:
    """Tests for tool call parsing from LLM output."""

    def test_parse_valid_tool_call(self):
        content = 'Here is my analysis. {"tool": "lookup_data", "arguments": {"dataset_id": "io_tables", "year": 2023}}'
        calls = parse_tool_calls(content)
        assert len(calls) == 1
        assert calls[0]["tool"] == "lookup_data"
        assert calls[0]["arguments"]["dataset_id"] == "io_tables"

    def test_parse_no_tool_calls(self):
        content = "I understand your question about the Umrah visa impact."
        calls = parse_tool_calls(content)
        assert len(calls) == 0

    def test_parse_invalid_json_fails_closed(self):
        content = '{"tool": "lookup_data", "arguments": {broken json}}'
        # Should either return empty (no match) or raise
        # The regex won't match broken JSON, so it returns empty
        calls = parse_tool_calls(content)
        assert len(calls) == 0

    def test_validate_unknown_tool_fails(self):
        with pytest.raises(InvalidToolCallError, match="Unknown tool"):
            validate_tool_call({"tool": "hack_system", "arguments": {}})

    def test_validate_missing_arguments_fails(self):
        with pytest.raises(InvalidToolCallError, match="arguments must be a dict"):
            validate_tool_call({"tool": "lookup_data", "arguments": "not_a_dict"})

    def test_validate_valid_tool_passes(self):
        # Should not raise
        validate_tool_call({"tool": "lookup_data", "arguments": {"dataset_id": "io"}})

    def test_parse_nested_json_arguments(self):
        """Nested objects in arguments must parse correctly."""
        content = '{"tool": "build_scenario", "arguments": {"shocks": [{"sector": "A", "value": 0.1}]}}'
        calls = parse_tool_calls(content)
        assert len(calls) == 1
        assert calls[0]["tool"] == "build_scenario"
        assert calls[0]["arguments"]["shocks"][0]["sector"] == "A"

    def test_parse_deeply_nested_arguments(self):
        """3+ levels of nesting must work."""
        content = '{"tool": "build_scenario", "arguments": {"config": {"shocks": [{"sectors": {"primary": "A"}}]}}}'
        calls = parse_tool_calls(content)
        assert len(calls) == 1
        assert calls[0]["arguments"]["config"]["shocks"][0]["sectors"]["primary"] == "A"

    def test_parse_arguments_with_strings_containing_braces(self):
        """Braces inside string values must not confuse the parser."""
        content = '{"tool": "narrate_results", "arguments": {"template": "GDP grew by {x}%"}}'
        calls = parse_tool_calls(content)
        assert len(calls) == 1
        assert calls[0]["arguments"]["template"] == "GDP grew by {x}%"

    def test_parse_multiple_tool_calls_with_nesting(self):
        """Multiple nested tool calls in one response."""
        content = (
            'First call: {"tool": "build_scenario", "arguments": {"shocks": [{"sector": "A"}]}} '
            'Second call: {"tool": "narrate_results", "arguments": {"data": {"value": 1.5}}}'
        )
        calls = parse_tool_calls(content)
        assert len(calls) == 2
        assert calls[0]["tool"] == "build_scenario"
        assert calls[1]["tool"] == "narrate_results"

    def test_parse_malformed_nested_json_skipped(self):
        """Unbalanced braces are silently skipped."""
        content = '{"tool": "build_scenario", "arguments": {"shocks": [{"sector": "A"'
        calls = parse_tool_calls(content)
        assert len(calls) == 0

    def test_parse_existing_flat_args_still_works(self):
        """Regression: flat arguments continue to work."""
        content = '{"tool": "lookup_data", "arguments": {"dataset_id": "io_tables", "year": 2023}}'
        calls = parse_tool_calls(content)
        assert len(calls) == 1
        assert calls[0]["tool"] == "lookup_data"
        assert calls[0]["arguments"]["year"] == 2023


# ── CopilotResponse tests ──────────────────────────────────────────────


class TestCopilotResponse:
    """Tests for CopilotResponse dataclass."""

    def test_response_has_prompt_version(self):
        resp = CopilotResponse(content="test")
        assert resp.prompt_version == COPILOT_PROMPT_VERSION

    def test_response_defaults(self):
        resp = CopilotResponse(content="Hello")
        assert resp.role == "assistant"
        assert resp.tool_calls == []
        assert resp.trace_metadata is None
        assert resp.pending_confirmation is None
        assert resp.token_usage.input_tokens == 0
        assert resp.token_usage.output_tokens == 0

    def test_response_with_pending_confirmation(self):
        resp = CopilotResponse(
            content="Shall I proceed?",
            pending_confirmation={
                "tool": "build_scenario",
                "arguments": {"name": "test"},
            },
        )
        assert resp.pending_confirmation is not None
        assert resp.pending_confirmation["tool"] == "build_scenario"


# ── Confirmation gate tests ─────────────────────────────────────────────


class TestConfirmationGate:
    """Tests for the confirmation gate error."""

    def test_confirmation_error_attributes(self):
        err = ConfirmationRequiredError("build_scenario", {"name": "test"})
        assert err.tool_name == "build_scenario"
        assert err.proposed_args == {"name": "test"}
        assert "confirmation" in str(err).lower()


# ── DummySchema removal (Sprint 26 — S26-BL-5) ──────────────────────────


class TestDummySchemaRemoved:
    """Verify _DummySchema is no longer defined (Sprint 26)."""

    def test_dummy_schema_not_importable(self):
        """_DummySchema should no longer exist in the module."""
        import src.agents.economist_copilot as mod

        assert not hasattr(mod, "_DummySchema"), (
            "_DummySchema should have been removed in Sprint 26"
        )


# ── process_turn with mocked LLM (Sprint 26 — S26-BL-1) ────────────────


class TestProcessTurnMultiTurn:
    """Copilot passes conversation history to LLM via messages field."""

    async def test_process_turn_passes_history_in_messages(self):
        """process_turn builds messages list with history + current msg."""
        mock_llm = MagicMock()
        mock_llm.call_unstructured = AsyncMock(return_value=LLMResponse(
            content="I can help with that tourism analysis.",
            parsed=None,
            provider=LLMProvider.LOCAL,
            model="local-deterministic",
            usage=TokenUsage(input_tokens=50, output_tokens=30),
        ))

        copilot = EconomistCopilot(llm_client=mock_llm)

        history = [
            {"role": "user", "content": "What sectors are affected by tourism?"},
            {"role": "assistant", "content": "Tourism primarily affects sectors I and G."},
        ]
        result = await copilot.process_turn(
            messages=history,
            user_message="Tell me more about sector I.",
        )

        # Verify call_unstructured was called
        assert mock_llm.call_unstructured.called

        # Get the LLMRequest that was passed
        call_args = mock_llm.call_unstructured.call_args
        request = call_args[0][0]  # first positional arg

        # messages should include history + new user message
        assert request.messages is not None
        assert len(request.messages) == 3  # 2 history + 1 new
        assert request.messages[0]["role"] == "user"
        assert request.messages[0]["content"] == "What sectors are affected by tourism?"
        assert request.messages[1]["role"] == "assistant"
        assert request.messages[2]["role"] == "user"
        assert request.messages[2]["content"] == "Tell me more about sector I."

        # user_prompt still set for compatibility
        assert request.user_prompt == "Tell me more about sector I."

        # Response content comes from mocked LLM
        assert result.content == "I can help with that tourism analysis."

    async def test_process_turn_empty_history(self):
        """process_turn works with empty history (first message)."""
        mock_llm = MagicMock()
        mock_llm.call_unstructured = AsyncMock(return_value=LLMResponse(
            content="Welcome! How can I help?",
            parsed=None,
            provider=LLMProvider.LOCAL,
            model="local-deterministic",
            usage=TokenUsage(input_tokens=20, output_tokens=15),
        ))

        copilot = EconomistCopilot(llm_client=mock_llm)

        result = await copilot.process_turn(
            messages=[],
            user_message="Hello",
        )

        call_args = mock_llm.call_unstructured.call_args
        request = call_args[0][0]

        assert request.messages is not None
        assert len(request.messages) == 1  # only the new user message
        assert request.messages[0] == {"role": "user", "content": "Hello"}

    async def test_process_turn_extracts_provider_and_model(self):
        """process_turn correctly extracts provider and model from LLMResponse."""
        mock_llm = MagicMock()
        mock_llm.call_unstructured = AsyncMock(return_value=LLMResponse(
            content="Analysis results.",
            parsed=None,
            provider=LLMProvider.ANTHROPIC,
            model="claude-sonnet-4-20250514",
            usage=TokenUsage(input_tokens=100, output_tokens=80),
        ))

        copilot = EconomistCopilot(llm_client=mock_llm)
        result = await copilot.process_turn(
            messages=[],
            user_message="Analyze this.",
        )

        assert result.model_provider == "ANTHROPIC"
        assert result.model_id == "claude-sonnet-4-20250514"
        assert result.token_usage.input_tokens == 100
        assert result.token_usage.output_tokens == 80

    async def test_process_turn_passes_model_from_context(self):
        """process_turn wires ctx['model'] into LLMRequest.model."""
        mock_llm = MagicMock()
        mock_llm.call_unstructured = AsyncMock(return_value=LLMResponse(
            content="Using the specified model.",
            parsed=None,
            provider=LLMProvider.ANTHROPIC,
            model="claude-sonnet-4-20250514",
            usage=TokenUsage(input_tokens=30, output_tokens=20),
        ))

        copilot = EconomistCopilot(llm_client=mock_llm)
        await copilot.process_turn(
            messages=[],
            user_message="Test model routing.",
            context={"model": "claude-sonnet-4-20250514"},
        )

        call_args = mock_llm.call_unstructured.call_args
        request = call_args[0][0]
        assert request.model == "claude-sonnet-4-20250514"
