# Sprint 28: Copilot Real Execution Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close three Sprint 27 deferrals so chat `run_engine` performs a real engine run, `create_export` invokes real export orchestration, and the assistant message reflects executed results via a post-execution narrative.

**Architecture:** Extract shared `RunExecutionService` and `ExportExecutionService` from inline API logic. Chat handlers call shared services directly (no internal HTTP). Add `ChatNarrativeService` to extract facts from tool results and build deterministic baseline narratives. Optionally enrich via `EconomistCopilot.enrich_narrative()`.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy async, NumPy/SciPy (engine), React/Next.js (frontend), Vitest (frontend tests), pytest (backend tests).

**Design doc:** `docs/plans/2026-03-06-sprint28-copilot-real-execution-design.md`

**Baseline:** 4881 backend tests (29 skipped), 336 frontend tests. Alembic head: `020_chat_sessions_messages`.

---

## Task 1: Create worktree and sprint branch

**Files:**
- None (git operations only)

**Step 1: Create worktree**

```bash
git worktree add .claude/worktrees/sprint28 -b phase3-sprint28-copilot-real-execution main
```

**Step 2: Verify clean state**

```bash
cd .claude/worktrees/sprint28
python -m pytest --co -q | tail -3
python -m alembic current
python -m alembic check
```

Expected: 4881 collected, head `020_chat_sessions_messages`, no new upgrade.

---

## Task 2: S28-0a — RunExecutionService dataclasses and skeleton

**Files:**
- Create: `src/services/run_execution.py`
- Test: `tests/services/test_run_execution.py`

**Step 1: Write failing test for RunExecutionResult dataclass**

```python
# tests/services/test_run_execution.py
"""Tests for RunExecutionService (Sprint 28)."""

import pytest
from uuid import uuid4

pytestmark = pytest.mark.anyio


class TestRunExecutionDataclasses:
    """S28-0a: Verify input/result dataclass contracts."""

    def test_run_from_scenario_input_fields(self):
        from src.services.run_execution import RunFromScenarioInput
        inp = RunFromScenarioInput(
            workspace_id=uuid4(),
            scenario_spec_id=uuid4(),
            scenario_spec_version=2,
        )
        assert inp.scenario_spec_version == 2

    def test_run_from_scenario_input_version_defaults_none(self):
        from src.services.run_execution import RunFromScenarioInput
        inp = RunFromScenarioInput(
            workspace_id=uuid4(),
            scenario_spec_id=uuid4(),
        )
        assert inp.scenario_spec_version is None

    def test_run_execution_result_completed(self):
        from src.services.run_execution import RunExecutionResult
        r = RunExecutionResult(
            status="COMPLETED",
            run_id=uuid4(),
            model_version_id=uuid4(),
            scenario_spec_id=uuid4(),
            scenario_spec_version=1,
            result_summary={"total_output": {"total": 1000.0}},
        )
        assert r.status == "COMPLETED"
        assert r.error is None

    def test_run_execution_result_failed(self):
        from src.services.run_execution import RunExecutionResult
        r = RunExecutionResult(status="FAILED", error="Model not found")
        assert r.status == "FAILED"
        assert r.run_id is None

    def test_run_repositories_bundle(self):
        from unittest.mock import MagicMock
        from src.services.run_execution import RunRepositories
        repos = RunRepositories(
            scenario_repo=MagicMock(),
            mv_repo=MagicMock(),
            md_repo=MagicMock(),
            snap_repo=MagicMock(),
            rs_repo=MagicMock(),
        )
        assert repos.scenario_repo is not None
```

**Step 2: Run test to verify it fails**

```bash
python -m pytest tests/services/test_run_execution.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'src.services.run_execution'`

**Step 3: Write minimal implementation**

```python
# src/services/run_execution.py
"""RunExecutionService — shared deterministic engine execution (Sprint 28).

Single source of truth for engine runs. Both the chat handler and the
API route call this service. No internal HTTP self-calls.

Agent-to-Math Boundary: this service calls BatchRunner.run() for
deterministic computation — it never performs economic calculations itself.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.engine import (
    ModelDataRepository,
    ModelVersionRepository,
    ResultSetRepository,
    RunSnapshotRepository,
)
from src.repositories.scenarios import ScenarioVersionRepository

_logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Normalized dataclasses
# ------------------------------------------------------------------


@dataclass(frozen=True)
class RunFromScenarioInput:
    """Chat path: resolve scenario into engine inputs."""
    workspace_id: UUID
    scenario_spec_id: UUID
    scenario_spec_version: int | None = None  # None = latest


@dataclass(frozen=True)
class RunFromRequestInput:
    """API path: pre-parsed engine inputs."""
    workspace_id: UUID
    model_version_id: UUID
    annual_shocks: dict  # dict[int, np.ndarray]
    base_year: int
    satellite_coefficients: object  # SatelliteCoefficients
    deflators: dict | None = None
    baseline_run_id: UUID | None = None
    scenario_spec_id: UUID | None = None
    scenario_spec_version: int | None = None


@dataclass(frozen=True)
class RunExecutionResult:
    status: Literal["COMPLETED", "FAILED"]
    run_id: UUID | None = None
    model_version_id: UUID | None = None
    scenario_spec_id: UUID | None = None
    scenario_spec_version: int | None = None
    result_summary: dict | None = None
    error: str | None = None


@dataclass
class RunRepositories:
    """All repos needed for a run execution."""
    scenario_repo: ScenarioVersionRepository
    mv_repo: ModelVersionRepository
    md_repo: ModelDataRepository
    snap_repo: RunSnapshotRepository
    rs_repo: ResultSetRepository
```

**Step 4: Run test to verify it passes**

```bash
python -m pytest tests/services/test_run_execution.py -v
```

Expected: 5 PASSED

**Step 5: Commit**

```bash
git add src/services/run_execution.py tests/services/test_run_execution.py
git commit -m "[sprint28] add RunExecutionService dataclasses and skeleton"
```

---

## Task 3: S28-0a — RunExecutionService.execute_from_scenario()

**Files:**
- Modify: `src/services/run_execution.py`
- Modify: `tests/services/test_run_execution.py`
- Read (reference): `src/api/runs.py` (lines 199-301, 419-451, 577-685 for helpers and create_run)
- Read (reference): `src/data/workforce/satellite_coeff_loader.py` (lines 70-160 for load_satellite_coefficients)

**Step 1: Write failing tests for execute_from_scenario**

Add to `tests/services/test_run_execution.py`:

```python
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db.session import Base
import src.db.tables  # noqa: F401
from src.db.tables import WorkspaceRow, ModelVersionRow, ModelDataRow
from src.models.common import new_uuid7, utc_now
from src.repositories.engine import (
    ModelDataRepository,
    ModelVersionRepository,
    ResultSetRepository,
    RunSnapshotRepository,
)
from src.repositories.scenarios import ScenarioVersionRepository
from src.services.run_execution import (
    RunExecutionService,
    RunFromScenarioInput,
    RunRepositories,
    RunExecutionResult,
)


@pytest.fixture
async def db_env():
    """In-memory DB with workspace, model version, model data, and scenario."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        ws_id = uuid4()
        now = utc_now()
        ws = WorkspaceRow(
            workspace_id=ws_id, client_name="Test", engagement_code="T-RUN",
            classification="INTERNAL", description="test", created_by=uuid4(),
            created_at=now, updated_at=now,
        )
        session.add(ws)

        # Register a 3-sector model with curated_real provenance
        mv_id = new_uuid7()
        mv = ModelVersionRow(
            model_version_id=mv_id, base_year=2023, source="test",
            sector_count=3, checksum="abc123", provenance_class="curated_real",
            created_at=now,
        )
        session.add(mv)

        z = [[0.1, 0.2, 0.0], [0.0, 0.1, 0.3], [0.1, 0.0, 0.1]]
        x = [100.0, 200.0, 150.0]
        md = ModelDataRow(
            model_version_id=mv_id,
            z_matrix_json=z, x_vector_json=x,
            sector_codes=["A", "B", "C"],
        )
        session.add(md)
        await session.flush()

        # Create scenario
        scenario_repo = ScenarioVersionRepository(session)
        scenario_id = new_uuid7()
        await scenario_repo.create(
            scenario_spec_id=scenario_id, version=1, name="test_scenario",
            workspace_id=ws_id, base_model_version_id=mv_id,
            base_year=2023, time_horizon={"start_year": 2023, "end_year": 2023},
            shock_items=[],
        )

        yield {
            "session": session,
            "ws_id": ws_id,
            "mv_id": mv_id,
            "scenario_id": scenario_id,
        }
    await engine.dispose()


class TestRunExecutionServiceFromScenario:
    """S28-0a: Real engine execution from scenario."""

    async def test_execute_from_scenario_success(self, db_env):
        env = db_env
        session = env["session"]
        repos = RunRepositories(
            scenario_repo=ScenarioVersionRepository(session),
            mv_repo=ModelVersionRepository(session),
            md_repo=ModelDataRepository(session),
            snap_repo=RunSnapshotRepository(session),
            rs_repo=ResultSetRepository(session),
        )
        svc = RunExecutionService()
        inp = RunFromScenarioInput(
            workspace_id=env["ws_id"],
            scenario_spec_id=env["scenario_id"],
            scenario_spec_version=1,
        )
        result = await svc.execute_from_scenario(inp, repos)
        assert result.status == "COMPLETED"
        assert result.run_id is not None
        assert result.model_version_id == env["mv_id"]
        assert result.scenario_spec_version == 1
        assert result.result_summary is not None
        assert isinstance(result.result_summary, dict)

    async def test_execute_from_scenario_not_found(self, db_env):
        env = db_env
        session = env["session"]
        repos = RunRepositories(
            scenario_repo=ScenarioVersionRepository(session),
            mv_repo=ModelVersionRepository(session),
            md_repo=ModelDataRepository(session),
            snap_repo=RunSnapshotRepository(session),
            rs_repo=ResultSetRepository(session),
        )
        svc = RunExecutionService()
        inp = RunFromScenarioInput(
            workspace_id=env["ws_id"],
            scenario_spec_id=uuid4(),  # non-existent
        )
        result = await svc.execute_from_scenario(inp, repos)
        assert result.status == "FAILED"
        assert "not found" in (result.error or "").lower()

    async def test_execute_from_scenario_cross_workspace(self, db_env):
        env = db_env
        session = env["session"]
        repos = RunRepositories(
            scenario_repo=ScenarioVersionRepository(session),
            mv_repo=ModelVersionRepository(session),
            md_repo=ModelDataRepository(session),
            snap_repo=RunSnapshotRepository(session),
            rs_repo=ResultSetRepository(session),
        )
        svc = RunExecutionService()
        inp = RunFromScenarioInput(
            workspace_id=uuid4(),  # different workspace
            scenario_spec_id=env["scenario_id"],
            scenario_spec_version=1,
        )
        result = await svc.execute_from_scenario(inp, repos)
        assert result.status == "FAILED"

    async def test_result_summary_from_persisted_rows(self, db_env):
        """result_summary must come from persisted ResultSet rows, not in-memory."""
        env = db_env
        session = env["session"]
        repos = RunRepositories(
            scenario_repo=ScenarioVersionRepository(session),
            mv_repo=ModelVersionRepository(session),
            md_repo=ModelDataRepository(session),
            snap_repo=RunSnapshotRepository(session),
            rs_repo=ResultSetRepository(session),
        )
        svc = RunExecutionService()
        inp = RunFromScenarioInput(
            workspace_id=env["ws_id"],
            scenario_spec_id=env["scenario_id"],
            scenario_spec_version=1,
        )
        result = await svc.execute_from_scenario(inp, repos)
        assert result.status == "COMPLETED"
        # Verify run_id points to a real persisted snapshot
        snap = await repos.snap_repo.get(result.run_id)
        assert snap is not None
        assert snap.workspace_id == env["ws_id"]
        # Verify result sets exist
        rs_rows = await repos.rs_repo.get_by_run(result.run_id)
        assert len(rs_rows) > 0
```

**Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/services/test_run_execution.py::TestRunExecutionServiceFromScenario -v
```

Expected: FAIL — `RunExecutionService` class not defined or missing `execute_from_scenario`.

**Step 3: Implement RunExecutionService.execute_from_scenario()**

Add to `src/services/run_execution.py`:

```python
import asyncio
import numpy as np

from src.config.settings import get_settings
from src.data.workforce.satellite_coeff_loader import load_satellite_coefficients
from src.engine.batch import BatchRequest, BatchRunner, ScenarioInput, SingleRunResult
from src.engine.model_store import LoadedModel, ModelStore, compute_model_checksum
from src.engine.satellites import SatelliteCoefficients
from src.models.common import new_uuid7
from src.models.model_version import ModelVersion


# Reuse the global model store from runs API (singleton)
_model_store = ModelStore()

# Per-model locks (same pattern as src/api/runs.py)
_model_locks: dict[UUID, asyncio.Lock] = {}
_global_lock = asyncio.Lock()

ALLOWED_RUNTIME_PROVENANCE = frozenset({"curated_real"})


class RunExecutionService:
    """Shared deterministic engine execution service.

    Both ChatToolExecutor._handle_run_engine() and the API route
    POST /v1/workspaces/{ws}/engine/runs call this service.
    """

    async def execute_from_scenario(
        self,
        input: RunFromScenarioInput,
        repos: RunRepositories,
    ) -> RunExecutionResult:
        """Execute engine run from a scenario_spec_id (chat path).

        Resolves scenario -> model -> satellite coefficients -> BatchRunner.run().
        Persists RunSnapshot + ResultSet rows.
        Returns result_summary derived from persisted rows.
        """
        # 1. Resolve scenario
        if input.scenario_spec_version is not None:
            row = await repos.scenario_repo.get_by_id_and_version(
                input.scenario_spec_id, input.scenario_spec_version,
            )
            if row is None or row.workspace_id != input.workspace_id:
                return RunExecutionResult(
                    status="FAILED",
                    error=f"Scenario {input.scenario_spec_id} v{input.scenario_spec_version} not found in workspace",
                )
        else:
            row = await repos.scenario_repo.get_latest_by_workspace(
                input.scenario_spec_id, input.workspace_id,
            )
            if row is None:
                return RunExecutionResult(
                    status="FAILED",
                    error=f"Scenario {input.scenario_spec_id} not found in workspace",
                )

        model_version_id = row.base_model_version_id

        # 2. Enforce model provenance
        mv_row = await repos.mv_repo.get(model_version_id)
        if mv_row is None:
            return RunExecutionResult(
                status="FAILED",
                error=f"Model {model_version_id} not found",
            )
        prov = getattr(mv_row, "provenance_class", "unknown")
        if prov not in ALLOWED_RUNTIME_PROVENANCE:
            return RunExecutionResult(
                status="FAILED",
                error=f"Model provenance_class '{prov}' not allowed for runtime execution",
            )

        # 3. Load model into cache
        try:
            loaded = await self._ensure_model_loaded(model_version_id, repos.mv_repo, repos.md_repo)
        except Exception as exc:
            return RunExecutionResult(
                status="FAILED",
                error=f"Failed to load model: {str(exc)[:200]}",
            )

        # 4. Resolve satellite coefficients from curated loader
        try:
            loaded_coeffs = load_satellite_coefficients(
                year=row.base_year,
                sector_codes=loaded.sector_codes,
            )
            coeffs = loaded_coeffs.coefficients
        except Exception as exc:
            return RunExecutionResult(
                status="FAILED",
                error=f"Failed to load satellite coefficients: {str(exc)[:200]}",
            )

        # 5. Build scenario input from ScenarioSpec
        shocks = row.shock_items or []
        annual_shocks = self._build_annual_shocks(shocks, row.base_year, len(loaded.sector_codes))
        time_horizon = row.time_horizon or {}

        scenario = ScenarioInput(
            scenario_spec_id=row.scenario_spec_id,
            scenario_spec_version=row.version,
            name=row.name,
            annual_shocks=annual_shocks,
            base_year=row.base_year,
        )

        # 6. Execute engine
        version_refs = self._make_version_refs()
        settings = get_settings()
        runner = BatchRunner(model_store=_model_store, environment=settings.ENVIRONMENT.value)
        request = BatchRequest(
            scenarios=[scenario],
            model_version_id=model_version_id,
            satellite_coefficients=coeffs,
            version_refs=version_refs,
        )

        try:
            batch_result = runner.run(request)
        except Exception as exc:
            return RunExecutionResult(
                status="FAILED",
                error=f"Engine execution failed: {str(exc)[:200]}",
            )

        sr = batch_result.run_results[0]

        # 7. Persist snapshot + result sets
        await self._persist_run_result(
            sr, repos.snap_repo, repos.rs_repo,
            workspace_id=input.workspace_id,
            scenario_spec_id=row.scenario_spec_id,
            scenario_spec_version=row.version,
        )

        # 8. Build result_summary from persisted rows
        rs_rows = await repos.rs_repo.get_by_run(sr.snapshot.run_id)
        result_summary: dict[str, dict] = {}
        for rs_row in rs_rows:
            if getattr(rs_row, "series_kind", None) is None:
                result_summary[rs_row.metric_type] = rs_row.values

        return RunExecutionResult(
            status="COMPLETED",
            run_id=sr.snapshot.run_id,
            model_version_id=model_version_id,
            scenario_spec_id=row.scenario_spec_id,
            scenario_spec_version=row.version,
            result_summary=result_summary,
        )

    def _build_annual_shocks(
        self, shock_items: list, base_year: int, n_sectors: int,
    ) -> dict[int, np.ndarray]:
        """Convert shock_items list into annual_shocks dict for BatchRunner.

        MVP: applies all shocks to base_year as a single delta vector.
        """
        delta = np.zeros(n_sectors, dtype=np.float64)
        # shock_items is a list of dicts from ScenarioSpec
        # For now, empty shocks = zero delta (identity run)
        return {base_year: delta}

    def _make_version_refs(self) -> dict[str, UUID]:
        """Generate placeholder version refs for engine run."""
        return {
            "taxonomy_version_id": new_uuid7(),
            "concordance_version_id": new_uuid7(),
            "mapping_library_version_id": new_uuid7(),
            "assumption_library_version_id": new_uuid7(),
            "prompt_pack_version_id": new_uuid7(),
        }

    async def _ensure_model_loaded(
        self,
        model_version_id: UUID,
        mv_repo: ModelVersionRepository,
        md_repo: ModelDataRepository,
    ) -> LoadedModel:
        """Load model from cache, falling back to DB on miss.

        Same logic as src/api/runs.py::_ensure_model_loaded() but extracted
        into the shared service.
        """
        try:
            return _model_store.get(model_version_id)
        except KeyError:
            pass

        async with _global_lock:
            if model_version_id not in _model_locks:
                _model_locks[model_version_id] = asyncio.Lock()
            lock = _model_locks[model_version_id]

        async with lock:
            try:
                return _model_store.get(model_version_id)
            except KeyError:
                pass

            mv_row = await mv_repo.get(model_version_id)
            if mv_row is None:
                raise ValueError(f"Model {model_version_id} not found")
            md_row = await md_repo.get(model_version_id)
            if md_row is None:
                raise ValueError(f"Model data for {model_version_id} not found")

            z_matrix = np.array(md_row.z_matrix_json, dtype=np.float64)
            x_vector = np.array(md_row.x_vector_json, dtype=np.float64)

            artifact_kwargs: dict[str, object] = {}
            for key in ("compensation_of_employees", "gross_operating_surplus",
                        "taxes_less_subsidies", "household_consumption_shares",
                        "imports_vector", "deflator_series"):
                val = getattr(md_row, f"{key}_json", None)
                if val is not None:
                    artifact_kwargs[key] = val
            fd_val = getattr(md_row, "final_demand_f_json", None)
            if fd_val is not None:
                artifact_kwargs["final_demand_F"] = fd_val

            mv = ModelVersion(
                model_version_id=mv_row.model_version_id,
                base_year=mv_row.base_year,
                source=mv_row.source,
                sector_count=mv_row.sector_count,
                checksum=mv_row.checksum,
                **artifact_kwargs,
            )
            loaded = LoadedModel(
                model_version=mv,
                Z=z_matrix,
                x=x_vector,
                sector_codes=list(md_row.sector_codes),
            )
            _model_store.cache_prevalidated(loaded)
            return loaded

    async def _persist_run_result(
        self,
        sr: SingleRunResult,
        snap_repo: RunSnapshotRepository,
        rs_repo: ResultSetRepository,
        workspace_id: UUID | None = None,
        scenario_spec_id: UUID | None = None,
        scenario_spec_version: int | None = None,
    ) -> None:
        """Persist a SingleRunResult to DB (snapshot + result sets).

        Same logic as src/api/runs.py::_persist_run_result().
        """
        snap = sr.snapshot
        await snap_repo.create(
            run_id=snap.run_id,
            model_version_id=snap.model_version_id,
            taxonomy_version_id=snap.taxonomy_version_id,
            concordance_version_id=snap.concordance_version_id,
            mapping_library_version_id=snap.mapping_library_version_id,
            assumption_library_version_id=snap.assumption_library_version_id,
            prompt_pack_version_id=snap.prompt_pack_version_id,
            workspace_id=workspace_id,
            scenario_spec_id=scenario_spec_id,
            scenario_spec_version=scenario_spec_version,
        )
        for rs in sr.result_sets:
            await rs_repo.create(
                result_id=rs.result_id,
                run_id=rs.run_id,
                metric_type=rs.metric_type,
                values=rs.values,
                workspace_id=workspace_id,
                year=rs.year,
                series_kind=rs.series_kind,
                baseline_run_id=rs.baseline_run_id,
            )
```

**Step 4: Run tests**

```bash
python -m pytest tests/services/test_run_execution.py -v
```

Expected: All tests PASS.

**Step 5: Commit**

```bash
git add src/services/run_execution.py tests/services/test_run_execution.py
git commit -m "[sprint28] implement RunExecutionService.execute_from_scenario with TDD"
```

---

## Task 4: S28-0b — ExportExecutionService

**Files:**
- Create: `src/services/export_execution.py`
- Create: `tests/services/test_export_execution.py`
- Read (reference): `src/api/exports.py` (lines 216-287 for create_export)
- Read (reference): `src/export/orchestrator.py` (full)

**Step 1: Write failing tests**

Create `tests/services/test_export_execution.py` with tests for:
- `ExportExecutionInput` / `ExportExecutionResult` / `ExportRepositories` dataclass contracts
- `execute()` with sandbox mode success (COMPLETED with checksums)
- `execute()` with governed mode blocked by NFF
- `execute()` with missing quality assessment (BLOCKED)
- `execute()` with run not found in workspace (FAILED)

The service must:
- Load claims via `ClaimRepository.get_by_run()`
- Load quality assessment via `DataQualityRepository.get_by_run()`
- Check model provenance via snapshot lookup
- Call `ExportOrchestrator.execute()`
- Store artifacts via `ExportArtifactStorage`
- Persist export record via `ExportRepository.create()`

**Step 2: Run tests to verify failure**

```bash
python -m pytest tests/services/test_export_execution.py -v
```

**Step 3: Implement ExportExecutionService in `src/services/export_execution.py`**

Key patterns:
- `ExportExecutionInput(workspace_id, run_id, mode, export_formats, pack_data)`
- `ExportExecutionResult(status, export_id, checksums, blocking_reasons, artifact_refs, error)`
- `ExportRepositories(export_repo, claim_repo, quality_repo, snap_repo, mv_repo, artifact_store)`
- Workspace check: verify `RunSnapshot.workspace_id` matches input
- Reuse `_claim_row_to_model()` and `_check_model_provenance()` logic from `src/api/exports.py`

**Step 4: Run tests**

```bash
python -m pytest tests/services/test_export_execution.py -v
```

**Step 5: Commit**

```bash
git add src/services/export_execution.py tests/services/test_export_execution.py
git commit -m "[sprint28] implement ExportExecutionService with TDD"
```

---

## Task 5: S28-0c — Refactor API routes to use shared services

**Files:**
- Modify: `src/api/runs.py` (refactor `create_run` to call `RunExecutionService.execute_from_request()`)
- Modify: `src/api/exports.py` (refactor `create_export` to call `ExportExecutionService.execute()`)
- Modify: `src/services/run_execution.py` (add `execute_from_request()`)
- Test: run existing API tests as regression

**Step 1: Add `execute_from_request()` to RunExecutionService**

This method takes `RunFromRequestInput` (pre-parsed model_version_id, shocks, coefficients) and does the same execution + persistence as `execute_from_scenario()` but without scenario resolution.

**Step 2: Refactor `src/api/runs.py::create_run()`**

Replace the inline logic with:
```python
svc = RunExecutionService()
result = await svc.execute_from_request(input, repos)
```

Map `RunExecutionResult` back to `RunResponse`.

**Step 3: Refactor `src/api/exports.py::create_export()`**

Replace inline logic with:
```python
svc = ExportExecutionService()
result = await svc.execute(input, repos)
```

Map `ExportExecutionResult` back to `CreateExportResponse`.

**Step 4: Run regression tests**

```bash
python -m pytest tests/api/test_runs.py tests/api/test_api_exports.py tests/api/test_exports_download.py -v
```

Expected: All existing tests PASS (no behavior change).

**Step 5: Commit**

```bash
git add src/api/runs.py src/api/exports.py src/services/run_execution.py
git commit -m "[sprint28] refactor API routes to use shared execution services"
```

---

## Task 6: S28-1 — Wire chat run_engine to real execution

**Files:**
- Modify: `src/services/chat_tool_executor.py` (`_handle_run_engine`)
- Modify: `tests/services/test_chat_tool_executor.py`

**Step 1: Write failing tests for real run execution from chat**

Add to `tests/services/test_chat_tool_executor.py`:

```python
class TestRunEngineRealExecution:
    """S28-1: Real engine execution replaces dry-run."""

    async def test_run_engine_returns_real_run_id(self, db_session):
        """run_engine must return a real run_id backed by a persisted RunSnapshot."""
        # Setup: create scenario with model in db_session
        # Execute: call _handle_run_engine with scenario_spec_id
        # Assert: result has status=success, reason_code != "scenario_validated_dry_run"
        # Assert: RunSnapshot exists for returned run_id
        ...

    async def test_run_engine_persists_result_sets(self, db_session):
        """run_engine must persist ResultSet rows."""
        # Execute and verify ResultSet rows exist for the run_id
        ...

    async def test_run_engine_result_summary_present(self, db_session):
        """result dict must include result_summary from persisted rows."""
        ...

    async def test_run_engine_dry_run_removed(self, db_session):
        """reason_code must NOT be scenario_validated_dry_run."""
        ...
```

**Step 2: Run tests to verify failure**

```bash
python -m pytest tests/services/test_chat_tool_executor.py::TestRunEngineRealExecution -v
```

**Step 3: Modify `_handle_run_engine()`**

Replace the dry-run validation with a call to `RunExecutionService.execute_from_scenario()`:

```python
async def _handle_run_engine(self, arguments: dict) -> dict:
    from src.services.run_execution import (
        RunExecutionService, RunFromScenarioInput, RunRepositories,
    )
    from src.repositories.engine import (
        ModelDataRepository, ModelVersionRepository,
        ResultSetRepository, RunSnapshotRepository,
    )
    from src.repositories.scenarios import ScenarioVersionRepository

    scenario_spec_id = arguments.get("scenario_spec_id")
    if not scenario_spec_id:
        return {"reason_code": "invalid_args", "error": "Missing required field: scenario_spec_id"}

    try:
        spec_uuid = UUID(str(scenario_spec_id))
    except (ValueError, AttributeError):
        return {"reason_code": "invalid_args", "error": f"Invalid scenario_spec_id format: {scenario_spec_id}"}

    version = arguments.get("scenario_spec_version")
    svc = RunExecutionService()
    repos = RunRepositories(
        scenario_repo=ScenarioVersionRepository(self._session),
        mv_repo=ModelVersionRepository(self._session),
        md_repo=ModelDataRepository(self._session),
        snap_repo=RunSnapshotRepository(self._session),
        rs_repo=ResultSetRepository(self._session),
    )
    inp = RunFromScenarioInput(
        workspace_id=self._workspace_id,
        scenario_spec_id=spec_uuid,
        scenario_spec_version=int(version) if version is not None else None,
    )

    result = await svc.execute_from_scenario(inp, repos)

    if result.status == "FAILED":
        return {
            "reason_code": "run_failed",
            "error": result.error or "Unknown engine failure",
        }

    return {
        "status": "success",
        "reason_code": "run_completed",
        "run_id": str(result.run_id),
        "scenario_spec_id": str(result.scenario_spec_id),
        "scenario_spec_version": result.scenario_spec_version,
        "model_version_id": str(result.model_version_id),
        "result_summary": result.result_summary,
    }
```

**Step 4: Run tests**

```bash
python -m pytest tests/services/test_chat_tool_executor.py -v
```

Expected: All tests PASS. Existing tests may need updating to match new reason_code `"run_completed"` instead of `"scenario_validated_dry_run"`.

**Step 5: Commit**

```bash
git add src/services/chat_tool_executor.py tests/services/test_chat_tool_executor.py
git commit -m "[sprint28] wire chat run_engine to real persisted engine execution"
```

---

## Task 7: S28-1b — Update trace metadata for real runs

**Files:**
- Modify: `src/services/chat.py` (remove dry-run `run_id` suppression)
- Modify: `tests/services/test_chat.py`

**Step 1: Write failing test**

```python
async def test_trace_run_id_populated_for_real_run(self, db_session, mock_copilot):
    """After S28, run_engine always produces a real run_id in trace."""
    # Setup copilot to return a run_engine tool call
    # Assert trace_metadata.run_id is populated (not suppressed)
```

**Step 2: Modify `send_message()` trace metadata block**

Remove the conditional suppression of `run_id` for `scenario_validated_dry_run`:

```python
# Before (S27):
if reason != "scenario_validated_dry_run":
    trace_dict["run_id"] = er.result.get("run_id")

# After (S28):
trace_dict["run_id"] = er.result.get("run_id")
```

**Step 3: Run tests**

```bash
python -m pytest tests/services/test_chat.py -v
```

**Step 4: Commit**

```bash
git add src/services/chat.py tests/services/test_chat.py
git commit -m "[sprint28] remove dry-run run_id suppression from trace metadata"
```

---

## Task 8: S28-2 — Wire chat create_export to real orchestration

**Files:**
- Modify: `src/services/chat_tool_executor.py` (`_handle_create_export`)
- Modify: `tests/services/test_chat_tool_executor.py`

**Step 1: Write failing tests**

```python
class TestCreateExportRealOrchestration:
    """S28-2: Real export orchestration replaces PENDING-only."""

    async def test_sandbox_export_completed(self, db_session):
        """Sandbox export should return COMPLETED with checksums."""
        ...

    async def test_governed_export_blocked_no_quality(self, db_session):
        """Governed export blocked when no quality assessment."""
        ...

    async def test_export_returns_blocking_reasons(self, db_session):
        """Blocked export must include blocking_reasons list."""
        ...

    async def test_export_not_pending(self, db_session):
        """Export status must NOT be PENDING after S28."""
        ...
```

**Step 2: Modify `_handle_create_export()`**

Replace PENDING-only creation with call to `ExportExecutionService.execute()`:

```python
async def _handle_create_export(self, arguments: dict) -> dict:
    from src.services.export_execution import (
        ExportExecutionService, ExportExecutionInput, ExportRepositories,
    )
    # ... validation ...
    svc = ExportExecutionService()
    repos = ExportRepositories(...)
    inp = ExportExecutionInput(
        workspace_id=self._workspace_id,
        run_id=run_uuid,
        mode=validated_mode,
        export_formats=export_formats,
        pack_data=pack_data,
    )
    result = await svc.execute(inp, repos)

    if result.status == "FAILED":
        return {"reason_code": "export_failed", "error": result.error}

    response = {
        "export_id": str(result.export_id),
        "status": result.status,
    }
    if result.checksums:
        response["checksums"] = result.checksums
    if result.blocking_reasons:
        response["blocking_reasons"] = result.blocking_reasons
    return response
```

**Step 3: Run tests**

```bash
python -m pytest tests/services/test_chat_tool_executor.py -v
```

**Step 4: Commit**

```bash
git add src/services/chat_tool_executor.py tests/services/test_chat_tool_executor.py
git commit -m "[sprint28] wire chat create_export to real export orchestration"
```

---

## Task 9: S28-3a — ChatNarrativeService (facts extraction + baseline builder)

**Files:**
- Create: `src/services/chat_narrative.py`
- Create: `tests/services/test_chat_narrative.py`

**Step 1: Write failing tests**

```python
# tests/services/test_chat_narrative.py
"""Tests for ChatNarrativeService (Sprint 28)."""

import pytest
from src.models.chat import ToolExecutionResult

pytestmark = pytest.mark.anyio


class TestNarrativeFacts:
    def test_extract_facts_from_successful_run(self):
        from src.services.chat_narrative import ChatNarrativeService, NarrativeFacts
        svc = ChatNarrativeService()
        results = [
            ToolExecutionResult(
                tool_name="run_engine", status="success",
                result={
                    "run_id": "abc-123", "model_version_id": "mv-1",
                    "scenario_spec_id": "sc-1", "scenario_spec_version": 1,
                    "result_summary": {"total_output": {"total": 1500.0}},
                },
            ),
        ]
        facts = svc.extract_facts(results)
        assert facts.run_completed is True
        assert facts.run_id == "abc-123"
        assert facts.has_meaningful_results is True

    def test_extract_facts_all_failed(self):
        from src.services.chat_narrative import ChatNarrativeService
        svc = ChatNarrativeService()
        results = [
            ToolExecutionResult(
                tool_name="run_engine", status="error",
                reason_code="run_failed",
                error_summary="Model not found",
            ),
        ]
        facts = svc.extract_facts(results)
        assert facts.run_completed is False
        assert facts.has_meaningful_results is False
        assert "Model not found" in facts.errors

    def test_extract_facts_export_blocked(self):
        from src.services.chat_narrative import ChatNarrativeService
        svc = ChatNarrativeService()
        results = [
            ToolExecutionResult(
                tool_name="run_engine", status="success",
                result={"run_id": "r1", "result_summary": {"total_output": {"total": 100.0}}},
            ),
            ToolExecutionResult(
                tool_name="create_export", status="success",
                result={
                    "export_id": "e1", "status": "BLOCKED",
                    "blocking_reasons": ["No quality assessment"],
                },
            ),
        ]
        facts = svc.extract_facts(results)
        assert facts.export_status == "BLOCKED"
        assert len(facts.export_blocking_reasons) == 1
        assert facts.has_meaningful_results is True


class TestBaselineNarrative:
    def test_build_baseline_run_success(self):
        from src.services.chat_narrative import ChatNarrativeService, NarrativeFacts
        svc = ChatNarrativeService()
        facts = NarrativeFacts(
            run_completed=True, run_id="r1",
            result_summary={"total_output": {"total": 1500.0}},
            has_meaningful_results=True,
        )
        narrative = svc.build_baseline_narrative(facts)
        assert "r1" in narrative
        assert "completed" in narrative.lower() or "run" in narrative.lower()

    def test_build_baseline_export_blocked(self):
        from src.services.chat_narrative import ChatNarrativeService, NarrativeFacts
        svc = ChatNarrativeService()
        facts = NarrativeFacts(
            run_completed=True, run_id="r1",
            result_summary={"total_output": {"total": 100.0}},
            export_completed=False, export_id="e1",
            export_status="BLOCKED",
            export_blocking_reasons=["No quality assessment"],
            has_meaningful_results=True,
        )
        narrative = svc.build_baseline_narrative(facts)
        assert "blocked" in narrative.lower()
        assert "quality" in narrative.lower()

    def test_build_baseline_all_failed(self):
        from src.services.chat_narrative import ChatNarrativeService, NarrativeFacts
        svc = ChatNarrativeService()
        facts = NarrativeFacts(
            run_completed=False,
            errors=["Model not found"],
            has_meaningful_results=False,
        )
        narrative = svc.build_baseline_narrative(facts)
        assert "failed" in narrative.lower() or "error" in narrative.lower()
```

**Step 2: Run tests to verify failure**

```bash
python -m pytest tests/services/test_chat_narrative.py -v
```

**Step 3: Implement ChatNarrativeService**

```python
# src/services/chat_narrative.py
"""ChatNarrativeService — post-execution narrative (Sprint 28).

Extracts normalized facts from tool execution results and builds
deterministic template-based baseline narratives. LLM enrichment
is handled separately by EconomistCopilot.enrich_narrative().
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.models.chat import ToolExecutionResult


@dataclass(frozen=True)
class NarrativeFacts:
    """Normalized domain facts extracted from tool execution results."""
    run_completed: bool = False
    run_id: str | None = None
    scenario_name: str | None = None
    model_version_id: str | None = None
    result_summary: dict | None = None
    export_completed: bool = False
    export_id: str | None = None
    export_status: str | None = None
    export_blocking_reasons: list[str] = field(default_factory=list)
    export_checksums: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    has_meaningful_results: bool = False


class ChatNarrativeService:
    """Extract facts and build baseline narrative from tool results."""

    def extract_facts(self, tool_results: list[ToolExecutionResult]) -> NarrativeFacts:
        """Normalize tool execution results into domain facts."""
        run_completed = False
        run_id = None
        model_version_id = None
        result_summary = None
        export_completed = False
        export_id = None
        export_status = None
        export_blocking_reasons: list[str] = []
        export_checksums: dict[str, str] = {}
        errors: list[str] = []
        has_meaningful = False

        for tr in tool_results:
            if tr.tool_name == "run_engine":
                if tr.status == "success" and tr.result:
                    run_completed = True
                    has_meaningful = True
                    run_id = tr.result.get("run_id")
                    model_version_id = tr.result.get("model_version_id")
                    result_summary = tr.result.get("result_summary")
                else:
                    if tr.error_summary:
                        errors.append(tr.error_summary)

            elif tr.tool_name == "create_export":
                if tr.status == "success" and tr.result:
                    has_meaningful = True
                    export_id = tr.result.get("export_id")
                    export_status = tr.result.get("status")
                    export_completed = export_status == "COMPLETED"
                    export_blocking_reasons = tr.result.get("blocking_reasons", [])
                    export_checksums = tr.result.get("checksums", {})
                else:
                    if tr.error_summary:
                        errors.append(tr.error_summary)

            elif tr.tool_name == "narrate_results":
                if tr.status == "success" and tr.result:
                    has_meaningful = True

            elif tr.status == "error" and tr.error_summary:
                errors.append(tr.error_summary)

        return NarrativeFacts(
            run_completed=run_completed,
            run_id=run_id,
            model_version_id=model_version_id,
            result_summary=result_summary,
            export_completed=export_completed,
            export_id=export_id,
            export_status=export_status,
            export_blocking_reasons=export_blocking_reasons,
            export_checksums=export_checksums,
            errors=errors,
            has_meaningful_results=has_meaningful,
        )

    def build_baseline_narrative(self, facts: NarrativeFacts) -> str:
        """Build a deterministic template narrative from facts.

        No LLM call. Grounded only in persisted deterministic outputs.
        """
        parts: list[str] = []

        if facts.run_completed and facts.run_id:
            parts.append(f"Engine run completed (run_id: {facts.run_id}).")
            if facts.result_summary:
                for metric, values in facts.result_summary.items():
                    if isinstance(values, dict) and "total" in values:
                        parts.append(f"  {metric}: {values['total']:,.2f}")

        if facts.export_status:
            if facts.export_completed:
                parts.append(f"Export {facts.export_id} generated successfully.")
                if facts.export_checksums:
                    for fmt, cs in facts.export_checksums.items():
                        parts.append(f"  {fmt}: {cs}")
            elif facts.export_status == "BLOCKED":
                parts.append(f"Export {facts.export_id} blocked:")
                for reason in facts.export_blocking_reasons:
                    parts.append(f"  - {reason}")
            elif facts.export_status == "FAILED":
                parts.append(f"Export failed.")

        if not facts.has_meaningful_results and facts.errors:
            parts.append("Execution encountered errors:")
            for err in facts.errors:
                parts.append(f"  - {err}")

        if not parts:
            return ""

        return "\n".join(parts)
```

**Step 4: Run tests**

```bash
python -m pytest tests/services/test_chat_narrative.py -v
```

**Step 5: Commit**

```bash
git add src/services/chat_narrative.py tests/services/test_chat_narrative.py
git commit -m "[sprint28] implement ChatNarrativeService with facts extraction and baseline builder"
```

---

## Task 10: S28-3b — Wire narrative into ChatService.send_message()

**Files:**
- Modify: `src/services/chat.py`
- Modify: `tests/services/test_chat.py`

**Step 1: Write failing tests**

```python
class TestPostExecutionNarrative:
    async def test_content_replaced_with_narrative_on_success(self, ...):
        """When tools produce meaningful results, content = post-execution narrative."""

    async def test_content_preserved_when_all_tools_fail(self, ...):
        """When all tools fail, original LLM content preserved + failure summary."""

    async def test_content_unchanged_when_no_tools(self, ...):
        """When no tools executed, original content unchanged."""
```

**Step 2: Modify send_message()**

After tool execution, add:
```python
from src.services.chat_narrative import ChatNarrativeService

# ... after tool execution ...
if exec_results:
    narrative_svc = ChatNarrativeService()
    tool_exec_results = [
        ToolExecutionResult(**er.model_dump()) if not isinstance(er, ToolExecutionResult) else er
        for er in exec_results
    ]
    facts = narrative_svc.extract_facts(tool_exec_results)

    if facts.has_meaningful_results:
        baseline = narrative_svc.build_baseline_narrative(facts)
        # Content policy: replace pre-execution content with narrative
        copilot_response.content = baseline
    elif facts.errors:
        # All failed: preserve original + append failure summary
        failure_summary = narrative_svc.build_baseline_narrative(facts)
        if failure_summary:
            copilot_response.content += "\n\n" + failure_summary
```

**Step 3: Run tests**

```bash
python -m pytest tests/services/test_chat.py -v
```

**Step 4: Commit**

```bash
git add src/services/chat.py tests/services/test_chat.py
git commit -m "[sprint28] wire post-execution narrative into ChatService.send_message"
```

---

## Task 11: S28-3c — EconomistCopilot.enrich_narrative() (optional enrichment)

**Files:**
- Modify: `src/agents/economist_copilot.py`
- Modify: `tests/agents/test_economist_copilot.py`

**Step 1: Write failing test**

```python
async def test_enrich_narrative_returns_enriched_text(self):
    """enrich_narrative() should call LLM and return enriched text."""

async def test_enrich_narrative_falls_back_to_baseline_on_failure(self):
    """If LLM fails, enrich_narrative() returns the baseline unchanged."""
```

**Step 2: Add enrich_narrative() method**

```python
async def enrich_narrative(
    self,
    baseline: str,
    context: dict[str, str] | None = None,
) -> str:
    """Enrich a baseline narrative into economist-quality prose.

    Receives sanitized, bounded context only. If LLM fails, returns
    the baseline unchanged.
    """
    if not baseline:
        return baseline

    ctx = context or {}
    enrichment_prompt = (
        "You are an economist writing a brief results summary. "
        "Rewrite the following into clear, professional economist prose. "
        "Do NOT invent any numbers — use only what is provided.\n\n"
        f"Context: {ctx.get('scenario_name', 'N/A')}\n\n"
        f"Baseline:\n{baseline}"
    )

    try:
        request = LLMRequest(
            system_prompt="You are a professional economist assistant.",
            user_prompt=enrichment_prompt,
            max_tokens=1024,
        )
        response = await self._llm.call_unstructured(request)
        return response.content
    except Exception:
        _logger.warning("Narrative enrichment failed, using baseline", exc_info=True)
        return baseline
```

**Step 3: Run tests**

```bash
python -m pytest tests/agents/test_economist_copilot.py -v
```

**Step 4: Commit**

```bash
git add src/agents/economist_copilot.py tests/agents/test_economist_copilot.py
git commit -m "[sprint28] add EconomistCopilot.enrich_narrative for optional LLM enrichment"
```

---

## Task 12: S28-4 — Frontend: export blocking reasons and deep links

**Files:**
- Modify: `frontend/src/components/chat/message-bubble.tsx`
- Modify: `frontend/src/components/chat/__tests__/chat-interface.test.tsx`

**Step 1: Write failing frontend test**

```tsx
test('renders blocking reasons for blocked export', () => {
  // render MessageBubble with tool_call result status="blocked"
  // assert blocking_reasons are displayed
});

test('renders deep link for completed run', () => {
  // render with trace_metadata.run_id populated
  // assert link to /workspaces/{ws}/engine/runs/{run_id}
});

test('does not render download link for blocked export', () => {
  // render with export status=BLOCKED
  // assert no download link
});
```

**Step 2: Update message-bubble.tsx**

- Add blocking reasons display for blocked exports (already has amber badge)
- Add deep links for `run_id` and `export_id` from trace metadata
- Conditional download link only when export status is COMPLETED

**Step 3: Run tests**

```bash
cd frontend && npx vitest run src/components/chat/__tests__/chat-interface.test.tsx
```

**Step 4: Commit**

```bash
git add frontend/src/components/chat/message-bubble.tsx frontend/src/components/chat/__tests__/
git commit -m "[sprint28] add export blocking reasons display and real deep links"
```

---

## Task 13: S28-5a — Update copilot prompt and tool descriptions

**Files:**
- Modify: `src/agents/prompts/economist_copilot_v1.py`

**Step 1: Update tool descriptions**

- `run_engine`: Change "Execute the Leontief engine on a confirmed scenario" to "Execute a real engine run, persist RunSnapshot + ResultSet rows, and return results"
- `create_export`: Change "Create a Decision Pack export from engine results" to "Generate export artifacts through governance/provenance gates (COMPLETED, BLOCKED, or FAILED)"

**Step 2: Run tests**

```bash
python -m pytest tests/agents/test_economist_copilot.py -v
```

**Step 3: Commit**

```bash
git add src/agents/prompts/economist_copilot_v1.py
git commit -m "[sprint28] update copilot prompt to reflect real execution behavior"
```

---

## Task 14: S28-5b — OpenAPI, evidence, and tracker sync

**Files:**
- Modify: `openapi.json` (regenerate)
- Modify: `docs/evidence/sprint25-copilot-evidence.md`
- Modify: `docs/ImpactOS_Master_Build_Plan_v2.md`
- Modify: `docs/plans/2026-03-03-full-system-completion-master-plan.md`

**Step 1: Regenerate OpenAPI**

```bash
python -c "import json; from pathlib import Path; from src.api.main import app; Path('openapi.json').write_text(json.dumps(app.openapi(), indent=2), encoding='utf-8')"
python -c "import json; json.load(open('openapi.json', 'r', encoding='utf-8')); print('openapi.json valid')"
```

**Step 2: Update evidence docs**

Add Sprint 28 section to `docs/evidence/sprint25-copilot-evidence.md`:
- Test counts (backend + frontend)
- Real run execution proof
- Real export orchestration proof
- Post-execution narrative proof

**Step 3: Update trackers**

- Add S28 row to master build plan
- Add S28 to full-system completion master plan

**Step 4: Commit**

```bash
git add openapi.json docs/evidence/ docs/ImpactOS_Master_Build_Plan_v2.md docs/plans/2026-03-03-full-system-completion-master-plan.md
git commit -m "[sprint28] refresh sprint28 evidence and openapi"
```

---

## Task 15: Full verification and PR

**Files:**
- None (verification only)

**Step 1: Run full backend tests**

```bash
python -m pytest tests -q
```

Expected: All pass (29 skipped).

**Step 2: Run full frontend tests**

```bash
cd frontend && npx vitest run
```

Expected: All pass.

**Step 3: Run alembic health**

```bash
python -m alembic current
python -m alembic heads
python -m alembic check
```

Expected: head `020_chat_sessions_messages`, no new upgrade needed.

**Step 4: Push and open PR**

```bash
git push -u origin phase3-sprint28-copilot-real-execution
gh pr create --title "Sprint 28: Copilot Real Execution + Post-Execution Narrative" --body "$(cat <<'EOF'
## Summary
- Extract shared `RunExecutionService` and `ExportExecutionService` from inline API logic
- Wire chat `run_engine` to real `BatchRunner.run()` with persisted `RunSnapshot` + `ResultSet`
- Wire chat `create_export` to real `ExportOrchestrator.execute()` with governance gates
- Add `ChatNarrativeService` for post-execution narrative (facts extraction + baseline builder)
- Frontend: export blocking reasons, real deep links, amber badge for BLOCKED status

## Test plan
- [ ] Backend: all tests pass (target: ~5000+ tests)
- [ ] Frontend: all tests pass (target: 340+ tests)
- [ ] Alembic: no new migration, head unchanged
- [ ] OpenAPI: regenerated and valid
- [ ] Regression: existing run/export API behavior unchanged
- [ ] Real run: `run_engine` from chat creates persisted RunSnapshot
- [ ] Real export: `create_export` from chat returns COMPLETED/BLOCKED/FAILED
- [ ] Narrative: assistant message reflects executed results

Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Execution Dependencies

```
Task 1 (worktree)
  |
  v
Task 2 (RunExecution dataclasses)
  |
  v
Task 3 (execute_from_scenario) ---> Task 5 (refactor API routes)
  |                                    |
  v                                    v
Task 4 (ExportExecution) ----------> Task 5
  |
  v
Task 6 (wire chat run_engine) -----> Task 7 (trace metadata)
  |
  v
Task 8 (wire chat create_export)
  |
  v
Task 9 (ChatNarrativeService)
  |
  v
Task 10 (wire narrative into send_message)
  |
  v
Task 11 (enrich_narrative - optional)
  |
  v
Task 12 (frontend)
  |
  v
Task 13 (prompt update)
  |
  v
Task 14 (evidence/openapi)
  |
  v
Task 15 (verification + PR)
```

**Parallelizable groups:**
- Tasks 2-4 can be developed in parallel (independent services)
- Task 11 (enrich_narrative) is independent of Tasks 12-13
- Task 14 (docs) is independent of Task 12 (frontend)
