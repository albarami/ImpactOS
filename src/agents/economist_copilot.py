"""Economist Copilot agent — Sprint 25.

Orchestrates conversational economist assistance using the ImpactOS
Leontief engine. Uses LLMClient for multi-provider LLM access and
enforces the agent-to-math boundary: LLM never computes numbers.

Mandatory confirmation gate blocks engine runs until user confirms.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from src.agents.llm_client import LLMClient, LLMRequest, ProviderUnavailableError
from src.models.common import DataClassification
from src.agents.prompts.economist_copilot_v1 import (
    COPILOT_PROMPT_VERSION,
    build_system_prompt,
    get_tool_definitions,
)
from src.models.chat import TokenUsage, ToolCall, TraceMetadata

_logger = logging.getLogger(__name__)

# Tools that require user confirmation before execution
_GATED_TOOLS = frozenset({"build_scenario", "run_engine"})

# Valid tool names
_VALID_TOOLS = frozenset({"lookup_data", "build_scenario", "run_engine", "narrate_results"})


class ConfirmationRequiredError(Exception):
    """Raised when a gated tool is called without user confirmation."""

    def __init__(self, tool_name: str, proposed_args: dict) -> None:
        self.tool_name = tool_name
        self.proposed_args = proposed_args
        super().__init__(
            f"Tool '{tool_name}' requires user confirmation before execution."
        )


class InvalidToolCallError(Exception):
    """Raised when a tool call cannot be parsed or is invalid."""

    def __init__(self, message: str, raw_content: str = "") -> None:
        self.raw_content = raw_content
        super().__init__(message)


@dataclass
class CopilotResponse:
    """Response from a single copilot turn."""

    content: str
    role: str = "assistant"
    tool_calls: list[ToolCall] = field(default_factory=list)
    trace_metadata: TraceMetadata | None = None
    pending_confirmation: dict | None = None
    prompt_version: str = COPILOT_PROMPT_VERSION
    model_provider: str = ""
    model_id: str = ""
    token_usage: TokenUsage = field(default_factory=TokenUsage)


def parse_tool_calls(content: str) -> list[dict]:
    """Extract tool call JSON objects from LLM response content.

    Uses balanced-brace extraction to support nested objects/arrays
    in tool arguments. Malformed JSON is silently skipped.
    """
    tool_calls: list[dict] = []

    i = 0
    while i < len(content):
        if content[i] == '{':
            # Try to extract a balanced JSON object
            obj_str = _extract_balanced_braces(content, i)
            if obj_str:
                try:
                    parsed = json.loads(obj_str)
                    if isinstance(parsed, dict) and "tool" in parsed and "arguments" in parsed:
                        tool_calls.append(parsed)
                except json.JSONDecodeError:
                    _logger.warning("Skipping malformed tool call JSON: %.200s", obj_str)
                i += len(obj_str)
            else:
                i += 1
        else:
            i += 1

    return tool_calls


def _extract_balanced_braces(text: str, start: int) -> str | None:
    """Extract a balanced {} block from text starting at position start.

    Returns the substring including outer braces, or None if unbalanced.
    Respects JSON string literals (skips braces inside quoted strings).
    """
    if start >= len(text) or text[start] != '{':
        return None

    depth = 0
    in_string = False
    escape_next = False

    for i in range(start, len(text)):
        ch = text[i]

        if escape_next:
            escape_next = False
            continue

        if ch == '\\' and in_string:
            escape_next = True
            continue

        if ch == '"' and not escape_next:
            in_string = not in_string
            continue

        if in_string:
            continue

        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return text[start:i + 1]

    return None  # Unbalanced


def validate_tool_call(tool_call: dict) -> None:
    """Validate a parsed tool call dict.

    Raises InvalidToolCallError if tool name is unknown or arguments missing.
    """
    tool_name = tool_call.get("tool", "")
    if tool_name not in _VALID_TOOLS:
        raise InvalidToolCallError(
            f"Unknown tool: '{tool_name}'. Valid tools: {sorted(_VALID_TOOLS)}"
        )

    args = tool_call.get("arguments")
    if not isinstance(args, dict):
        raise InvalidToolCallError(
            f"Tool '{tool_name}' arguments must be a dict, got {type(args).__name__}"
        )


class EconomistCopilot:
    """Conversational economist copilot agent.

    Uses LLMClient for LLM access and enforces:
    - Confirmation gate on build_scenario and run_engine
    - Agent-to-math boundary (LLM never computes numbers)
    - Prompt versioning for reproducibility
    """

    def __init__(
        self,
        llm_client: LLMClient,
        prompt_version: str = COPILOT_PROMPT_VERSION,
    ) -> None:
        self._llm = llm_client
        self._prompt_version = prompt_version

    @property
    def prompt_version(self) -> str:
        return self._prompt_version

    async def process_turn(
        self,
        messages: list[dict[str, str]],
        user_message: str,
        context: dict[str, Any] | None = None,
    ) -> CopilotResponse:
        """Process a single conversation turn.

        Args:
            messages: Prior conversation history as list of {role, content} dicts.
            user_message: The new user message.
            context: Optional context dict with keys like 'workspace_description',
                     'user_confirmed' (bool), etc.

        Returns:
            CopilotResponse with content, tool_calls, trace, etc.

        Raises:
            ConfirmationRequiredError: If LLM calls a gated tool without confirmation.
            InvalidToolCallError: If LLM produces malformed tool calls.
            ProviderUnavailableError: If no LLM provider is available.
        """
        ctx = context or {}
        system_prompt = build_system_prompt(ctx)

        # Build full conversation history for LLM
        llm_messages = list(messages) + [{"role": "user", "content": user_message}]

        classification = ctx.get("classification", DataClassification.INTERNAL)

        request = LLMRequest(
            system_prompt=system_prompt,
            user_prompt=user_message,
            messages=llm_messages,
            max_tokens=ctx.get("max_tokens", 4096),
        )

        response = await self._llm.call_unstructured(
            request, classification=classification,
        )

        # Extract content and usage from normalized LLMResponse
        content = response.content
        usage = TokenUsage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
        provider = response.provider.value if hasattr(response.provider, "value") else str(response.provider)
        model_id = response.model

        # Check for tool calls in response
        tool_calls_raw = parse_tool_calls(content)
        tool_calls: list[ToolCall] = []

        for tc in tool_calls_raw:
            validate_tool_call(tc)
            tool_name = tc["tool"]
            tool_args = tc["arguments"]

            # Confirmation gate: block gated tools unless user confirmed
            if tool_name in _GATED_TOOLS and not ctx.get("user_confirmed", False):
                _logger.info(
                    "Confirmation gate: blocking %s (user_confirmed=False)",
                    tool_name,
                )
                return CopilotResponse(
                    content=content,
                    pending_confirmation={
                        "tool": tool_name,
                        "arguments": tool_args,
                    },
                    prompt_version=self._prompt_version,
                    model_provider=provider,
                    model_id=model_id,
                    token_usage=usage,
                )

            tool_calls.append(ToolCall(
                tool_name=tool_name,
                arguments=tool_args,
            ))

        return CopilotResponse(
            content=content,
            tool_calls=tool_calls,
            prompt_version=self._prompt_version,
            model_provider=provider,
            model_id=model_id,
            token_usage=usage,
        )

