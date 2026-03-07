"""P3-1: Depth engine must be reachable from the copilot chat flow.

Tests prove:
1. run_depth_suite is a valid copilot tool
2. run_depth_suite requires confirmation (gated)
3. Prompt includes run_depth_suite
4. Tool definitions include run_depth_suite with required params
5. ChatToolExecutor has a handler for run_depth_suite
6. Handler creates DepthPlan and runs orchestrator
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4, UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db.session import Base
import src.db.tables  # noqa: F401
from src.db.tables import WorkspaceRow
from src.models.chat import ToolCall
from src.models.common import new_uuid7, utc_now
from src.services.chat_tool_executor import ChatToolExecutor

pytestmark = pytest.mark.anyio


# ------------------------------------------------------------------
# Prompt + tool definition tests (no DB needed)
# ------------------------------------------------------------------


class TestDepthToolInPrompt:
    """P3-1: run_depth_suite must be in the copilot tool set."""

    def test_run_depth_suite_is_valid_tool(self):
        from src.agents.economist_copilot import _VALID_TOOLS
        assert "run_depth_suite" in _VALID_TOOLS

    def test_run_depth_suite_is_gated(self):
        from src.agents.economist_copilot import _GATED_TOOLS
        assert "run_depth_suite" in _GATED_TOOLS

    def test_prompt_includes_run_depth_suite(self):
        from src.agents.prompts.economist_copilot_v1 import build_system_prompt
        prompt = build_system_prompt()
        assert "run_depth_suite" in prompt

    def test_tool_definitions_include_run_depth_suite(self):
        from src.agents.prompts.economist_copilot_v1 import get_tool_definitions
        tools = get_tool_definitions()
        names = {t["name"] for t in tools}
        assert "run_depth_suite" in names

    def test_tool_count_is_six(self):
        from src.agents.prompts.economist_copilot_v1 import get_tool_definitions
        tools = get_tool_definitions()
        assert len(tools) == 6

    def test_run_depth_suite_definition_has_required_params(self):
        from src.agents.prompts.economist_copilot_v1 import get_tool_definitions
        tools = get_tool_definitions()
        depth_tool = next(t for t in tools if t["name"] == "run_depth_suite")
        params = depth_tool["parameters"]
        assert "key_questions" in params
        assert params["key_questions"]["required"] is True

    def test_run_depth_suite_requires_confirmation(self):
        from src.agents.prompts.economist_copilot_v1 import get_tool_definitions
        tools = get_tool_definitions()
        depth_tool = next(t for t in tools if t["name"] == "run_depth_suite")
        assert depth_tool["requires_confirmation"] is True


# ------------------------------------------------------------------
# Handler test (requires DB)
# ------------------------------------------------------------------


@pytest.fixture
async def db_session_for_depth():
    """In-memory DB with workspace for depth handler tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        ws_id = uuid4()
        now = utc_now()
        ws = WorkspaceRow(
            workspace_id=ws_id,
            client_name="Depth Test",
            engagement_code="P3-1",
            classification="INTERNAL",
            description="Depth handler test workspace",
            created_by=uuid4(),
            created_at=now,
            updated_at=now,
        )
        session.add(ws)
        await session.flush()
        yield session, ws_id
    await engine.dispose()


class TestDepthSuiteHandler:
    """P3-1: ChatToolExecutor must have a working run_depth_suite handler."""

    async def test_handler_exists(self, db_session_for_depth):
        """ChatToolExecutor must have a handler for run_depth_suite."""
        session, ws_id = db_session_for_depth
        executor = ChatToolExecutor(session=session, workspace_id=ws_id)
        handler = executor._get_handler("run_depth_suite")
        assert handler is not None, "No handler for run_depth_suite in ChatToolExecutor"

    async def test_handler_creates_plan_and_runs(self, db_session_for_depth):
        """run_depth_suite handler creates a DepthPlan row and runs orchestrator."""
        session, ws_id = db_session_for_depth
        executor = ChatToolExecutor(session=session, workspace_id=ws_id)

        # Mock the orchestrator to avoid LLM calls
        with patch(
            "src.services.chat_tool_executor.run_depth_plan",
            new_callable=AsyncMock,
            return_value="COMPLETED",
        ) as mock_run:
            tc = ToolCall(
                tool_name="run_depth_suite",
                arguments={
                    "key_questions": ["What is the impact of tourism on GDP?"],
                    "target_sectors": ["I", "G"],
                },
            )
            result = await executor.execute(tc)

        assert result.status == "success", f"Expected success, got {result.status}: {result.result}"
        data = result.result
        assert "plan_id" in data
        assert data["status"] == "COMPLETED"
        # Verify run_depth_plan was called
        assert mock_run.called

    async def test_handler_passes_context(self, db_session_for_depth):
        """Handler passes key_questions and target_sectors in context to run_depth_plan."""
        session, ws_id = db_session_for_depth
        executor = ChatToolExecutor(session=session, workspace_id=ws_id)

        with patch(
            "src.services.chat_tool_executor.run_depth_plan",
            new_callable=AsyncMock,
            return_value="COMPLETED",
        ) as mock_run:
            tc = ToolCall(
                tool_name="run_depth_suite",
                arguments={
                    "key_questions": ["Tourism GDP impact?"],
                    "target_sectors": ["I"],
                    "base_year": 2023,
                },
            )
            await executor.execute(tc)

        # Verify context passed to run_depth_plan
        call_kwargs = mock_run.call_args.kwargs
        ctx = call_kwargs["context"]
        assert ctx["key_questions"] == ["Tourism GDP impact?"]
        assert ctx["target_sectors"] == ["I"]
        assert ctx["base_year"] == 2023

    async def test_handler_missing_key_questions_returns_error(self, db_session_for_depth):
        """Handler returns error when key_questions is missing."""
        session, ws_id = db_session_for_depth
        executor = ChatToolExecutor(session=session, workspace_id=ws_id)
        tc = ToolCall(
            tool_name="run_depth_suite",
            arguments={},
        )
        result = await executor.execute(tc)
        assert result.status == "error"
        assert "key_questions" in result.result.get("error", "").lower()
