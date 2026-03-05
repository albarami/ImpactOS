"""Economist Copilot agent — Sprint 25.

Orchestrates conversational economist assistance using the ImpactOS
Leontief engine. Uses LLMClient for multi-provider LLM access and
enforces the agent-to-math boundary: LLM never computes numbers.

Mandatory confirmation gate blocks engine runs until user confirms.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

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

    Looks for JSON objects with 'tool' and 'arguments' keys.
    Returns list of parsed dicts. Malformed JSON is silently skipped
    (fail-closed: never let bad JSON disrupt the conversation).
    """
    tool_calls: list[dict] = []

    # Match JSON objects containing "tool" key
    pattern = r'\{[^{}]*"tool"\s*:\s*"[^"]+"\s*,\s*"arguments"\s*:\s*\{[^{}]*\}[^{}]*\}'
    matches = re.findall(pattern, content, re.DOTALL)

    for match in matches:
        try:
            parsed = json.loads(match)
            if "tool" in parsed and "arguments" in parsed:
                tool_calls.append(parsed)
        except json.JSONDecodeError:
            # Fail closed: skip malformed JSON rather than disrupting flow
            _logger.warning("Skipping malformed tool call JSON: %s", match)

    return tool_calls


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

        # Build message list for LLM
        llm_messages = list(messages) + [{"role": "user", "content": user_message}]

        # Call LLM via the client
        request = LLMRequest(
            system_prompt=system_prompt,
            user_prompt=user_message,
            output_schema=_DummySchema,
            max_tokens=ctx.get("max_tokens", 4096),
        )

        classification = ctx.get("classification", DataClassification.INTERNAL)
        response = await self._llm.call(request, classification=classification)

        # Extract content and usage from response
        content = self._extract_content(response)
        usage = self._extract_usage(response)
        provider, model_id = self._extract_model_info(response)

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

    def _extract_content(self, response: Any) -> str:
        """Extract text content from LLM response (provider-agnostic)."""
        # LLMResponse from our client
        if hasattr(response, "content") and isinstance(response.content, str):
            return response.content

        # Anthropic SDK response
        if hasattr(response, "content") and isinstance(response.content, list):
            texts = [b.text for b in response.content if hasattr(b, "text")]
            return "\n".join(texts) if texts else ""

        # OpenAI / OpenRouter response
        if hasattr(response, "choices"):
            choices = response.choices
            if choices and hasattr(choices[0], "message"):
                return choices[0].message.content or ""

        # httpx Response (OpenRouter raw)
        if hasattr(response, "json"):
            data = response.json()
            choices = data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")

        # Fallback
        return str(response)

    def _extract_usage(self, response: Any) -> TokenUsage:
        """Extract token usage from LLM response."""
        # LLMResponse from our client
        if hasattr(response, "usage"):
            u = response.usage
            if hasattr(u, "input_tokens"):
                return TokenUsage(
                    input_tokens=getattr(u, "input_tokens", 0),
                    output_tokens=getattr(u, "output_tokens", 0),
                )
            # OpenAI style
            if hasattr(u, "prompt_tokens"):
                return TokenUsage(
                    input_tokens=u.prompt_tokens or 0,
                    output_tokens=u.completion_tokens or 0,
                )

        return TokenUsage()

    def _extract_model_info(self, response: Any) -> tuple[str, str]:
        """Extract provider and model ID from response."""
        # LLMResponse from our client
        if hasattr(response, "provider") and hasattr(response, "model"):
            return str(getattr(response, "provider", "")), str(getattr(response, "model", ""))

        if hasattr(response, "model"):
            model = response.model or ""
            if "claude" in model.lower():
                return "anthropic", model
            elif "gpt" in model.lower():
                return "openai", model
            return "openrouter", model

        if hasattr(response, "json"):
            data = response.json()
            model = data.get("model", "")
            return "openrouter", model

        return "", ""


# Private dummy schema for LLMRequest compatibility — the copilot uses
# free-form conversation, not structured output, but LLMRequest requires
# an output_schema.  This is only used when calling through the existing
# LLMClient.call() path and won't affect the actual prompt/response.
# NOTE: A future sprint should add an unstructured mode to LLMClient
# so conversational agents don't need this workaround.
class _DummySchema(BaseModel):
    """Placeholder schema for LLMRequest when structured output isn't needed."""

    raw_response: str = ""
