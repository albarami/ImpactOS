"""Tests for Economist Copilot agent and versioned prompt (Sprint 25)."""

import pytest

from src.agents.prompts.economist_copilot_v1 import (
    COPILOT_PROMPT_VERSION,
    build_system_prompt,
    get_tool_definitions,
)
from src.agents.economist_copilot import (
    ConfirmationRequiredError,
    CopilotResponse,
    InvalidToolCallError,
    parse_tool_calls,
    validate_tool_call,
)


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
