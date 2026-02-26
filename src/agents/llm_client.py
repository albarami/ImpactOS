"""LLM client abstraction — MVP-8.

Unified interface for Anthropic/OpenAI/OpenRouter with:
- Workspace classification-based routing (RESTRICTED → local,
  CONFIDENTIAL → enterprise ZDR, PUBLIC → any)
- Structured JSON output with Pydantic validation
- Retry with exponential backoff
- Token usage tracking

Agents use this client — they NEVER compute economic results.
"""

import json
import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TypeVar

from pydantic import BaseModel

from src.models.common import DataClassification

T = TypeVar("T", bound=BaseModel)


# ---------------------------------------------------------------------------
# Provider enum
# ---------------------------------------------------------------------------


class LLMProvider(StrEnum):
    """Supported LLM providers."""

    LOCAL = "LOCAL"
    ANTHROPIC = "ANTHROPIC"
    OPENAI = "OPENAI"
    OPENROUTER = "OPENROUTER"


# ---------------------------------------------------------------------------
# Token tracking
# ---------------------------------------------------------------------------


@dataclass
class TokenUsage:
    """Token usage for a single LLM call."""

    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


# ---------------------------------------------------------------------------
# Request / Response
# ---------------------------------------------------------------------------


@dataclass
class LLMRequest:
    """Structured request to an LLM provider."""

    system_prompt: str
    user_prompt: str
    output_schema: type[BaseModel]
    max_tokens: int = 1024
    temperature: float = 0.0


@dataclass
class LLMResponse:
    """Structured response from an LLM provider."""

    content: str
    parsed: BaseModel
    provider: LLMProvider
    model: str
    usage: TokenUsage


# ---------------------------------------------------------------------------
# Provider routing
# ---------------------------------------------------------------------------

_DEFAULT_ROUTING: dict[DataClassification, LLMProvider] = {
    DataClassification.RESTRICTED: LLMProvider.LOCAL,
    DataClassification.CONFIDENTIAL: LLMProvider.ANTHROPIC,
    DataClassification.INTERNAL: LLMProvider.ANTHROPIC,
    DataClassification.PUBLIC: LLMProvider.OPENROUTER,
}


class ProviderRouter:
    """Select LLM provider based on workspace data classification."""

    def __init__(
        self,
        routing_table: dict[DataClassification, LLMProvider] | None = None,
    ) -> None:
        self._table = routing_table or dict(_DEFAULT_ROUTING)

    def select(self, classification: DataClassification) -> LLMProvider:
        """Return the appropriate provider for the given classification."""
        return self._table[classification]


# ---------------------------------------------------------------------------
# JSON extraction helpers
# ---------------------------------------------------------------------------

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?```", re.DOTALL)


def _extract_json(raw: str) -> str:
    """Extract JSON from raw LLM output, stripping markdown fences."""
    match = _JSON_BLOCK_RE.search(raw)
    if match:
        return match.group(1).strip()
    return raw.strip()


# ---------------------------------------------------------------------------
# LLM client
# ---------------------------------------------------------------------------


class LLMClient:
    """Unified LLM client with structured output, retry, and tracking."""

    def __init__(
        self,
        *,
        anthropic_key: str = "",
        openai_key: str = "",
        openrouter_key: str = "",
        max_retries: int = 3,
        base_delay: float = 1.0,
    ) -> None:
        self._anthropic_key = anthropic_key
        self._openai_key = openai_key
        self._openrouter_key = openrouter_key
        self.max_retries = max_retries
        self.base_delay = base_delay
        self._router = ProviderRouter()
        self._usage_log: list[TokenUsage] = []

    # ----- Structured output parsing -----

    def parse_structured_output(self, *, raw: str, schema: type[T]) -> T:
        """Parse raw LLM output into a validated Pydantic model.

        Raises ValueError if JSON is invalid or fails schema validation.
        """
        cleaned = _extract_json(raw)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON from LLM: {exc}") from exc
        try:
            return schema.model_validate(data)
        except Exception as exc:
            raise ValueError(f"Schema validation failed: {exc}") from exc

    # ----- Provider availability -----

    def available_providers(self) -> list[LLMProvider]:
        """Return list of providers with valid API keys."""
        providers = [LLMProvider.LOCAL]
        if self._anthropic_key:
            providers.append(LLMProvider.ANTHROPIC)
        if self._openai_key:
            providers.append(LLMProvider.OPENAI)
        if self._openrouter_key:
            providers.append(LLMProvider.OPENROUTER)
        return providers

    def is_available_for(self, classification: DataClassification) -> bool:
        """Check if a provider is available for the given classification."""
        needed = self._router.select(classification)
        return needed in self.available_providers()

    # ----- Retry / backoff -----

    def compute_backoff_delays(self) -> list[float]:
        """Compute exponential backoff delays for retries."""
        return [self.base_delay * (2**i) for i in range(self.max_retries)]

    # ----- Token tracking -----

    def record_usage(self, usage: TokenUsage) -> None:
        """Record token usage from a call."""
        self._usage_log.append(usage)

    def cumulative_usage(self) -> TokenUsage:
        """Return cumulative token usage across all recorded calls."""
        total_in = sum(u.input_tokens for u in self._usage_log)
        total_out = sum(u.output_tokens for u in self._usage_log)
        return TokenUsage(input_tokens=total_in, output_tokens=total_out)

    def reset_usage(self) -> None:
        """Reset cumulative token usage."""
        self._usage_log.clear()
