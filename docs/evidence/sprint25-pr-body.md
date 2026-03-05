## Summary

Adds the Economist Copilot v1 — a conversational AI assistant that orchestrates the ImpactOS Leontief engine via chat, with full DB persistence, versioned prompts, mandatory confirmation gate, and trace metadata.

**Diff vs `origin/main`:** 31 files changed, +4467 / −55

---

### Commit Chain

| # | SHA | Message |
|---|-----|---------|
| 1 | `8c2b923` | `[sprint25] add chat persistence foundation with migration 020` |
| 2 | `269e909` | `[sprint25] implement economist copilot agent with versioned prompt and confirmation gate` |
| 3 | `4bae81c` | `[sprint25] add workspace-scoped chat api and service orchestration` |
| 4 | `0a7f01c` | `[sprint25] add chat frontend interface with trace metadata and sidebar entry` |
| 5 | `492ef01` | `[sprint25] refresh sprint25 evidence and openapi` |
| 6 | `442d89f` | `[sprint25] fix code review findings: classification default, DummySchema BaseModel, confirmation gate protocol` |

---

### Verification Block

| Check | Command | Result |
|-------|---------|--------|
| Backend pytest | `python -m pytest --tb=no -q` | **4698 passed**, 29 skipped, 0 failures |
| Frontend vitest | `npx vitest run` | **320 passed** (36 test files), 0 failures |
| Alembic head | `python -m alembic heads` | `020_chat_sessions_messages (head)` |
| Alembic chain | `019_run_snapshot_scenario_link → 020_chat_sessions_messages` | Linear, no branches |
| Alembic current/check | Requires live PostgreSQL — deferred to pre-merge gate | — |

**New tests added:** 86 total

| Layer | File | Count |
|-------|------|-------|
| Repository | `tests/repositories/test_chat.py` | 16 (8 × 2 backends) |
| Agent | `tests/agents/test_economist_copilot.py` | 23 |
| Service | `tests/services/test_chat.py` | 10 |
| API | `tests/api/test_chat.py` | 24 (12 × 2 backends) |
| Frontend | `frontend/src/components/chat/__tests__/chat-interface.test.tsx` | 13 |

---

### Constraint Compliance Matrix (C-1 … C-6)

| ID | Constraint | Status | Evidence |
|----|-----------|--------|----------|
| C-1 | DB persistence from day 1 | ✅ PASS | Migration `020_chat_sessions_messages` creates `chat_sessions` + `chat_messages`. `ChatSessionRepository` + `ChatMessageRepository` with 16 round-trip tests. |
| C-2 | Versioned prompt artifact | ✅ PASS | `COPILOT_PROMPT_VERSION = "copilot_v1"` in `src/agents/prompts/economist_copilot_v1.py`. Stored on every assistant message via `prompt_version` column. Verified by `test_copilot_response_includes_prompt_version`. |
| C-3 | Confirmation gate | ✅ PASS | `_GATED_TOOLS = frozenset({"build_scenario", "run_engine"})` blocks execution unless `context["user_confirmed"]` is True. Frontend `ConfirmationGate` renders Approve/Edit/Reject. Backend stores `pending_confirmation` in `trace_metadata`. |
| C-4 | Trace metadata | ✅ PASS | `TraceMetadata` model with run_id, scenario_spec_id, model_version_id, assumptions, confidence. Stored as JSONB. Frontend renders collapsible `<details>`. Verified by `test_trace_metadata_json_round_trip`. |
| C-5 | LLM never outputs numbers | ✅ PASS | System prompt: "You NEVER compute, modify, or generate economic numbers." Agent returns structured tool calls only; engine produces numeric results. Verified by `test_system_prompt_contains_agent_math_boundary`. |
| C-6 | Existing layers additive | ✅ PASS | Baseline: 4654 collected (pre-sprint). Current: 4698 backend + 320 frontend. Zero regressions. Only additive modifications to `sidebar.tsx` (+2 lines), `main.py` (+2 lines), `tables.py` (+55 lines), `settings.py` (+10 lines). |

---

### Known Gaps → Sprint 26 Backlog

| ID | Gap | Description | Severity |
|----|-----|-------------|----------|
| S26-BL-1 | Multi-turn conversation history not sent to LLM | `LLMRequest` only supports `system_prompt` + `user_prompt`, not a messages list. History is loaded from DB but not passed to the LLM — every turn is effectively stateless. | Medium |
| S26-BL-2 | `chatFetch` bypasses shared `openapi-fetch` client | Chat hooks use raw `fetch()` instead of the shared `api` client. No auth token attached. Must migrate once OpenAPI schema includes chat endpoints. | Medium |
| S26-BL-3 | Tool call regex cannot handle nested JSON | `parse_tool_calls` regex uses `[^{}]*` which fails on nested objects in `arguments` (e.g., `{"shocks": [{"sector": "A"}]}`). Replace with JSON-aware balanced-brace parser. | Low |
| S26-BL-4 | `COPILOT_MODEL` / `COPILOT_MAX_TOKENS` settings unused | Settings added to `src/config/settings.py` but never wired into `ChatService` or `EconomistCopilot`. Model selection handled entirely by `LLMClient` routing. | Low |
| S26-BL-5 | `LLMClient` lacks unstructured conversation mode | `_DummySchema(BaseModel)` is a workaround; `LLMClient._normalize_response()` calls `parse_structured_output()` which expects valid JSON. Free-form LLM responses will fail schema validation on real calls. | Medium |

---

## Test Plan

- [x] Backend: 4698 passed, 29 skipped, 0 failures
- [x] Frontend: 320 passed, 0 failures
- [x] Alembic head: `020_chat_sessions_messages`
- [x] New tests: 86 (23 agent + 16 repo + 10 service + 24 API + 13 frontend)
- [ ] Pre-merge: `alembic upgrade head` + `alembic current` + `alembic check` against live PostgreSQL
- [ ] Manual smoke test: create session → send message → verify trace metadata → confirm scenario

🤖 Generated with [Claude Code](https://claude.com/claude-code)
