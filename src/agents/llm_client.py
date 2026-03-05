"""LLM client abstraction — MVP-8 + Sprint 9 provider rollout.

Unified interface for Anthropic/OpenAI/OpenRouter with:
- Workspace classification-based routing (RESTRICTED → local,
  CONFIDENTIAL → enterprise ZDR, PUBLIC → any)
- Hard policy enforcement: RESTRICTED never reaches external providers
- Structured JSON output with Pydantic validation
- Retry with exponential backoff
- Token usage tracking and provider observability

Agents use this client — they NEVER compute economic results.
"""

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, TypeVar

from pydantic import BaseModel

from src.models.common import DataClassification

T = TypeVar("T", bound=BaseModel)

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ProviderUnavailableError(Exception):
    """Raised when the required LLM provider is unavailable or all retries exhausted."""

    def __init__(
        self,
        message: str,
        *,
        reason_code: str = "PROVIDER_UNAVAILABLE",
        agent_name: str = "",
        environment: str = "",
    ) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.agent_name = agent_name
        self.environment = environment


# ---------------------------------------------------------------------------
# Provider enum
# ---------------------------------------------------------------------------


_CLOUD_PROVIDERS = frozenset({"ANTHROPIC", "OPENAI", "OPENROUTER"})


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
    """Structured request to an LLM provider.

    For structured output callers, set ``output_schema`` and leave
    ``structured=True`` (the default).  For free-form conversation
    (e.g. the economist copilot), set ``structured=False`` and omit
    ``output_schema``.

    When ``messages`` is provided it is sent as the full conversation
    history to the provider; otherwise a single user turn built from
    ``user_prompt`` is used.
    """

    system_prompt: str
    user_prompt: str
    output_schema: type[BaseModel] | None = None
    max_tokens: int = 1024
    temperature: float = 0.0
    messages: list[dict[str, str]] | None = None
    structured: bool = True
    model: str = ""


@dataclass
class LLMResponse:
    """Structured response from an LLM provider."""

    content: str
    parsed: BaseModel | None
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
        request_timeout: float = 60.0,
        model_anthropic: str = "claude-sonnet-4-20250514",
        model_openai: str = "gpt-4o",
        model_openrouter: str = "anthropic/claude-sonnet-4-20250514",
        routing_table: dict[DataClassification, LLMProvider] | None = None,
    ) -> None:
        self._anthropic_key = anthropic_key
        self._openai_key = openai_key
        self._openrouter_key = openrouter_key
        self.max_retries = max_retries
        self.base_delay = base_delay
        self._request_timeout = request_timeout
        self._model_anthropic = model_anthropic
        self._model_openai = model_openai
        self._model_openrouter = model_openrouter
        self._router = ProviderRouter(routing_table=routing_table)
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

    # ----- Provider call (Sprint 9) -----

    async def call(
        self,
        request: LLMRequest,
        *,
        classification: DataClassification,
    ) -> LLMResponse:
        """Call an LLM provider with classification-based routing.

        Hard policy: RESTRICTED classification is ALWAYS routed to LOCAL,
        regardless of routing table or available keys. This is the
        agent-to-math boundary's security enforcement.

        Raises:
            ProviderUnavailableError: When the required provider is not
                available or all retries are exhausted.
        """
        provider = self._router.select(classification)

        # Hard guard: RESTRICTED must NEVER reach external providers
        if classification == DataClassification.RESTRICTED:
            provider = LLMProvider.LOCAL

        # LOCAL path — deterministic, always available, no network
        if provider == LLMProvider.LOCAL:
            response = self._call_local(request)
            _logger.info(
                "LLM call complete: classification=%s provider=%s model=%s "
                "input_tokens=%d output_tokens=%d latency_ms=0",
                classification, response.provider, response.model,
                response.usage.input_tokens, response.usage.output_tokens,
            )
            return response

        # Availability check before attempting external call
        if provider not in self.available_providers():
            raise ProviderUnavailableError(
                f"Provider {provider} required for classification "
                f"{classification} but no API key configured"
            )

        t0 = time.monotonic()
        response = await self._call_external_with_retry(
            request, provider=provider,
        )
        latency_ms = (time.monotonic() - t0) * 1000

        _logger.info(
            "LLM call complete: classification=%s provider=%s model=%s "
            "input_tokens=%d output_tokens=%d latency_ms=%.1f",
            classification, response.provider, response.model,
            response.usage.input_tokens, response.usage.output_tokens,
            latency_ms,
        )
        return response

    async def call_unstructured(
        self,
        request: LLMRequest,
        *,
        classification: DataClassification | None = None,
    ) -> LLMResponse:
        """Call LLM without structured output parsing.

        Convenience wrapper that forces ``structured=False`` and clears
        ``output_schema`` so the response is returned as plain text
        without Pydantic validation.  All other request parameters
        (messages, temperature, max_tokens, etc.) are preserved.
        """
        unstructured_request = LLMRequest(
            system_prompt=request.system_prompt,
            user_prompt=request.user_prompt,
            messages=request.messages,
            output_schema=None,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            structured=False,
            model=request.model,
        )
        cls = classification if classification is not None else DataClassification.INTERNAL
        return await self.call(unstructured_request, classification=cls)

    async def _call_external_with_retry(
        self,
        request: LLMRequest,
        *,
        provider: LLMProvider,
    ) -> LLMResponse:
        """Dispatch to external provider with retry and backoff."""
        dispatch: dict[LLMProvider, Any] = {
            LLMProvider.ANTHROPIC: self._call_anthropic,
            LLMProvider.OPENAI: self._call_openai,
            LLMProvider.OPENROUTER: self._call_openrouter,
        }
        call_fn = dispatch[provider]
        delays = self.compute_backoff_delays()

        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                raw_response = await call_fn(request)
                return self._normalize_response(
                    raw_response,
                    provider=provider,
                    schema=request.output_schema,
                    structured=request.structured,
                )
            except Exception as exc:
                last_error = exc
                _logger.warning(
                    "Provider %s attempt %d/%d failed: %s",
                    provider, attempt + 1, self.max_retries, exc,
                )
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(delays[attempt])

        raise ProviderUnavailableError(
            f"All {self.max_retries} retries exhausted for {provider}: "
            f"{last_error}"
        )

    def _call_local(self, request: LLMRequest) -> LLMResponse:
        """Deterministic LOCAL provider — returns schema-valid defaults.

        Works offline with no API keys or network. Used for RESTRICTED
        workspaces and as dev/test fallback.

        When ``output_schema`` is *None* (unstructured mode) a simple
        placeholder string is returned instead of schema-derived defaults.
        """
        schema = request.output_schema
        if schema is None or not request.structured:
            return LLMResponse(
                content="",
                parsed=None,
                provider=LLMProvider.LOCAL,
                model="local-deterministic",
                usage=TokenUsage(input_tokens=0, output_tokens=0),
            )

        defaults: dict[str, Any] = {}
        for field_name, field_info in schema.model_fields.items():
            annotation = field_info.annotation
            if annotation is str:
                defaults[field_name] = "UNKNOWN"
            elif annotation is float:
                defaults[field_name] = 0.0
            elif annotation is int:
                defaults[field_name] = 0
            elif annotation is bool:
                defaults[field_name] = False
            else:
                defaults[field_name] = None

        parsed = schema.model_validate(defaults)
        content = parsed.model_dump_json()

        return LLMResponse(
            content=content,
            parsed=parsed,
            provider=LLMProvider.LOCAL,
            model="local-deterministic",
            usage=TokenUsage(input_tokens=0, output_tokens=0),
        )

    def _normalize_response(
        self,
        raw: Any,
        *,
        provider: LLMProvider,
        schema: type[T] | None,
        structured: bool = True,
    ) -> LLMResponse:
        """Normalize raw provider response into LLMResponse.

        When ``structured`` is *True* and a ``schema`` is provided the
        raw text is parsed and validated against the Pydantic model.
        In unstructured mode (``structured=False`` or ``schema is None``)
        the ``parsed`` field is set to *None*.
        """
        if provider == LLMProvider.ANTHROPIC:
            text = raw.content[0].text
            model = raw.model
            usage = TokenUsage(
                input_tokens=raw.usage.input_tokens,
                output_tokens=raw.usage.output_tokens,
            )
        elif provider == LLMProvider.OPENAI:
            text = raw.choices[0].message.content
            model = raw.model
            usage = TokenUsage(
                input_tokens=raw.usage.prompt_tokens,
                output_tokens=raw.usage.completion_tokens,
            )
        elif provider == LLMProvider.OPENROUTER:
            data = raw.json()
            text = data["choices"][0]["message"]["content"]
            model = data.get("model", "openrouter/unknown")
            usage_data = data.get("usage", {})
            usage = TokenUsage(
                input_tokens=usage_data.get("prompt_tokens", 0),
                output_tokens=usage_data.get("completion_tokens", 0),
            )
        else:
            raise ValueError(f"Cannot normalize response from provider: {provider}")

        if structured and schema is not None:
            parsed = self.parse_structured_output(raw=text, schema=schema)
        else:
            parsed = None

        self.record_usage(usage)

        return LLMResponse(
            content=text,
            parsed=parsed,
            provider=provider,
            model=model,
            usage=usage,
        )

    async def _call_anthropic(self, request: LLMRequest) -> Any:
        """Call Anthropic API via SDK. Returns raw SDK response."""
        import anthropic

        client = anthropic.AsyncAnthropic(
            api_key=self._anthropic_key,
            timeout=self._request_timeout,
        )
        msgs = request.messages if request.messages else [{"role": "user", "content": request.user_prompt}]
        model = request.model or self._model_anthropic
        return await client.messages.create(
            model=model,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            system=request.system_prompt,
            messages=msgs,
        )

    async def _call_openai(self, request: LLMRequest) -> Any:
        """Call OpenAI API via SDK. Returns raw SDK response."""
        import openai

        client = openai.AsyncOpenAI(
            api_key=self._openai_key,
            timeout=self._request_timeout,
        )
        msgs = request.messages if request.messages else [{"role": "user", "content": request.user_prompt}]
        full_msgs = [{"role": "system", "content": request.system_prompt}] + msgs
        model = request.model or self._model_openai
        return await client.chat.completions.create(
            model=model,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            messages=full_msgs,
        )

    async def _call_openrouter(self, request: LLMRequest) -> Any:
        """Call OpenRouter API via httpx. Returns raw httpx Response."""
        import httpx

        msgs = request.messages if request.messages else [{"role": "user", "content": request.user_prompt}]
        full_msgs = [{"role": "system", "content": request.system_prompt}] + msgs

        model = request.model or self._model_openrouter

        async with httpx.AsyncClient(timeout=self._request_timeout) as http:
            resp = await http.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._openrouter_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": request.max_tokens,
                    "temperature": request.temperature,
                    "messages": full_msgs,
                },
            )
            resp.raise_for_status()
            return resp
