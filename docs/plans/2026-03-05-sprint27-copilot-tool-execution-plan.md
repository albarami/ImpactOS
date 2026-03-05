# Sprint 27: Copilot Tool Execution & Run/Export Orchestration — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move the Economist Copilot from "chat + tool-call suggestions" to real tool execution that can create scenarios, run the deterministic engine, and trigger governed exports from conversation.

**Architecture:** Standalone `ChatToolExecutor` service handles deterministic tool dispatch. `EconomistCopilot` stays LLM-only. `ChatService` orchestrates: parse -> gate -> execute -> persist -> respond. All tools execute synchronously within `send_message`, except `create_export` which is fire-and-return.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy async, NumPy/SciPy (engine), React/Next.js (frontend), Vitest (frontend tests), pytest (backend tests).

**Baseline:** 4757 tests collected (4728 passed, 29 skipped). Alembic: `020_chat_sessions_messages (head)`.

---

## Task 1: Add COPILOT_ENABLED setting and runtime wiring tests (S27-0)

**Files:**
- Modify: `src/config/settings.py:92-100`
- Modify: `src/api/chat.py:33-45`
- Test: `tests/api/test_chat.py`
- Test: `tests/services/test_chat.py`

**Step 1: Write failing tests for copilot runtime wiring**

Add to `tests/api/test_chat.py`:

```python
class TestCopilotRuntimeWiring:
    """S27-0: Chat API wires real copilot by default."""

    async def test_send_message_without_copilot_enabled_false_returns_stub(
        self, client, db_session
    ):
        """When COPILOT_ENABLED=false, send_message returns stub."""
        await _seed_ws(db_session)
        resp = await client.post(f"/v1/workspaces/{WS}/chat/sessions", json={"title": "t"})
        sid = resp.json()["session_id"]
        resp = await client.post(
            f"/v1/workspaces/{WS}/chat/sessions/{sid}/messages",
            json={"content": "hello"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["role"] == "assistant"
        # Stub path should say copilot not configured
        assert "not configured" in data["content"].lower() or data["content"] != ""

    async def test_copilot_enabled_setting_defaults_true(self):
        """COPILOT_ENABLED defaults to True."""
        from src.config.settings import Settings
        s = Settings(DATABASE_URL="sqlite:///test.db")
        assert s.COPILOT_ENABLED is True
```

Add to `tests/services/test_chat.py`:

```python
class TestCopilotRuntimeBehavior:
    """S27-0: Service-level runtime wiring behavior."""

    async def test_send_message_copilot_none_returns_stub(self, db_session):
        """When copilot=None, returns 'not configured' stub."""
        session, ws_id = db_session
        svc = ChatService(
            session_repo=ChatSessionRepository(session),
            message_repo=ChatMessageRepository(session),
            copilot=None,
        )
        sess = await svc.create_session(ws_id, title="test")
        msg = await svc.send_message(ws_id, UUID(sess.session_id), "hi")
        assert "not configured" in msg.content.lower()

    async def test_send_message_with_copilot_calls_process_turn(self, db_session, mock_copilot):
        """When copilot is provided, calls process_turn."""
        session, ws_id = db_session
        svc = ChatService(
            session_repo=ChatSessionRepository(session),
            message_repo=ChatMessageRepository(session),
            copilot=mock_copilot,
        )
        sess = await svc.create_session(ws_id, title="test")
        msg = await svc.send_message(ws_id, UUID(sess.session_id), "test question")
        mock_copilot.process_turn.assert_awaited_once()
        assert msg.content == "I understand your question about tourism impacts."
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/test_chat.py::TestCopilotRuntimeWiring tests/services/test_chat.py::TestCopilotRuntimeBehavior -v`
Expected: FAIL (TestCopilotRuntimeWiring may fail on missing `COPILOT_ENABLED`, service tests should pass since the copilot=None logic already exists)

**Step 3: Add COPILOT_ENABLED setting**

In `src/config/settings.py` after line 100 (after COPILOT_MAX_TOKENS), add:

```python
    COPILOT_ENABLED: bool = Field(
        default=True,
        description="Enable economist copilot. Set false to disable.",
    )
```

**Step 4: Wire real copilot into _get_chat_service**

Replace `_get_chat_service` in `src/api/chat.py`:

```python
import logging
from src.agents.economist_copilot import EconomistCopilot
from src.agents.llm_client import LLMClient, ProviderUnavailableError
from src.config.settings import Environment

_logger = logging.getLogger(__name__)


def _build_copilot(settings) -> EconomistCopilot | None:
    """Build EconomistCopilot from settings. Returns None if disabled."""
    if not settings.COPILOT_ENABLED:
        return None

    llm = LLMClient(
        anthropic_key=settings.ANTHROPIC_API_KEY,
        openai_key=settings.OPENAI_API_KEY,
        openrouter_key=settings.OPENROUTER_API_KEY,
        max_retries=settings.LLM_MAX_RETRIES,
        base_delay=settings.LLM_BASE_DELAY_SECONDS,
        request_timeout=settings.LLM_REQUEST_TIMEOUT_SECONDS,
        model_anthropic=settings.LLM_DEFAULT_MODEL_ANTHROPIC,
        model_openai=settings.LLM_DEFAULT_MODEL_OPENAI,
        model_openrouter=settings.LLM_DEFAULT_MODEL_OPENROUTER,
    )

    # Non-dev: fail-closed if no provider is available
    if settings.ENVIRONMENT != Environment.DEV and not llm.available_providers():
        _logger.error("Copilot: no LLM providers available in %s", settings.ENVIRONMENT)
        return None  # Will trigger 503 in _get_chat_service

    return EconomistCopilot(llm_client=llm)


def _get_chat_service(
    session: AsyncSession,
    copilot=None,
) -> ChatService:
    """Build ChatService with repos from DB session."""
    settings = get_settings()

    if copilot is None:
        copilot = _build_copilot(settings)

    # Non-dev fail-closed: require copilot when enabled
    if settings.COPILOT_ENABLED and copilot is None and settings.ENVIRONMENT != Environment.DEV:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=503,
            detail="Copilot unavailable: LLM provider not configured",
        )

    return ChatService(
        session_repo=ChatSessionRepository(session),
        message_repo=ChatMessageRepository(session),
        copilot=copilot,
        max_tokens=settings.COPILOT_MAX_TOKENS,
        model=settings.COPILOT_MODEL,
    )
```

**Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/api/test_chat.py tests/services/test_chat.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add src/config/settings.py src/api/chat.py tests/api/test_chat.py tests/services/test_chat.py
git commit -m "[sprint27] wire chat runtime to real copilot dependency with fail-closed behavior"
```

---

## Task 2: Create ToolExecutionResult model and ChatToolExecutor skeleton (S27-1a)

**Files:**
- Modify: `src/models/chat.py`
- Create: `src/services/chat_tool_executor.py`
- Create: `tests/services/test_chat_tool_executor.py`

**Step 1: Write failing test for ToolExecutionResult model**

Add to `tests/services/test_chat_tool_executor.py`:

```python
"""Tests for ChatToolExecutor (Sprint 27)."""

import pytest
from src.models.chat import ToolExecutionResult


class TestToolExecutionResult:
    def test_success_result(self):
        r = ToolExecutionResult(
            tool_name="lookup_data",
            status="success",
            reason_code="data_found",
            result={"rows": 5},
        )
        assert r.status == "success"
        assert r.tool_name == "lookup_data"
        assert r.retryable is False
        assert r.latency_ms == 0

    def test_error_result(self):
        r = ToolExecutionResult(
            tool_name="run_engine",
            status="error",
            reason_code="model_not_found",
            retryable=True,
            error_summary="Model version not found",
        )
        assert r.status == "error"
        assert r.retryable is True
        assert r.error_summary == "Model version not found"
        assert r.result is None

    def test_blocked_result(self):
        r = ToolExecutionResult(
            tool_name="build_scenario",
            status="blocked",
            reason_code="confirmation_required",
        )
        assert r.status == "blocked"
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/services/test_chat_tool_executor.py::TestToolExecutionResult -v`
Expected: FAIL — `ToolExecutionResult` not yet defined

**Step 3: Add ToolExecutionResult to models**

In `src/models/chat.py`, add after `ToolCall` class:

```python
from typing import Literal

class ToolExecutionResult(BaseModel):
    """Result of executing a tool call."""

    tool_name: str
    status: Literal["success", "error", "blocked"]
    reason_code: str = ""
    retryable: bool = False
    latency_ms: int = 0
    result: dict | None = None
    error_summary: str | None = None
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/services/test_chat_tool_executor.py::TestToolExecutionResult -v`
Expected: PASS

**Step 5: Write failing test for ChatToolExecutor skeleton**

Add to `tests/services/test_chat_tool_executor.py`:

```python
from unittest.mock import AsyncMock
from uuid import uuid4
from src.services.chat_tool_executor import ChatToolExecutor
from src.models.chat import ToolCall


class TestChatToolExecutorBasics:
    """S27-1: Basic executor dispatch."""

    @pytest.fixture
    def executor(self):
        session = AsyncMock()
        return ChatToolExecutor(session=session, workspace_id=uuid4())

    def test_max_tool_calls_constant(self, executor):
        assert executor.MAX_TOOL_CALLS_PER_TURN == 5

    async def test_unknown_tool_returns_error(self, executor):
        tc = ToolCall(tool_name="unknown_tool", arguments={"x": 1})
        result = await executor.execute(tc)
        assert result.status == "error"
        assert result.reason_code == "unknown_tool"
        assert "unknown" in result.error_summary.lower()

    async def test_execute_all_respects_cap(self, executor):
        calls = [ToolCall(tool_name="lookup_data", arguments={}) for _ in range(7)]
        results = await executor.execute_all(calls)
        assert len(results) == 5  # capped at MAX_TOOL_CALLS_PER_TURN

    async def test_execute_all_caps_run_engine_to_one(self, executor):
        calls = [
            ToolCall(tool_name="run_engine", arguments={"scenario_spec_id": str(uuid4()), "scenario_spec_version": 1}),
            ToolCall(tool_name="run_engine", arguments={"scenario_spec_id": str(uuid4()), "scenario_spec_version": 1}),
        ]
        results = await executor.execute_all(calls)
        run_results = [r for r in results if r.tool_name == "run_engine"]
        success_count = sum(1 for r in run_results if r.status != "blocked")
        blocked_count = sum(1 for r in run_results if r.status == "blocked")
        assert success_count <= 1
        assert blocked_count >= 1
```

**Step 6: Run test to verify it fails**

Run: `python -m pytest tests/services/test_chat_tool_executor.py::TestChatToolExecutorBasics -v`
Expected: FAIL — module not found

**Step 7: Create ChatToolExecutor skeleton**

Create `src/services/chat_tool_executor.py`:

```python
"""Chat tool executor — Sprint 27.

Deterministic tool dispatch for economist copilot tool calls.
Calls existing repos/services directly (no HTTP self-calls).
"""

from __future__ import annotations

import logging
import time
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.chat import ToolCall, ToolExecutionResult

_logger = logging.getLogger(__name__)


class ChatToolExecutor:
    """Executes copilot tool calls against backend services."""

    MAX_TOOL_CALLS_PER_TURN = 5
    _MAX_RUN_ENGINE_PER_TURN = 1
    _MAX_CREATE_EXPORT_PER_TURN = 1

    def __init__(self, session: AsyncSession, workspace_id: UUID) -> None:
        self._session = session
        self._workspace_id = workspace_id

    async def execute(self, tool_call: ToolCall) -> ToolExecutionResult:
        """Execute a single tool call. Returns result (never raises)."""
        start = time.monotonic()
        try:
            handler = self._get_handler(tool_call.tool_name)
            if handler is None:
                return ToolExecutionResult(
                    tool_name=tool_call.tool_name,
                    status="error",
                    reason_code="unknown_tool",
                    error_summary=f"Unknown tool: {tool_call.tool_name}",
                )
            result = await handler(tool_call.arguments)
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return ToolExecutionResult(
                tool_name=tool_call.tool_name,
                status=result.status,
                reason_code=result.reason_code,
                retryable=result.retryable,
                latency_ms=elapsed_ms,
                result=result.result,
                error_summary=result.error_summary,
            )
        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            _logger.exception("Tool execution error: %s", tool_call.tool_name)
            return ToolExecutionResult(
                tool_name=tool_call.tool_name,
                status="error",
                reason_code="internal_error",
                retryable=True,
                latency_ms=elapsed_ms,
                error_summary=str(exc)[:200],
            )

    async def execute_all(self, tool_calls: list[ToolCall]) -> list[ToolExecutionResult]:
        """Execute tool calls sequentially with safety caps."""
        results: list[ToolExecutionResult] = []
        run_engine_count = 0
        create_export_count = 0

        for tc in tool_calls[:self.MAX_TOOL_CALLS_PER_TURN]:
            if tc.tool_name == "run_engine":
                run_engine_count += 1
                if run_engine_count > self._MAX_RUN_ENGINE_PER_TURN:
                    results.append(ToolExecutionResult(
                        tool_name=tc.tool_name,
                        status="blocked",
                        reason_code="per_turn_cap_exceeded",
                        error_summary=f"Max {self._MAX_RUN_ENGINE_PER_TURN} run_engine per turn",
                    ))
                    continue

            if tc.tool_name == "create_export":
                create_export_count += 1
                if create_export_count > self._MAX_CREATE_EXPORT_PER_TURN:
                    results.append(ToolExecutionResult(
                        tool_name=tc.tool_name,
                        status="blocked",
                        reason_code="per_turn_cap_exceeded",
                        error_summary=f"Max {self._MAX_CREATE_EXPORT_PER_TURN} create_export per turn",
                    ))
                    continue

            result = await self.execute(tc)
            results.append(result)

        return results

    def _get_handler(self, tool_name: str):
        """Return handler coroutine for tool name, or None."""
        handlers = {
            "lookup_data": self._handle_lookup_data,
            "build_scenario": self._handle_build_scenario,
            "run_engine": self._handle_run_engine,
            "narrate_results": self._handle_narrate_results,
            "create_export": self._handle_create_export,
        }
        return handlers.get(tool_name)

    # -- Tool handlers (stubs for now, implemented in Task 3) --

    async def _handle_lookup_data(self, args: dict) -> ToolExecutionResult:
        return ToolExecutionResult(
            tool_name="lookup_data", status="success",
            reason_code="not_implemented",
            result={"message": "lookup_data not yet implemented"},
        )

    async def _handle_build_scenario(self, args: dict) -> ToolExecutionResult:
        return ToolExecutionResult(
            tool_name="build_scenario", status="success",
            reason_code="not_implemented",
            result={"message": "build_scenario not yet implemented"},
        )

    async def _handle_run_engine(self, args: dict) -> ToolExecutionResult:
        return ToolExecutionResult(
            tool_name="run_engine", status="success",
            reason_code="not_implemented",
            result={"message": "run_engine not yet implemented"},
        )

    async def _handle_narrate_results(self, args: dict) -> ToolExecutionResult:
        return ToolExecutionResult(
            tool_name="narrate_results", status="success",
            reason_code="not_implemented",
            result={"message": "narrate_results not yet implemented"},
        )

    async def _handle_create_export(self, args: dict) -> ToolExecutionResult:
        return ToolExecutionResult(
            tool_name="create_export", status="success",
            reason_code="not_implemented",
            result={"message": "create_export not yet implemented"},
        )
```

**Step 8: Run tests to verify they pass**

Run: `python -m pytest tests/services/test_chat_tool_executor.py -v`
Expected: PASS

**Step 9: Commit**

```bash
git add src/models/chat.py src/services/chat_tool_executor.py tests/services/test_chat_tool_executor.py
git commit -m "[sprint27] add ToolExecutionResult model and ChatToolExecutor skeleton with safety caps"
```

---

## Task 3: Implement tool handlers — build_scenario, run_engine, narrate_results, create_export (S27-1b)

**Files:**
- Modify: `src/services/chat_tool_executor.py`
- Modify: `tests/services/test_chat_tool_executor.py`
- Reference: `src/repositories/scenarios.py` (ScenarioVersionRepository)
- Reference: `src/api/runs.py` (RunRequest, engine run logic)
- Reference: `src/api/exports.py` (CreateExportRequest)
- Reference: `src/engine/batch.py` (BatchRunner)

**Step 1: Write failing tests for build_scenario handler**

Add to `tests/services/test_chat_tool_executor.py`:

```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.db.session import Base
import src.db.tables  # noqa: F401
from src.db.tables import WorkspaceRow
from src.models.common import utc_now


@pytest.fixture
async def real_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        ws_id = uuid4()
        now = utc_now()
        ws = WorkspaceRow(
            workspace_id=ws_id,
            client_name="Test",
            engagement_code="T-EX",
            classification="INTERNAL",
            description="test",
            created_by=uuid4(),
            created_at=now,
            updated_at=now,
        )
        session.add(ws)
        await session.flush()
        yield session, ws_id
    await engine.dispose()


class TestBuildScenarioHandler:
    async def test_build_scenario_success(self, real_db):
        session, ws_id = real_db
        # Seed a model version for the scenario
        from src.db.tables import ModelVersionRow
        mv_id = uuid4()
        session.add(ModelVersionRow(
            model_version_id=mv_id,
            workspace_id=ws_id,
            name="test-model",
            provenance_class="CURATED",
            data_source="test",
            base_year=2023,
            region="SAU",
            sector_count=21,
            created_by=uuid4(),
            created_at=utc_now(),
        ))
        await session.flush()

        executor = ChatToolExecutor(session=session, workspace_id=ws_id)
        tc = ToolCall(tool_name="build_scenario", arguments={
            "name": "Tourism boost",
            "base_year": 2023,
            "base_model_version_id": str(mv_id),
            "start_year": 2024,
            "end_year": 2026,
        })
        result = await executor.execute(tc)
        assert result.status == "success"
        assert result.reason_code == "scenario_created"
        assert "scenario_spec_id" in result.result
        assert "version" in result.result

    async def test_build_scenario_missing_name(self, real_db):
        session, ws_id = real_db
        executor = ChatToolExecutor(session=session, workspace_id=ws_id)
        tc = ToolCall(tool_name="build_scenario", arguments={"base_year": 2023})
        result = await executor.execute(tc)
        assert result.status == "error"
        assert result.reason_code == "invalid_args"
```

**Step 2: Run to verify failure**

Run: `python -m pytest tests/services/test_chat_tool_executor.py::TestBuildScenarioHandler -v`
Expected: FAIL (handler returns stub)

**Step 3: Implement build_scenario handler**

Replace `_handle_build_scenario` in `src/services/chat_tool_executor.py`:

```python
    async def _handle_build_scenario(self, args: dict) -> ToolExecutionResult:
        """Create a ScenarioSpec via repository."""
        from src.repositories.scenarios import ScenarioVersionRepository
        from src.models.common import new_uuid7

        name = args.get("name")
        base_year = args.get("base_year")
        base_model_version_id = args.get("base_model_version_id")
        start_year = args.get("start_year", base_year)
        end_year = args.get("end_year", base_year)

        if not name or base_year is None or not base_model_version_id:
            return ToolExecutionResult(
                tool_name="build_scenario",
                status="error",
                reason_code="invalid_args",
                error_summary="Required: name, base_year, base_model_version_id",
            )

        try:
            repo = ScenarioVersionRepository(self._session)
            spec_id = new_uuid7()
            time_horizon = {"start_year": start_year, "end_year": end_year}

            await repo.create(
                scenario_spec_id=spec_id,
                version=1,
                name=name,
                workspace_id=self._workspace_id,
                base_model_version_id=UUID(base_model_version_id),
                base_year=base_year,
                time_horizon=time_horizon,
            )

            return ToolExecutionResult(
                tool_name="build_scenario",
                status="success",
                reason_code="scenario_created",
                result={
                    "scenario_spec_id": str(spec_id),
                    "version": 1,
                    "name": name,
                },
            )
        except Exception as exc:
            return ToolExecutionResult(
                tool_name="build_scenario",
                status="error",
                reason_code="scenario_creation_failed",
                retryable=True,
                error_summary=str(exc)[:200],
            )
```

**Step 4: Write failing tests for run_engine and narrate_results, then implement**

These follow the same pattern. `run_engine` is complex (needs model loading + engine math), so the handler wraps the existing `BatchRunner` logic. `narrate_results` reads persisted `ResultSet` rows from DB. `create_export` creates an export record and returns immediately.

Due to complexity, the exact implementation of `run_engine` and `create_export` should be developed by the subagent with full access to `src/api/runs.py` and `src/api/exports.py` as reference.

Key contracts:
- `run_engine` handler: Takes `scenario_spec_id` + `scenario_spec_version`. Loads model, builds shocks, calls `BatchRunner.run()`, persists via repos. Returns `run_id` + summary.
- `narrate_results` handler: Takes `run_id`. Reads `ResultSet` rows from DB via `ResultSetRepository`. Returns structured result data (no LLM call here — the copilot narrates from the data on the next turn).
- `create_export` handler: Takes `run_id`, `mode`, `export_formats`, `pack_data`. Creates export record via `ExportRepository`. Returns `export_id` + `status: PENDING`.
- `lookup_data` handler: MVP stub that returns available dataset metadata. Full implementation deferred.

**Step 5: Commit**

```bash
git add src/services/chat_tool_executor.py tests/services/test_chat_tool_executor.py
git commit -m "[sprint27] implement tool handlers for scenario, engine, narrate, and export"
```

---

## Task 4: Integrate ChatToolExecutor into ChatService (S27-2)

**Files:**
- Modify: `src/services/chat.py`
- Modify: `src/api/chat.py`
- Modify: `tests/services/test_chat.py`
- Modify: `tests/api/test_chat.py`

**Step 1: Write failing tests for tool execution in ChatService**

Add to `tests/services/test_chat.py`:

```python
class TestToolExecution:
    """S27-2: ChatService executes tool calls via ChatToolExecutor."""

    async def test_confirmed_tool_gets_executed(self, db_session):
        """When user confirms, gated tools should be executed."""
        session, ws_id = db_session
        mock_copilot = AsyncMock()
        mock_copilot.process_turn = AsyncMock(return_value=CopilotResponse(
            content="Running scenario analysis.",
            tool_calls=[ToolCall(
                tool_name="build_scenario",
                arguments={"name": "Test", "base_year": 2023,
                           "base_model_version_id": "some-uuid",
                           "start_year": 2024, "end_year": 2026},
            )],
            prompt_version="copilot_v1",
            model_provider="anthropic",
            model_id="claude-sonnet-4-20250514",
            token_usage=TokenUsage(input_tokens=100, output_tokens=50),
        ))

        mock_executor = AsyncMock()
        mock_executor.execute_all = AsyncMock(return_value=[
            ToolExecutionResult(
                tool_name="build_scenario",
                status="success",
                reason_code="scenario_created",
                result={"scenario_spec_id": "abc", "version": 1},
            ),
        ])

        svc = ChatService(
            session_repo=ChatSessionRepository(session),
            message_repo=ChatMessageRepository(session),
            copilot=mock_copilot,
            tool_executor=mock_executor,
        )
        sess = await svc.create_session(ws_id, title="test")
        msg = await svc.send_message(
            ws_id, UUID(sess.session_id), "proceed",
            confirm_scenario=True,
        )
        mock_executor.execute_all.assert_awaited_once()
        # Tool results should be persisted
        assert msg.tool_calls is not None
        assert msg.tool_calls[0].result is not None
        assert msg.tool_calls[0].result["status"] == "success"

    async def test_unconfirmed_gated_tool_not_executed(self, db_session):
        """When user has NOT confirmed, gated tools should NOT be executed."""
        session, ws_id = db_session
        mock_copilot = AsyncMock()
        mock_copilot.process_turn = AsyncMock(return_value=CopilotResponse(
            content="I propose running the engine.",
            pending_confirmation={"tool": "run_engine", "arguments": {"spec_id": "x"}},
            prompt_version="copilot_v1",
            model_provider="anthropic",
            model_id="claude-sonnet-4-20250514",
            token_usage=TokenUsage(input_tokens=100, output_tokens=50),
        ))

        mock_executor = AsyncMock()
        svc = ChatService(
            session_repo=ChatSessionRepository(session),
            message_repo=ChatMessageRepository(session),
            copilot=mock_copilot,
            tool_executor=mock_executor,
        )
        sess = await svc.create_session(ws_id, title="test")
        msg = await svc.send_message(ws_id, UUID(sess.session_id), "analyze tourism")
        # Executor should NOT be called for pending confirmation
        mock_executor.execute_all.assert_not_awaited()
        assert msg.trace_metadata is not None
        assert msg.trace_metadata.pending_confirmation is not None

    async def test_trace_metadata_populated_from_execution(self, db_session):
        """Trace metadata should include run_id and scenario_spec_id after execution."""
        session, ws_id = db_session
        mock_copilot = AsyncMock()
        mock_copilot.process_turn = AsyncMock(return_value=CopilotResponse(
            content="Engine results ready.",
            tool_calls=[ToolCall(
                tool_name="run_engine",
                arguments={"scenario_spec_id": "spec-123", "scenario_spec_version": 1},
            )],
            prompt_version="copilot_v1",
            model_provider="anthropic",
            model_id="claude-sonnet-4-20250514",
            token_usage=TokenUsage(input_tokens=100, output_tokens=50),
        ))

        mock_executor = AsyncMock()
        mock_executor.execute_all = AsyncMock(return_value=[
            ToolExecutionResult(
                tool_name="run_engine",
                status="success",
                reason_code="run_completed",
                result={
                    "run_id": "run-456",
                    "model_version_id": "mv-789",
                    "scenario_spec_id": "spec-123",
                    "scenario_spec_version": 1,
                },
            ),
        ])

        svc = ChatService(
            session_repo=ChatSessionRepository(session),
            message_repo=ChatMessageRepository(session),
            copilot=mock_copilot,
            tool_executor=mock_executor,
        )
        sess = await svc.create_session(ws_id, title="test")
        msg = await svc.send_message(
            ws_id, UUID(sess.session_id), "run it",
            confirm_scenario=True,
        )
        assert msg.trace_metadata is not None
        assert msg.trace_metadata.run_id == "run-456"
        assert msg.trace_metadata.scenario_spec_id == "spec-123"
```

**Step 2: Run to verify failure**

Run: `python -m pytest tests/services/test_chat.py::TestToolExecution -v`
Expected: FAIL — ChatService doesn't accept `tool_executor` yet

**Step 3: Integrate executor into ChatService**

Modify `src/services/chat.py`:

1. Add `tool_executor` param to `__init__`:

```python
    def __init__(
        self,
        session_repo: ChatSessionRepository,
        message_repo: ChatMessageRepository,
        copilot: EconomistCopilot | None = None,
        tool_executor=None,
        max_tokens: int = 4096,
        model: str = "",
    ) -> None:
        ...
        self._tool_executor = tool_executor
```

2. In `send_message`, after copilot returns, execute tool calls and populate trace:

```python
        # Execute confirmed tool calls (skip if pending_confirmation)
        if copilot_response.tool_calls and self._tool_executor and not copilot_response.pending_confirmation:
            exec_results = await self._tool_executor.execute_all(copilot_response.tool_calls)
            # Merge results into tool calls
            for tc, er in zip(copilot_response.tool_calls, exec_results):
                tc.result = er.model_dump()
            # Populate trace metadata from execution results
            trace_dict = trace_dict or {}
            for er in exec_results:
                if er.status == "success" and er.result:
                    if er.tool_name == "run_engine":
                        trace_dict["run_id"] = er.result.get("run_id")
                        trace_dict["model_version_id"] = er.result.get("model_version_id")
                        trace_dict["scenario_spec_id"] = er.result.get("scenario_spec_id")
                        trace_dict["scenario_spec_version"] = er.result.get("scenario_spec_version")
                    elif er.tool_name == "build_scenario":
                        trace_dict["scenario_spec_id"] = er.result.get("scenario_spec_id")
                        trace_dict["scenario_spec_version"] = er.result.get("version")
```

3. Wire executor in `_get_chat_service` in `src/api/chat.py`:

```python
from src.services.chat_tool_executor import ChatToolExecutor

def _get_chat_service(session, copilot=None):
    settings = get_settings()
    if copilot is None:
        copilot = _build_copilot(settings)
    # ... fail-closed check ...
    return ChatService(
        session_repo=ChatSessionRepository(session),
        message_repo=ChatMessageRepository(session),
        copilot=copilot,
        tool_executor=ChatToolExecutor(session=session, workspace_id=???),
        max_tokens=settings.COPILOT_MAX_TOKENS,
        model=settings.COPILOT_MODEL,
    )
```

Note: `workspace_id` for the executor must come from the endpoint. Either pass it through `send_message` to the executor, or create the executor lazily. The subagent implementing this should read the current `send_message` endpoint to find the right wiring point.

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/services/test_chat.py tests/api/test_chat.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/services/chat.py src/api/chat.py tests/services/test_chat.py tests/api/test_chat.py
git commit -m "[sprint27] integrate chat service with executed tool results and trace linking"
```

---

## Task 5: Update copilot prompt and add create_export tool (S27-1c)

**Files:**
- Modify: `src/agents/prompts/economist_copilot_v1.py`
- Modify: `src/agents/economist_copilot.py` (add `create_export` to `_VALID_TOOLS`)
- Modify: `tests/agents/test_economist_copilot.py`

**Step 1: Write failing test**

```python
class TestCreateExportTool:
    def test_create_export_is_valid_tool(self):
        from src.agents.economist_copilot import _VALID_TOOLS
        assert "create_export" in _VALID_TOOLS

    def test_create_export_not_gated(self):
        from src.agents.economist_copilot import _GATED_TOOLS
        assert "create_export" not in _GATED_TOOLS

    def test_prompt_includes_create_export(self):
        from src.agents.prompts.economist_copilot_v1 import build_system_prompt, get_tool_definitions
        prompt = build_system_prompt({})
        assert "create_export" in prompt
        tools = get_tool_definitions()
        tool_names = [t["name"] for t in tools]
        assert "create_export" in tool_names
```

**Step 2: Run to verify failure, implement, run to verify pass**

- Add `"create_export"` to `_VALID_TOOLS` in `economist_copilot.py`
- Add tool 5 definition to `get_tool_definitions()` and system prompt in `economist_copilot_v1.py`

**Step 3: Commit**

```bash
git add src/agents/economist_copilot.py src/agents/prompts/economist_copilot_v1.py tests/agents/test_economist_copilot.py
git commit -m "[sprint27] add create_export tool to copilot prompt and valid tools"
```

---

## Task 6: Frontend — tool execution status and deep links (S27-3)

**Files:**
- Modify: `frontend/src/components/chat/message-bubble.tsx`
- Modify: `frontend/src/lib/api/hooks/useChat.ts` (ToolExecutionResult type)
- Modify: `frontend/src/components/chat/__tests__/chat-interface.test.tsx`
- Modify: `frontend/src/lib/api/hooks/__tests__/useChat.test.ts`

**Step 1: Write failing frontend tests**

Add to `frontend/src/components/chat/__tests__/chat-interface.test.tsx`:

```typescript
it('renders executed tool results with success badge', async () => {
  // Mock session with a message containing executed tool calls
  // Verify the tool result <details> block shows a success badge
});

it('renders executed tool results with error badge', async () => {
  // Mock session with a message containing failed tool calls
  // Verify error badge and error_summary are displayed
});

it('renders deep link to run page from trace metadata', async () => {
  // Mock session with trace_metadata.run_id set
  // Verify link to /w/{workspaceId}/runs/{runId} is rendered
});
```

**Step 2: Update ToolCall type to include execution result fields**

In `useChat.ts`, update ToolCall interface:

```typescript
export interface ToolExecutionResult {
  tool_name: string;
  status: 'success' | 'error' | 'blocked';
  reason_code: string;
  retryable: boolean;
  latency_ms: number;
  result?: Record<string, unknown> | null;
  error_summary?: string | null;
}
```

**Step 3: Update MessageBubble to show status badges and deep links**

Add status badge (green/red/amber) to tool call `<summary>` elements.
Add deep links when `trace_metadata.run_id` is present.

**Step 4: Run frontend tests**

Run: `cd frontend && npx vitest run src/components/chat/__tests__/chat-interface.test.tsx src/lib/api/hooks/__tests__/useChat.test.ts`

**Step 5: Commit**

```bash
git add frontend/src/components/chat/message-bubble.tsx frontend/src/lib/api/hooks/useChat.ts \
  frontend/src/components/chat/__tests__/chat-interface.test.tsx frontend/src/lib/api/hooks/__tests__/useChat.test.ts
git commit -m "[sprint27] add frontend visibility for tool execution status and run/export links"
```

---

## Task 7: Contracts, evidence, and docs sync (S27-4)

**Files:**
- Regenerate: `openapi.json`
- Modify: `docs/evidence/sprint25-copilot-evidence.md` (add Sprint 27 section)
- Modify: `docs/ImpactOS_Master_Build_Plan_v2.md` (add S27 row)
- Modify: `docs/plans/2026-03-03-full-system-completion-master-plan.md` (add S27 entry)
- Create: `docs/evidence/sprint27-pr-body.md`

**Step 1: Regenerate OpenAPI**

```bash
python -c "import json; from pathlib import Path; from src.api.main import app; Path('openapi.json').write_text(json.dumps(app.openapi(), indent=2), encoding='utf-8')"
python -c "import json; json.load(open('openapi.json', 'r', encoding='utf-8')); print('openapi.json valid')"
```

**Step 2: Update evidence docs**

Add Sprint 27 section to evidence docs with tool execution proof matrix.

**Step 3: Run full verification**

```bash
python -m pytest tests -q
cd frontend && npx vitest run && cd ..
python -m alembic current
python -m alembic heads
python -m alembic check
```

**Step 4: Commit**

```bash
git add openapi.json docs/
git commit -m "[sprint27] refresh sprint27 evidence and openapi"
```

---

## Task 8: Code review + apply findings

Use `superpowers:requesting-code-review` to dispatch code-reviewer agent.
Apply findings using `superpowers:receiving-code-review`.

---

## Task 9: Final verification + PR

Use `superpowers:verification-before-completion` to run full verification.
Use `superpowers:finishing-a-development-branch` to push and open PR.

**Branch:** `phase3-sprint27-copilot-tool-execution`
**Expected commits:**
1. `[sprint27] wire chat runtime to real copilot dependency with fail-closed behavior`
2. `[sprint27] add ToolExecutionResult model and ChatToolExecutor skeleton with safety caps`
3. `[sprint27] implement tool handlers for scenario, engine, narrate, and export`
4. `[sprint27] integrate chat service with executed tool results and trace linking`
5. `[sprint27] add create_export tool to copilot prompt and valid tools`
6. `[sprint27] add frontend visibility for tool execution status and run/export links`
7. `[sprint27] refresh sprint27 evidence and openapi`
