# Sprint 9: LLM Provider Rollout — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Roll out real LLM provider execution behind the existing agent boundary with classification-based routing, structured output validation, deterministic fallback, and provider observability.

**Architecture:** `LLMClient.call()` dispatches to provider-specific adapters (LOCAL/Anthropic/OpenAI/OpenRouter) based on `ProviderRouter.select(classification)`. A hard policy guard rejects external providers for RESTRICTED data. All responses are Pydantic-validated before agent consumption. When providers are unavailable or return invalid output, the system falls back to the existing deterministic library/rule path. Agents never compute economic results.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, anthropic SDK, openai SDK, httpx (OpenRouter)

---

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Provider adapter pattern | Methods on LLMClient (`_call_local`, `_call_anthropic`, etc.) | Simple, testable, no premature abstraction |
| Policy enforcement | Hard guard in `call()` before dispatch | Single enforcement point, impossible to bypass |
| LOCAL provider | Returns schema-valid deterministic JSON | Works offline, no keys, safe for RESTRICTED |
| Retry strategy | Actual loop with exponential backoff + jitter | Existing `compute_backoff_delays()` already computes delays |
| Fallback trigger | `ProviderUnavailableError` caught by agents | Agents fall back to library/rule path |
| Settings | New fields on existing `Settings` class | Consistent with project pattern |
| Observability | Structured logging via `logging` module | No new dependencies, auditable |

## Classification → Provider Routing Matrix

| Classification | Primary Provider | Fallback | External Allowed |
|---|---|---|---|
| RESTRICTED | LOCAL | (none — LOCAL always available) | **NEVER** |
| CONFIDENTIAL | ANTHROPIC | LOCAL (deterministic) | Enterprise only |
| INTERNAL | ANTHROPIC | LOCAL (deterministic) | Enterprise only |
| PUBLIC | OPENROUTER | LOCAL (deterministic) | Yes (configured) |

---

## Task 1 (S9-1 RED): Failing tests for provider adapter execution

**Files:**
- Create: `tests/agents/test_llm_client_providers.py`

Tests to write (all must FAIL):
1. `test_call_local_returns_normalized_response` — LOCAL adapter returns LLMResponse with correct fields
2. `test_call_anthropic_returns_normalized_response` — mocked SDK returns normalized response
3. `test_call_openai_returns_normalized_response` — mocked SDK returns normalized response
4. `test_call_openrouter_returns_normalized_response` — mocked httpx returns normalized response
5. `test_call_retries_on_provider_failure` — provider fails N-1 times then succeeds, retries work
6. `test_call_all_retries_exhausted_raises` — all retries fail → ProviderUnavailableError
7. `test_local_works_without_keys` — LOCAL needs no API keys or network

## Task 2 (S9-2 RED): Failing tests for classification policy enforcement

**Files:**
- Create: `tests/agents/test_llm_client_policy.py`

Tests to write (all must FAIL):
1. `test_restricted_rejects_external_provider` — RESTRICTED + any external → error
2. `test_restricted_routes_to_local_only` — RESTRICTED → LOCAL call succeeds
3. `test_confidential_requires_enterprise_key` — CONFIDENTIAL + no Anthropic key → ProviderUnavailableError
4. `test_confidential_routes_to_anthropic` — CONFIDENTIAL + Anthropic key → succeeds (mocked)
5. `test_internal_same_policy_as_confidential` — mirrors confidential behavior
6. `test_public_routes_to_openrouter` — PUBLIC + OpenRouter key → succeeds (mocked)
7. `test_public_fallback_when_no_key` — PUBLIC + no key → ProviderUnavailableError

## Task 3 (S9-1+S9-2 GREEN): Implement provider adapters + policy enforcement

**Files:**
- Modify: `src/agents/llm_client.py` — add `call()`, provider adapters, `ProviderUnavailableError`
- Modify: `src/config/settings.py` — add LLM model/timeout/retry settings

Implementation:
1. Add `ProviderUnavailableError` exception class
2. Add `call(request, classification)` method with hard policy guard
3. Add `_call_local()` — returns schema-appropriate deterministic JSON
4. Add `_call_anthropic()` — uses anthropic SDK (mocked in tests)
5. Add `_call_openai()` — uses openai SDK (mocked in tests)
6. Add `_call_openrouter()` — uses httpx (mocked in tests)
7. Add retry loop wrapping provider calls
8. Add settings for model IDs, timeouts, retries

## Task 4 (S9-3 RED): Failing tests for structured output + fallback safety

**Files:**
- Add to: `tests/agents/test_llm_client_providers.py`
- Add to: `tests/compiler/test_ai_compiler.py`

Tests:
1. `test_invalid_provider_output_raises_validation_error` — bad JSON from provider → ValueError
2. `test_partial_json_does_not_leak` — incomplete response → clean error
3. `test_compiler_falls_back_when_llm_unavailable` — AICompiler uses library path when call() raises
4. `test_agents_never_return_partial_results` — agent methods return valid Pydantic or raise

## Task 5 (S9-4 RED): Failing tests for observability

**Files:**
- Add to: `tests/agents/test_llm_client_providers.py`

Tests:
1. `test_call_logs_provider_and_model` — structured log contains provider/model
2. `test_call_logs_retry_count` — retries are logged
3. `test_token_usage_recorded_per_call` — usage tracked after successful call
4. `test_api_keys_never_logged` — log output does not contain key values

## Task 6 (S9-3+S9-4 GREEN): Implement validation safety + observability

**Files:**
- Modify: `src/agents/llm_client.py` — add logging, validation guards
- Modify: `src/compiler/ai_compiler.py` — add try/except fallback on ProviderUnavailableError

## Task 7: Reconcile + refactor shared logic

## Task 8: Code review, verification, PR
