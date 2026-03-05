"""ChatToolExecutor — dispatches copilot tool calls to handlers (Sprint 27).

Executes tool calls proposed by the EconomistCopilot, enforcing per-turn
safety caps and measuring latency. Stub handlers return structured JSON;
real implementations will be wired in later sprints.

Agent-to-Math Boundary: this executor dispatches to deterministic engine
endpoints — it never performs economic computations itself.
"""

from __future__ import annotations

import logging
import time
from typing import Callable, Awaitable

from src.models.chat import ToolCall, ToolExecutionResult

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Safety caps
# ------------------------------------------------------------------
MAX_TOOL_CALLS_PER_TURN = 5
_MAX_RUN_ENGINE_PER_TURN = 1
_MAX_CREATE_EXPORT_PER_TURN = 1

# Tools with per-turn caps (tool_name -> max per turn)
_PER_TOOL_CAPS: dict[str, int] = {
    "run_engine": _MAX_RUN_ENGINE_PER_TURN,
    "create_export": _MAX_CREATE_EXPORT_PER_TURN,
}


# ------------------------------------------------------------------
# Stub handlers
# ------------------------------------------------------------------

async def _handle_lookup_data(arguments: dict) -> dict:
    """Stub: look up economic data."""
    return {"stub": True, "tool": "lookup_data", "arguments": arguments}


async def _handle_build_scenario(arguments: dict) -> dict:
    """Stub: build a scenario spec from user intent."""
    return {"stub": True, "tool": "build_scenario", "arguments": arguments}


async def _handle_run_engine(arguments: dict) -> dict:
    """Stub: run the deterministic I-O engine."""
    return {"stub": True, "tool": "run_engine", "arguments": arguments}


async def _handle_narrate_results(arguments: dict) -> dict:
    """Stub: narrate engine results into natural language."""
    return {"stub": True, "tool": "narrate_results", "arguments": arguments}


async def _handle_create_export(arguments: dict) -> dict:
    """Stub: create an export (Excel/PPT/PDF)."""
    return {"stub": True, "tool": "create_export", "arguments": arguments}


# Handler registry: tool_name -> async handler(arguments) -> dict
_HANDLER_REGISTRY: dict[str, Callable[[dict], Awaitable[dict]]] = {
    "lookup_data": _handle_lookup_data,
    "build_scenario": _handle_build_scenario,
    "run_engine": _handle_run_engine,
    "narrate_results": _handle_narrate_results,
    "create_export": _handle_create_export,
}


# ------------------------------------------------------------------
# Executor
# ------------------------------------------------------------------


class ChatToolExecutor:
    """Dispatches tool calls to handlers with safety caps and latency tracking."""

    def _get_handler(
        self, tool_name: str,
    ) -> Callable[[dict], Awaitable[dict]] | None:
        """Return the handler for a tool, or None if unknown."""
        return _HANDLER_REGISTRY.get(tool_name)

    async def execute(self, tool_call: ToolCall) -> ToolExecutionResult:
        """Execute a single tool call.

        Returns a ToolExecutionResult with status, latency, and result/error.
        Unknown tools return status='error' with reason_code='unknown_tool'.
        Exceptions are caught and returned as status='error'.
        """
        handler = self._get_handler(tool_call.tool_name)
        if handler is None:
            return ToolExecutionResult(
                tool_name=tool_call.tool_name,
                status="error",
                reason_code="unknown_tool",
                error_summary=f"Unknown tool: {tool_call.tool_name}",
            )

        start = time.monotonic()
        try:
            result = await handler(tool_call.arguments)
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return ToolExecutionResult(
                tool_name=tool_call.tool_name,
                status="success",
                latency_ms=elapsed_ms,
                result=result,
            )
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            _logger.exception("Tool %s failed", tool_call.tool_name)
            return ToolExecutionResult(
                tool_name=tool_call.tool_name,
                status="error",
                reason_code="handler_exception",
                retryable=True,
                latency_ms=elapsed_ms,
                error_summary=str(exc),
            )

    async def execute_all(
        self, tool_calls: list[ToolCall],
    ) -> list[ToolExecutionResult]:
        """Execute tool calls sequentially, enforcing safety caps.

        - Overall cap: MAX_TOOL_CALLS_PER_TURN
        - Per-tool caps: run_engine (1), create_export (1)
        - Excess calls are returned as status='blocked'
        """
        results: list[ToolExecutionResult] = []
        per_tool_counts: dict[str, int] = {}

        for tool_call in tool_calls:
            # Overall cap
            executed_count = sum(
                1 for r in results if r.status != "blocked"
            )
            if executed_count >= MAX_TOOL_CALLS_PER_TURN:
                results.append(ToolExecutionResult(
                    tool_name=tool_call.tool_name,
                    status="blocked",
                    reason_code="max_tool_calls_exceeded",
                ))
                continue

            # Per-tool cap
            tool_name = tool_call.tool_name
            cap = _PER_TOOL_CAPS.get(tool_name)
            if cap is not None:
                current = per_tool_counts.get(tool_name, 0)
                if current >= cap:
                    results.append(ToolExecutionResult(
                        tool_name=tool_name,
                        status="blocked",
                        reason_code=f"max_{tool_name}_exceeded",
                    ))
                    continue

            # Execute
            result = await self.execute(tool_call)
            results.append(result)

            # Track per-tool count (only for executed, not blocked)
            if result.status != "blocked":
                per_tool_counts[tool_name] = per_tool_counts.get(tool_name, 0) + 1

        return results
