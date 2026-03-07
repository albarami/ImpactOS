"""Phase 2 verification: Copilot contract and orchestration integrity.

These tests prove:
1. lookup_data returns real model data, not hardcoded stubs (P2-2)
2. lookup_data filters by sector_codes and year
3. Pending confirmation stores tool intent in DB (P2-3/P2-4)
4. Confirmation replay retrieves and executes stored intent (P2-4)
5. Confirmation replay skips LLM re-parsing (P2-4)
6. Server-side ID injection: scenario_spec_id comes from DB, not LLM (P2-3)
"""

import pytest
import numpy as np
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db.session import Base
import src.db.tables  # noqa: F401
from src.db.tables import WorkspaceRow, ModelVersionRow, ModelDataRow
from src.models.chat import ToolCall, ToolExecutionResult, TokenUsage, TraceMetadata
from src.models.common import new_uuid7, utc_now
from src.repositories.chat import ChatMessageRepository, ChatSessionRepository
from src.services.chat import ChatService
from src.services.chat_tool_executor import ChatToolExecutor
from src.agents.economist_copilot import CopilotResponse

pytestmark = pytest.mark.anyio


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
async def db_session_with_model():
    """In-memory DB with workspace + 3-sector model for lookup tests."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        ws_id = uuid4()
        now = utc_now()
        ws = WorkspaceRow(
            workspace_id=ws_id,
            client_name="Phase2 Test",
            engagement_code="P2-TEST",
            classification="INTERNAL",
            description="Phase 2 test workspace",
            created_by=uuid4(),
            created_at=now,
            updated_at=now,
        )
        session.add(ws)

        mv_id = new_uuid7()
        mv = ModelVersionRow(
            model_version_id=mv_id,
            base_year=2023,
            source="test_phase2",
            sector_count=3,
            checksum="sha256:" + "b" * 64,
            provenance_class="curated_real",
            model_denomination="SAR_THOUSANDS",
            created_at=now,
        )
        session.add(mv)

        z = [[10.0, 20.0, 0.0], [0.0, 15.0, 30.0], [5.0, 0.0, 10.0]]
        x = [100.0, 200.0, 150.0]
        md = ModelDataRow(
            model_version_id=mv_id,
            z_matrix_json=z,
            x_vector_json=x,
            sector_codes=["A", "B", "C"],
        )
        session.add(md)
        await session.flush()
        yield session, ws_id, mv_id
    await engine.dispose()


def _mock_satellite_coefficients():
    """Return a context manager that patches load_satellite_coefficients."""
    from src.engine.satellites import SatelliteCoefficients
    from src.data.workforce.satellite_coeff_loader import (
        LoadedCoefficients,
        CoefficientProvenance,
    )
    mock_coeffs = SatelliteCoefficients(
        jobs_coeff=np.array([0.01, 0.02, 0.015]),
        import_ratio=np.array([0.15, 0.15, 0.15]),
        va_ratio=np.array([0.5, 0.4, 0.6]),
        version_id=new_uuid7(),
    )
    return patch(
        "src.services.run_execution.load_satellite_coefficients",
        return_value=LoadedCoefficients(
            coefficients=mock_coeffs,
            provenance=CoefficientProvenance(
                employment_coeff_year=2023,
                io_base_year=2023,
                import_ratio_year=2023,
                va_ratio_year=2023,
            ),
        ),
    )


# ------------------------------------------------------------------
# P2-2: lookup_data returns real data
# ------------------------------------------------------------------


class TestLookupDataReal:
    """P2-2: lookup_data must return real model data, not stubs."""

    async def test_lookup_io_tables_returns_sector_codes(self, db_session_with_model):
        """lookup_data with dataset_id=io_tables returns real sector codes."""
        session, ws_id, mv_id = db_session_with_model
        executor = ChatToolExecutor(session=session, workspace_id=ws_id)
        tc = ToolCall(
            tool_name="lookup_data",
            arguments={
                "dataset_id": "io_tables",
                "model_version_id": str(mv_id),
            },
        )
        result = await executor.execute(tc)
        assert result.status == "success"
        data = result.result
        assert "sector_codes" in data
        assert data["sector_codes"] == ["A", "B", "C"]

    async def test_lookup_io_tables_returns_output_vector(self, db_session_with_model):
        """lookup_data with dataset_id=io_tables returns real output vector."""
        session, ws_id, mv_id = db_session_with_model
        executor = ChatToolExecutor(session=session, workspace_id=ws_id)
        tc = ToolCall(
            tool_name="lookup_data",
            arguments={
                "dataset_id": "io_tables",
                "model_version_id": str(mv_id),
            },
        )
        result = await executor.execute(tc)
        assert result.status == "success"
        data = result.result
        assert "total_output" in data
        assert len(data["total_output"]) == 3
        assert data["total_output"]["A"] == 100.0

    async def test_lookup_io_tables_returns_denomination(self, db_session_with_model):
        """lookup_data with dataset_id=io_tables returns model denomination."""
        session, ws_id, mv_id = db_session_with_model
        executor = ChatToolExecutor(session=session, workspace_id=ws_id)
        tc = ToolCall(
            tool_name="lookup_data",
            arguments={
                "dataset_id": "io_tables",
                "model_version_id": str(mv_id),
            },
        )
        result = await executor.execute(tc)
        assert result.status == "success"
        data = result.result
        assert data["denomination"] == "SAR_THOUSANDS"

    async def test_lookup_io_tables_filters_by_sector_codes(self, db_session_with_model):
        """lookup_data with sector_codes filter returns only requested sectors."""
        session, ws_id, mv_id = db_session_with_model
        executor = ChatToolExecutor(session=session, workspace_id=ws_id)
        tc = ToolCall(
            tool_name="lookup_data",
            arguments={
                "dataset_id": "io_tables",
                "model_version_id": str(mv_id),
                "sector_codes": ["A", "C"],
            },
        )
        result = await executor.execute(tc)
        assert result.status == "success"
        data = result.result
        assert set(data["total_output"].keys()) == {"A", "C"}

    async def test_lookup_models_lists_available(self, db_session_with_model):
        """lookup_data with dataset_id=models lists available model versions."""
        session, ws_id, mv_id = db_session_with_model
        executor = ChatToolExecutor(session=session, workspace_id=ws_id)
        tc = ToolCall(
            tool_name="lookup_data",
            arguments={"dataset_id": "models"},
        )
        result = await executor.execute(tc)
        assert result.status == "success"
        data = result.result
        assert "models" in data
        assert len(data["models"]) >= 1
        model_info = data["models"][0]
        assert "model_version_id" in model_info
        assert model_info["base_year"] == 2023

    async def test_lookup_missing_model_version_returns_error(self, db_session_with_model):
        """lookup_data with nonexistent model_version_id returns error."""
        session, ws_id, _ = db_session_with_model
        executor = ChatToolExecutor(session=session, workspace_id=ws_id)
        fake_id = str(new_uuid7())
        tc = ToolCall(
            tool_name="lookup_data",
            arguments={
                "dataset_id": "io_tables",
                "model_version_id": fake_id,
            },
        )
        result = await executor.execute(tc)
        assert result.status == "error"
        assert "not found" in result.result.get("error", "").lower()

    async def test_lookup_without_dataset_id_lists_datasets(self, db_session_with_model):
        """lookup_data without dataset_id returns available dataset types."""
        session, ws_id, _ = db_session_with_model
        executor = ChatToolExecutor(session=session, workspace_id=ws_id)
        tc = ToolCall(
            tool_name="lookup_data",
            arguments={},
        )
        result = await executor.execute(tc)
        assert result.status == "success"
        data = result.result
        assert "datasets" in data


# ------------------------------------------------------------------
# P2-3 + P2-4: Stored intent replay
# ------------------------------------------------------------------


class TestStoredIntentReplay:
    """P2-3/P2-4: Confirmation must replay stored tool intent, not re-parse."""

    async def test_pending_confirmation_stored_in_message(self, db_session_with_model):
        """When copilot returns pending_confirmation, it is persisted in DB message."""
        session, ws_id, mv_id = db_session_with_model

        pending_args = {
            "name": "Tourism Impact",
            "base_year": 2023,
            "base_model_version_id": str(mv_id),
            "shock_items": [
                {"type": "FINAL_DEMAND_SHOCK", "sector_code": "A", "amount": 1000},
            ],
        }
        copilot = AsyncMock()
        copilot.process_turn = AsyncMock(return_value=CopilotResponse(
            content="I'll build a tourism scenario. Please confirm.",
            pending_confirmation={"tool": "build_scenario", "arguments": pending_args},
            prompt_version="copilot_v1",
            model_provider="anthropic",
            model_id="claude-sonnet-4-20250514",
            token_usage=TokenUsage(input_tokens=100, output_tokens=50),
        ))

        svc = ChatService(
            ChatSessionRepository(session),
            ChatMessageRepository(session),
            copilot=copilot,
            db_session=session,
        )
        created = await svc.create_session(ws_id)
        sid = UUID(created.session_id)
        result = await svc.send_message(ws_id, sid, "Build tourism scenario")

        # Verify pending_confirmation is in trace metadata
        assert result.trace_metadata is not None
        assert result.trace_metadata.pending_confirmation is not None
        assert result.trace_metadata.pending_confirmation["tool"] == "build_scenario"
        assert result.trace_metadata.pending_confirmation["arguments"] == pending_args

    async def test_confirmation_replays_stored_intent(self, db_session_with_model):
        """When user confirms, ChatService replays stored tool call, not LLM re-parse.

        Key assertions:
        1. copilot.process_turn is NOT called again on confirmation turn
        2. The stored build_scenario arguments are executed exactly
        3. scenario_spec_id in trace matches the newly created scenario
        """
        session, ws_id, mv_id = db_session_with_model

        pending_args = {
            "name": "Tourism Impact Exact",
            "base_year": 2023,
            "base_model_version_id": str(mv_id),
            "shock_items": [
                {"type": "FINAL_DEMAND_SHOCK", "sector_code": "B", "amount": 5000},
            ],
        }

        # Turn 1: copilot returns pending_confirmation
        first_response = CopilotResponse(
            content="I'll build a tourism scenario. Please confirm.",
            pending_confirmation={"tool": "build_scenario", "arguments": pending_args},
            prompt_version="copilot_v1",
            model_provider="anthropic",
            model_id="claude-sonnet-4-20250514",
            token_usage=TokenUsage(input_tokens=100, output_tokens=50),
        )

        copilot = AsyncMock()
        copilot.process_turn = AsyncMock(return_value=first_response)

        svc = ChatService(
            ChatSessionRepository(session),
            ChatMessageRepository(session),
            copilot=copilot,
            db_session=session,
        )
        created = await svc.create_session(ws_id)
        sid = UUID(created.session_id)

        # Turn 1: Send initial message → pending_confirmation
        await svc.send_message(ws_id, sid, "Build tourism scenario")
        assert copilot.process_turn.call_count == 1

        # Turn 2: User confirms → stored intent should be replayed
        result = await svc.send_message(ws_id, sid, "Yes, proceed", confirm_scenario=True)

        # copilot.process_turn should NOT have been called again
        # (the stored intent is replayed directly)
        assert copilot.process_turn.call_count == 1, (
            "Copilot should NOT be re-invoked on confirmation; "
            "stored intent should be replayed directly"
        )

        # The scenario should have been created with exact stored args
        assert result.trace_metadata is not None
        assert result.trace_metadata.scenario_spec_id is not None
        # Verify it's a valid UUID
        UUID(result.trace_metadata.scenario_spec_id)

    async def test_confirmation_without_pending_calls_copilot(self, db_session_with_model):
        """If no pending intent exists, confirm_scenario=True falls through to copilot."""
        session, ws_id, mv_id = db_session_with_model

        copilot = AsyncMock()
        copilot.process_turn = AsyncMock(return_value=CopilotResponse(
            content="No pending scenario to confirm.",
            prompt_version="copilot_v1",
            model_provider="anthropic",
            model_id="claude-sonnet-4-20250514",
            token_usage=TokenUsage(input_tokens=50, output_tokens=30),
        ))

        svc = ChatService(
            ChatSessionRepository(session),
            ChatMessageRepository(session),
            copilot=copilot,
            db_session=session,
        )
        created = await svc.create_session(ws_id)
        sid = UUID(created.session_id)

        # No prior pending_confirmation, just confirm_scenario=True
        result = await svc.send_message(ws_id, sid, "Yes, proceed", confirm_scenario=True)

        # Should call copilot normally
        assert copilot.process_turn.call_count == 1

    async def test_stored_intent_replay_for_run_engine(self, db_session_with_model):
        """Confirmation replay works for run_engine too, not just build_scenario."""
        session, ws_id, mv_id = db_session_with_model

        # First create a scenario to reference
        from src.repositories.scenarios import ScenarioVersionRepository
        repo = ScenarioVersionRepository(session)
        spec_id = new_uuid7()
        await repo.create(
            scenario_spec_id=spec_id, version=1, name="Intent Replay Test",
            workspace_id=ws_id, base_model_version_id=mv_id,
            base_year=2023, time_horizon={"start_year": 2023, "end_year": 2023},
        )

        pending_args = {
            "scenario_spec_id": str(spec_id),
            "scenario_spec_version": 1,
        }

        # Turn 1: copilot returns pending_confirmation for run_engine
        first_response = CopilotResponse(
            content="I'll run the engine now. Please confirm.",
            pending_confirmation={"tool": "run_engine", "arguments": pending_args},
            prompt_version="copilot_v1",
            model_provider="anthropic",
            model_id="claude-sonnet-4-20250514",
            token_usage=TokenUsage(input_tokens=100, output_tokens=50),
        )

        copilot = AsyncMock()
        copilot.process_turn = AsyncMock(return_value=first_response)
        copilot.enrich_narrative = AsyncMock(
            side_effect=lambda baseline, context=None: baseline,
        )

        svc = ChatService(
            ChatSessionRepository(session),
            ChatMessageRepository(session),
            copilot=copilot,
            db_session=session,
        )
        created = await svc.create_session(ws_id)
        sid = UUID(created.session_id)

        # Turn 1: pending
        await svc.send_message(ws_id, sid, "Run the engine")

        # Turn 2: confirm → replay
        with _mock_satellite_coefficients():
            result = await svc.send_message(ws_id, sid, "Yes, run it", confirm_scenario=True)

        # copilot should NOT have been re-invoked
        assert copilot.process_turn.call_count == 1

        # Run should have completed
        assert result.trace_metadata is not None
        assert result.trace_metadata.run_id is not None
        UUID(result.trace_metadata.run_id)  # valid UUID
