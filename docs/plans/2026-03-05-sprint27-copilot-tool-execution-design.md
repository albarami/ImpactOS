# Sprint 27 Design: Copilot Tool Execution & Run/Export Orchestration

**Date:** 2026-03-05
**Status:** Approved
**Sprint:** 27 (Copilot Operationalization)

## Problem

The Economist Copilot chat system currently:
- Never wires a real `EconomistCopilot` instance into the API layer (`copilot=None` always).
- Returns "Copilot is not configured" for every `send_message` call.
- Parses tool calls from LLM responses but never executes them (`ToolCall.result` is always `None`).
- Has confirmation gate logic that works but gates nothing since no execution follows.
- Has `TraceMetadata` fields (`run_id`, `scenario_spec_id`, etc.) that are never populated.
- Frontend renders `resolvedToolCalls` and `ConfirmationGate` but no tool results ever arrive.

## Solution: Standalone ChatToolExecutor (Approach A)

### Architecture

```
User -> ChatAPI.send_message()
         -> ChatService.send_message()
              -> EconomistCopilot.process_turn()     [LLM-only, returns parsed tool calls]
              -> Confirmation gate check              [blocks gated tools if unconfirmed]
              -> ChatToolExecutor.execute_tool_calls() [sequential, capped dispatch]
                   -> lookup_data    -> data repos/services
                   -> build_scenario -> ScenarioVersionRepository
                   -> run_engine     -> engine.leontief (deterministic)
                   -> narrate_results -> reads persisted ResultSets, returns to LLM
                   -> create_export   -> ExportService (fire-and-return)
              -> Persist message with tool_calls[*].result + trace_metadata
         -> Return ChatMessageResponse
```

### Key Constraints

- **Agent-to-math boundary**: `EconomistCopilot` stays LLM-only. `ChatToolExecutor` handles deterministic dispatch.
- **No HTTP self-calls**: Executor calls repos/services directly via imports.
- **Sequential execution**: Tool N can depend on tool N-1's result.
- **Safety caps**: Max 5 tool calls per turn. At most 1 `run_engine` and 1 `create_export` per turn.
- **Synchronous**: All tools execute inline during `send_message`, except `create_export` which is fire-and-return.

## Contract: ToolExecutionResult

```python
class ToolExecutionResult(BaseModel):
    tool_name: str
    status: Literal["success", "error", "blocked"]
    reason_code: str = ""
    retryable: bool = False
    latency_ms: int = 0
    result: dict | None = None
    error_summary: str | None = None  # sanitized, no stack traces
```

Stored in `ToolCall.result` (existing `dict | None` field).

## Runtime Wiring (S27-0)

### _get_chat_service() changes

```python
def _get_chat_service(session, copilot=None):
    settings = get_settings()
    if copilot is None:
        copilot = _build_copilot(settings)
    executor = ChatToolExecutor(session)
    return ChatService(..., copilot=copilot, tool_executor=executor)
```

### _build_copilot(settings)

- If `COPILOT_ENABLED=false`: return `None`, service returns stub.
- Dev mode (`ENVIRONMENT=dev`): Create `LLMClient` with LOCAL provider if no API keys.
- Non-dev: Require valid API key config. If unavailable, raise `HTTPException(503)` with reason code — no silent stub fallback.

### New setting

- `COPILOT_ENABLED: bool = True` (default on)

## Tool Handlers

| Tool | Handler | Input | Output | Gated? | Cap |
|------|---------|-------|--------|--------|-----|
| `lookup_data` | Query data repos | `dataset_id`, `sector_codes`, `year` | Dataset rows/metadata | No | - |
| `build_scenario` | Create ScenarioSpec | `name`, `base_year`, `shock_items` | `scenario_spec_id`, `version` | Yes | - |
| `run_engine` | `compute_leontief()` | `scenario_spec_id`, `version` | `run_id`, summary results | Yes | Max 1/turn |
| `narrate_results` | Read persisted ResultSets by run_id | `run_id` | Result data for LLM narrative | No | - |
| `create_export` | Create export record, return ID | `run_id`, `mode`, `export_formats[]`, `pack_data` | `export_id`, `status: PENDING` | No | Max 1/turn |

### narrate_results source-of-truth

`narrate_results` must read persisted ResultSets from DB by `run_id`. It does NOT accept free-form result data from the LLM. This enforces the agent-to-math boundary: the LLM narrates real numbers, not invented ones.

## Trace Metadata Population

After tool execution, `ChatService` populates `TraceMetadata` fields:
- `build_scenario` -> `scenario_spec_id`, `scenario_spec_version`
- `run_engine` -> `run_id`, `model_version_id`
- Assumptions and confidence from scenario/run metadata
- `io_table` and `multiplier_type` from run parameters

## Frontend Changes

Minimal changes — existing patterns cover most of it:

- `MessageBubble` already renders `resolvedToolCalls` with expandable `<details>` blocks
- `ConfirmationGate` works unchanged
- **New**: Tool execution status badge (success/error/blocked) on tool call `<summary>`
- **New**: Deep links from trace metadata:
  - `run_id` -> `/w/{workspaceId}/runs/{runId}`
  - `export_id` in tool result -> `/w/{workspaceId}/exports/{exportId}`

## Error Handling

- Tool execution errors are caught and stored as `ToolExecutionResult(status="error", ...)`.
- Error summary is sanitized: no stack traces, no secrets.
- `retryable=True` for transient failures (DB timeouts, etc.)
- Assistant message still gets created with error context so LLM can explain on next turn.
- Never propagated as HTTP 500 — the `send_message` endpoint always returns 201.

## Non-dev Fail-Closed

When `ENVIRONMENT != dev` and required LLM provider config is missing:
- `_build_copilot()` returns `None`
- `_get_chat_service()` detects this and raises `HTTPException(503, detail="Copilot unavailable: LLM provider not configured")`
- No silent "not configured" stub in production.
