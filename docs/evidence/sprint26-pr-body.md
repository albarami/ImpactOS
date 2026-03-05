## Summary

Copilot Hardening sprint -- burns down all 5 Sprint 25 backlog items (S26-BL-1..5) with zero new product surface and full backward compatibility.

**Branch head:** see `git log --oneline -1` after push
**Diff vs `origin/main`:** 13 files changed, +1106 / -163

---

### Commit Chain

| # | SHA | Message |
|---|-----|---------|
| 1 | `b7e418c` | `[sprint26] add multi-turn history + unstructured conversation mode to LLM client and copilot` |
| 2 | `191e705` | `[sprint26] replace regex tool parser with nested-json-safe parser` |
| 3 | `79094bc` | `[sprint26] wire copilot model/token settings into runtime` |
| 4 | `66e3d87` | `[sprint26] migrate useChat hooks to shared openapi-fetch client` |
| 5 | `f0a2931` | `[sprint26] refresh sprint26 evidence and openapi` |
| 6 | *(head)* | `[sprint26] fix code review findings: wire COPILOT_MODEL into LLMRequest, clean parser guard` |

---

### Backlog Resolutions

| ID | Gap (from Sprint 25) | Resolution |
|----|-----|-----------|
| S26-BL-1 | Multi-turn history not sent to LLM | `LLMRequest.messages` field; all 3 providers use it; `process_turn()` builds full history |
| S26-BL-5 | No unstructured conversation mode | `call_unstructured()` method; `structured` flag; `_DummySchema` removed |
| S26-BL-3 | Regex tool parser fails on nested JSON | Balanced-brace extractor (`_extract_balanced_braces`); handles nested objects, string braces |
| S26-BL-4 | COPILOT_MODEL/MAX_TOKENS unused | Settings wired through API factory -> ChatService -> context -> LLMRequest.model |
| S26-BL-2 | chatFetch bypasses shared api client | All 4 hooks migrated to `api.GET()`/`api.POST()` from openapi-fetch; BASE_URL removed |

---

### Verification Block

| Check | Command | Result |
|-------|---------|--------|
| Backend pytest | `python -m pytest --tb=no -q` | **4728 passed**, 29 skipped, 0 failures |
| Frontend vitest | `npx vitest run` | **328 passed** (37 test files), 0 failures |
| Alembic current | `alembic current` | `020_chat_sessions_messages (head)` |
| Alembic heads | `alembic heads` | `020_chat_sessions_messages (head)` |

**New tests added:** 30 total

| Layer | File | Count |
|-------|------|-------|
| LLM Client | `tests/agents/test_llm_client.py` | +14 |
| Copilot Agent | `tests/agents/test_economist_copilot.py` | +8 |
| Chat Service | `tests/services/test_chat.py` | +5 |
| Frontend Hooks | `frontend/src/lib/api/hooks/__tests__/useChat.test.ts` | +8 (new file) |

---

### Hard Constraint Compliance

| Constraint | Status | Evidence |
|-----------|--------|----------|
| Agent-to-math boundary | PASS | LLM returns text + tool calls only; engine does all computation; `call_unstructured()` returns raw text with `parsed=None` |
| Backward-compatible API | PASS | All new LLMRequest fields have defaults; existing callers (compiler, depth engine) unchanged |
| Workspace auth semantics | PASS | `require_workspace_member` on all 4 chat endpoints; session-workspace isolation unchanged |
| Confirmation gate | PASS | `_GATED_TOOLS`, `user_confirmed` context flag, `pending_confirmation` response -- all structurally identical |
| No secret leakage | PASS | No API keys logged/serialized; `call_unstructured()` copies fields, not key context |
| Fail-closed in non-dev | PASS | `ProviderUnavailableError` when no API key; RESTRICTED hard-guard to LOCAL unchanged |

---

## Test Plan

- [x] Backend: 4728 passed, 29 skipped, 0 failures
- [x] Frontend: 328 passed, 0 failures
- [x] Alembic: no new migration (hardening only)
- [x] New tests: 30 (14 LLM + 8 copilot + 5 service + 8 frontend)
- [x] Code review: APPROVE with I-1 fixed (COPILOT_MODEL now wired to LLMRequest.model)
- [ ] Manual smoke test: multi-turn chat with nested tool calls

🤖 Generated with [Claude Code](https://claude.com/claude-code)
