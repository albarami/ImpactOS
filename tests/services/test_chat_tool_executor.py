"""Tests for ChatToolExecutor (Sprint 27).

Verifies ToolExecutionResult model, safety caps, latency tracking,
and error handling in the tool execution skeleton.
"""

import pytest
from unittest.mock import AsyncMock, patch

from src.models.chat import ToolCall, ToolExecutionResult
from src.services.chat_tool_executor import (
    ChatToolExecutor,
    MAX_TOOL_CALLS_PER_TURN,
    _MAX_RUN_ENGINE_PER_TURN,
    _MAX_CREATE_EXPORT_PER_TURN,
)

pytestmark = pytest.mark.anyio


class TestToolExecutionResult:
    """S27-1a: ToolExecutionResult model validation."""

    def test_success_result(self):
        r = ToolExecutionResult(
            tool_name="lookup_data",
            status="success",
            latency_ms=42,
            result={"data": [1, 2, 3]},
        )
        assert r.status == "success"
        assert r.tool_name == "lookup_data"
        assert r.latency_ms == 42
        assert r.result == {"data": [1, 2, 3]}
        assert r.error_summary is None
        assert r.retryable is False

    def test_error_result(self):
        r = ToolExecutionResult(
            tool_name="run_engine",
            status="error",
            reason_code="handler_exception",
            retryable=True,
            error_summary="Connection timeout",
        )
        assert r.status == "error"
        assert r.reason_code == "handler_exception"
        assert r.retryable is True
        assert r.error_summary == "Connection timeout"
        assert r.result is None

    def test_blocked_result(self):
        r = ToolExecutionResult(
            tool_name="run_engine",
            status="blocked",
            reason_code="max_run_engine_exceeded",
        )
        assert r.status == "blocked"
        assert r.reason_code == "max_run_engine_exceeded"
        assert r.latency_ms == 0


class TestChatToolExecutorBasics:
    """S27-1a: ChatToolExecutor skeleton behavior."""

    def test_max_tool_calls_constant(self):
        assert MAX_TOOL_CALLS_PER_TURN == 5

    def test_max_run_engine_constant(self):
        assert _MAX_RUN_ENGINE_PER_TURN == 1

    def test_max_create_export_constant(self):
        assert _MAX_CREATE_EXPORT_PER_TURN == 1

    async def test_unknown_tool_returns_error(self):
        executor = ChatToolExecutor()
        tc = ToolCall(tool_name="nonexistent_tool", arguments={})
        result = await executor.execute(tc)
        assert result.status == "error"
        assert result.reason_code == "unknown_tool"
        assert "nonexistent_tool" in (result.error_summary or "")

    async def test_known_tool_returns_success(self):
        executor = ChatToolExecutor()
        tc = ToolCall(tool_name="lookup_data", arguments={"query": "GDP"})
        result = await executor.execute(tc)
        assert result.status == "success"
        assert result.result is not None
        assert result.result["stub"] is True

    async def test_execute_all_respects_cap(self):
        executor = ChatToolExecutor()
        # Create more tool calls than the cap allows
        calls = [
            ToolCall(tool_name="lookup_data", arguments={"i": i})
            for i in range(MAX_TOOL_CALLS_PER_TURN + 3)
        ]
        results = await executor.execute_all(calls)
        assert len(results) == MAX_TOOL_CALLS_PER_TURN + 3

        executed = [r for r in results if r.status == "success"]
        blocked = [r for r in results if r.status == "blocked"]
        assert len(executed) == MAX_TOOL_CALLS_PER_TURN
        assert len(blocked) == 3
        for b in blocked:
            assert b.reason_code == "max_tool_calls_exceeded"

    async def test_execute_all_caps_run_engine_to_one(self):
        executor = ChatToolExecutor()
        calls = [
            ToolCall(tool_name="run_engine", arguments={}),
            ToolCall(tool_name="run_engine", arguments={}),
            ToolCall(tool_name="lookup_data", arguments={}),
        ]
        results = await executor.execute_all(calls)
        assert len(results) == 3

        # First run_engine should succeed
        assert results[0].status == "success"
        assert results[0].tool_name == "run_engine"

        # Second run_engine should be blocked
        assert results[1].status == "blocked"
        assert results[1].reason_code == "max_run_engine_exceeded"

        # lookup_data should still succeed
        assert results[2].status == "success"
        assert results[2].tool_name == "lookup_data"

    async def test_execute_all_caps_create_export_to_one(self):
        executor = ChatToolExecutor()
        calls = [
            ToolCall(tool_name="create_export", arguments={}),
            ToolCall(tool_name="create_export", arguments={}),
        ]
        results = await executor.execute_all(calls)
        assert results[0].status == "success"
        assert results[1].status == "blocked"
        assert results[1].reason_code == "max_create_export_exceeded"

    async def test_execute_measures_latency(self):
        executor = ChatToolExecutor()
        tc = ToolCall(tool_name="lookup_data", arguments={})
        result = await executor.execute(tc)
        assert result.status == "success"
        # Latency should be non-negative (stubs are fast, so >= 0)
        assert result.latency_ms >= 0

    async def test_execute_catches_exceptions(self):
        executor = ChatToolExecutor()
        tc = ToolCall(tool_name="lookup_data", arguments={})

        # Patch the handler to raise
        async def _failing_handler(args):
            raise RuntimeError("simulated failure")

        with patch.dict(
            "src.services.chat_tool_executor._HANDLER_REGISTRY",
            {"lookup_data": _failing_handler},
        ):
            result = await executor.execute(tc)

        assert result.status == "error"
        assert result.reason_code == "handler_exception"
        assert result.retryable is True
        assert "simulated failure" in (result.error_summary or "")
        assert result.latency_ms >= 0

    async def test_execute_all_empty_list(self):
        executor = ChatToolExecutor()
        results = await executor.execute_all([])
        assert results == []

    async def test_get_handler_returns_none_for_unknown(self):
        executor = ChatToolExecutor()
        assert executor._get_handler("unknown") is None

    async def test_get_handler_returns_callable_for_known(self):
        executor = ChatToolExecutor()
        handler = executor._get_handler("lookup_data")
        assert handler is not None
        assert callable(handler)
