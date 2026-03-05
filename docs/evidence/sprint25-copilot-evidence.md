# Sprint 25 Constraint Compliance Evidence: Economist Copilot v1

**Date:** 2026-03-05
**Branch:** `phase3-sprint25-economist-copilot-v1`
**Head commit:** `0a7f01c`

---

## Overview

Sprint 25 delivers the Economist Copilot v1 -- a conversational AI assistant for Strategic Gears economists. The copilot orchestrates the ImpactOS Leontief engine through natural-language dialogue while strictly enforcing the agent-to-math boundary. This evidence document demonstrates compliance with the 6 sprint constraints.

---

## C-1: DB Persistence from Day 1

**Requirement:** Chat sessions and messages must persist in PostgreSQL from the first commit.

**Evidence:**

- **Migration `020_chat_sessions_messages`** (`alembic/versions/020_chat_sessions_messages.py`):
  - Creates `chat_sessions` table with columns: `session_id` (PK), `workspace_id` (FK to workspaces), `title`, `created_at`, `updated_at`
  - Creates `chat_messages` table with columns: `message_id` (PK), `session_id` (FK to chat_sessions), `role`, `content`, `tool_calls` (JSONB), `tool_results` (JSONB), `trace_metadata` (JSONB), `prompt_version`, `model_provider`, `model_id`, `token_usage` (JSONB), `created_at`
  - Index `ix_chat_sessions_workspace` on `(workspace_id, updated_at)` for efficient listing
  - Index `ix_chat_messages_session` on `(session_id, created_at)` for chronological retrieval
  - Committed at `8c2b923` (first sprint 25 commit)

- **ORM rows** defined in `src/db/tables.py` (lines 1099+): `ChatSessionRow`, `ChatMessageRow`

- **Repository layer** (`src/repositories/chat.py`):
  - `ChatSessionRepository`: `create`, `get`, `list_for_workspace`, `update_title`, `touch`
  - `ChatMessageRepository`: `create`, `list_for_session`

- **Repository tests** (`tests/repositories/test_chat.py` -- 8 tests):
  - `test_create_session_round_trip` -- create + fetch verifies persistence
  - `test_session_workspace_isolation` -- cross-workspace get returns None
  - `test_list_sessions_for_workspace` -- ordered listing by updated_at desc
  - `test_update_session_title` -- title update persists
  - `test_create_message_round_trip` -- message create + list verifies persistence
  - `test_messages_ordered_by_created_at` -- chronological ordering
  - `test_message_with_trace_metadata` -- JSONB trace round-trip
  - `test_message_with_tool_calls` -- JSONB tool_calls round-trip

---

## C-2: Versioned Prompt Artifact

**Requirement:** Every assistant message must carry a prompt version string for reproducibility.

**Evidence:**

- **Version constant:** `COPILOT_PROMPT_VERSION = "copilot_v1"` in `src/agents/prompts/economist_copilot_v1.py` (line 7)

- **Stored per message:** `prompt_version` column (VARCHAR 50) in `chat_messages` table, populated by `ChatService.send_message()` from `CopilotResponse.prompt_version`

- **CopilotResponse default:** `prompt_version: str = COPILOT_PROMPT_VERSION` in `src/agents/economist_copilot.py` (line 63)

- **Tests:**
  - `test_prompt_version_is_string` in `tests/agents/test_economist_copilot.py` (class `TestVersionedPrompt`)
  - `test_response_has_prompt_version` in `tests/agents/test_economist_copilot.py` (class `TestCopilotResponse`) -- verifies CopilotResponse carries version
  - `test_send_message_returns_prompt_version` in `tests/services/test_chat.py` (class `TestChatService`) -- verifies service propagates version to API response

---

## C-3: Scenario Confirmation Gate

**Requirement:** `build_scenario` and `run_engine` tool calls must be blocked until the user explicitly confirms.

**Evidence:**

- **Backend gate:** `_GATED_TOOLS = frozenset({"build_scenario", "run_engine"})` in `src/agents/economist_copilot.py` (line 29). In `EconomistCopilot.process_turn()`, if `tool_name in _GATED_TOOLS and not ctx.get("user_confirmed", False)`, the response is returned with `pending_confirmation` set (lines 186-201).

- **ConfirmationRequiredError:** Raised with `tool_name` and `proposed_args` attributes (`src/agents/economist_copilot.py`, lines 35-43).

- **Service integration:** `ChatService.send_message()` passes `confirm_scenario` from the API request as `context["user_confirmed"]` (`src/services/chat.py`, line 179).

- **API endpoint:** `SendMessageRequest.confirm_scenario: bool | None` field (`src/models/chat.py`, line 72). Endpoint at `POST /v1/workspaces/{ws}/chat/sessions/{sid}/messages`.

- **Frontend gate:** `ConfirmationGate` component (`frontend/src/components/chat/confirmation-gate.tsx`) renders Approve / Edit / Reject buttons with amber warning styling. Integrated into `ChatInterface` (`frontend/src/components/chat/chat-interface.tsx`, lines 148-158).

- **Tests:**
  - `test_prompt_contains_confirmation_gate` in `tests/agents/test_economist_copilot.py` (class `TestVersionedPrompt`) -- system prompt contains gate rules
  - `test_gated_tools_require_confirmation` in `tests/agents/test_economist_copilot.py` (class `TestToolDefinitions`) -- build_scenario and run_engine marked requires_confirmation
  - `test_response_with_pending_confirmation` in `tests/agents/test_economist_copilot.py` (class `TestCopilotResponse`)
  - `test_confirmation_error_attributes` in `tests/agents/test_economist_copilot.py` (class `TestConfirmationGate`)
  - `test_send_message_with_confirm_scenario` in `tests/api/test_chat.py` (class `TestSendMessage`)
  - Frontend: `renders confirmation gate when last message has pending tool call` in `frontend/src/components/chat/__tests__/chat-interface.test.tsx`
  - Frontend: `calls approve with confirm_scenario: true` in `frontend/src/components/chat/__tests__/chat-interface.test.tsx`

---

## C-4: Trace Metadata in Every Results Response

**Requirement:** Every assistant message carrying engine results must include provenance trace metadata.

**Evidence:**

- **TraceMetadata model** (`src/models/chat.py`, lines 8-19):
  - Fields: `run_id`, `scenario_spec_id`, `scenario_spec_version`, `model_version_id`, `io_table`, `multiplier_type`, `assumptions`, `confidence`, `confidence_reasons`

- **DB storage:** `trace_metadata` JSONB column on `chat_messages` table (`alembic/versions/020_chat_sessions_messages.py`, line 54)

- **Service propagation:** `ChatService.send_message()` extracts `trace_metadata` from `CopilotResponse` and persists it as JSONB (`src/services/chat.py`, lines 190-192)

- **Frontend rendering:** `TraceMetadata` component (`frontend/src/components/chat/trace-metadata.tsx`) renders a collapsible `<details>` element showing run_id, scenario_spec_id, model_version_id, io_table, multiplier_type, confidence (with badge), confidence_reasons, and assumptions.

- **Tests:**
  - `test_message_with_trace_metadata` in `tests/repositories/test_chat.py` (class `TestChatMessageRepository`) -- JSONB round-trip with all trace fields
  - `test_prompt_trace_metadata_required` in `tests/agents/test_economist_copilot.py` (class `TestVersionedPrompt`) -- system prompt mandates trace fields
  - `test_send_message_returns_trace_metadata` in `tests/services/test_chat.py` (class `TestChatService`) -- service returns trace from copilot response
  - Frontend: `shows trace metadata on assistant message with trace data` in `frontend/src/components/chat/__tests__/chat-interface.test.tsx`

---

## C-5: LLM Never Outputs Numbers

**Requirement:** The agent-to-math boundary must be enforced -- the LLM produces structured tool calls only, never economic numbers.

**Evidence:**

- **System prompt guardrails** in `src/agents/prompts/economist_copilot_v1.py` (line 69):
  - `"You NEVER produce economic numbers yourself. ALL numeric outputs come from the deterministic engine via ResultSets."`
  - `"You produce STRUCTURED JSON for tool calls only. Never compute economic results."`
  - Guardrails section: `"NEVER invent numbers"`

- **Architecture enforcement:**
  - `EconomistCopilot.process_turn()` returns `CopilotResponse` with text content + optional `tool_calls` list. Tool calls are validated via `validate_tool_call()` against `_VALID_TOOLS`.
  - Numeric results only come through `narrate_results` tool, which takes engine `ResultSet` data as input (not LLM-generated numbers).

- **Tests:**
  - `test_prompt_agent_math_boundary` in `tests/agents/test_economist_copilot.py` (class `TestVersionedPrompt`) -- verifies system prompt references deterministic engine / ResultSet
  - `test_prompt_contains_critical_rules` in `tests/agents/test_economist_copilot.py` (class `TestVersionedPrompt`) -- verifies "NEVER produce economic numbers" rule present

---

## C-6: Existing Layers Remain Additive

**Requirement:** No existing tests break, only new files added (plus necessary integration points).

**Evidence:**

- **Baseline at sprint start (post-Sprint 24 merge):** 4932 backend tests collected (commit `1146f70`)

- **New backend test files added (Sprint 25):**
  - `tests/repositories/test_chat.py` -- 8 tests
  - `tests/agents/test_economist_copilot.py` -- 23 tests
  - `tests/services/test_chat.py` -- 10 tests
  - `tests/api/test_chat.py` -- 12 tests
  - Total new backend tests: 53

- **New frontend test file:**
  - `frontend/src/components/chat/__tests__/chat-interface.test.tsx` -- 13 tests

- **New source files (not modifications to existing):**
  - `alembic/versions/020_chat_sessions_messages.py` -- migration
  - `src/models/chat.py` -- Pydantic models
  - `src/repositories/chat.py` -- repository layer
  - `src/services/chat.py` -- service layer
  - `src/api/chat.py` -- API endpoints
  - `src/agents/economist_copilot.py` -- copilot agent
  - `src/agents/prompts/economist_copilot_v1.py` -- versioned prompt
  - `frontend/src/lib/api/hooks/useChat.ts` -- React Query hooks
  - `frontend/src/components/chat/chat-interface.tsx` -- main chat UI
  - `frontend/src/components/chat/confirmation-gate.tsx` -- confirmation gate component
  - `frontend/src/components/chat/trace-metadata.tsx` -- trace display component
  - `frontend/src/components/chat/message-bubble.tsx` -- message bubble component
  - `frontend/src/app/w/[workspaceId]/chat/` -- chat page route

- **Existing file modifications:**
  - `src/db/tables.py` -- added `ChatSessionRow` and `ChatMessageRow` ORM definitions (additive, no existing rows modified)
  - `src/api/main.py` -- registered chat router (additive)
  - `frontend/src/components/layout/sidebar.tsx` -- added "Chat" nav entry (additive, single line)

- **Summary:** Backend 4932 + 53 new = 4985 backend tests. Frontend 13 new chat tests. All pre-existing tests unaffected.

---

## Sprint 25 Commit Log

| Commit | Description |
|--------|-------------|
| `8c2b923` | add chat persistence foundation with migration 020 |
| `269e909` | implement economist copilot agent with versioned prompt and confirmation gate |
| `4bae81c` | add workspace-scoped chat api and service orchestration |
| `0a7f01c` | add chat frontend interface with trace metadata and sidebar entry |

---

## Files Delivered

### Backend
- `alembic/versions/020_chat_sessions_messages.py`
- `src/models/chat.py`
- `src/repositories/chat.py`
- `src/services/chat.py`
- `src/api/chat.py`
- `src/agents/economist_copilot.py`
- `src/agents/prompts/economist_copilot_v1.py`
- `tests/repositories/test_chat.py`
- `tests/agents/test_economist_copilot.py`
- `tests/services/test_chat.py`
- `tests/api/test_chat.py`

### Frontend
- `frontend/src/lib/api/hooks/useChat.ts`
- `frontend/src/components/chat/chat-interface.tsx`
- `frontend/src/components/chat/confirmation-gate.tsx`
- `frontend/src/components/chat/trace-metadata.tsx`
- `frontend/src/components/chat/message-bubble.tsx`
- `frontend/src/components/chat/__tests__/chat-interface.test.tsx`
- `frontend/src/app/w/[workspaceId]/chat/` (page route)

### Docs
- `openapi.json` (regenerated with chat endpoints)
- `docs/evidence/sprint25-copilot-evidence.md` (this file)
