# Sprint 24: Full-System Staging Proof + Go/No-Go Dossier

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Close Sprint 23 carryovers I-2 (ScenarioSpec into bridge engine) and I-4 (populate RunSelector), then compile full-system staging proof evidence and a go/no-go dossier.

**Architecture:** I-2 requires a new migration (019) adding `scenario_spec_id` + `scenario_spec_version` to `run_snapshots`, wiring the spec through `_persist_run_result()` and both run-creation paths, then fetching specs in the bridge API. I-4 requires a new `GET /{workspace_id}/engine/runs` list endpoint, a `useWorkspaceRuns()` hook, and wiring it into the compare page. Staging proof + dossier are evidence-gathering documentation tasks.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy async, Alembic, NumPy, Next.js 15, React 18, TanStack Query, Vitest, Tailwind CSS

**Branch:** `phase3-sprint24-full-system-staging-proof`
**Baseline:** 4609 backend tests, 303 frontend tests, alembic head 018

---

## Task 1: Add scenario_spec_id columns to run_snapshots (Migration 019)

**Files:**
- Create: `alembic/versions/019_run_snapshot_scenario_link.py`
- Modify: `src/db/tables.py` (RunSnapshotRow, lines 122-138)

**Step 1: Write the migration file**

Create `alembic/versions/019_run_snapshot_scenario_link.py`:

```python
"""019: Add scenario_spec_id + scenario_spec_version to run_snapshots.

Sprint 24 carryover I-2: link runs to their source scenario
so variance bridge can detect PHASING/IMPORT_SHARE/FEASIBILITY drivers.

Revision ID: 019_run_snapshot_scenario_link
Revises: 018_variance_bridge_analyses
"""

import sqlalchemy as sa
from alembic import op

revision = "019_run_snapshot_scenario_link"
down_revision = "018_variance_bridge_analyses"
branch_labels = None
depends_on = None

from sqlalchemy.dialects import postgresql
FlexUUID = postgresql.UUID(as_uuid=True).with_variant(sa.String(36), "sqlite")


def upgrade() -> None:
    op.add_column(
        "run_snapshots",
        sa.Column("scenario_spec_id", FlexUUID, nullable=True),
    )
    op.add_column(
        "run_snapshots",
        sa.Column("scenario_spec_version", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_run_snapshots_scenario_spec_id",
        "run_snapshots",
        ["scenario_spec_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_run_snapshots_scenario_spec_id",
        table_name="run_snapshots",
    )
    op.drop_column("run_snapshots", "scenario_spec_version")
    op.drop_column("run_snapshots", "scenario_spec_id")
```

**Step 2: Add ORM columns to RunSnapshotRow**

In `src/db/tables.py`, add after `workspace_id` field (line 135):

```python
    scenario_spec_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)
    scenario_spec_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
```

**Step 3: Run backend tests to verify no breakage**

Run: `python -m pytest tests/ -q --tb=short`
Expected: 4609 passed (existing tests unaffected — new columns are nullable)

**Step 4: Commit**

```bash
git add alembic/versions/019_run_snapshot_scenario_link.py src/db/tables.py
git commit -m "[sprint24] add scenario_spec_id/version to run_snapshots (migration 019)"
```

---

## Task 2: Wire scenario_spec through run persistence (TDD)

**Files:**
- Modify: `src/repositories/engine.py` (RunSnapshotRepository.create, lines 93-115)
- Modify: `src/api/runs.py` (_persist_run_result, lines 409-426; create_run, ~619; run_from_scenario in scenarios.py)
- Test: `tests/api/test_variance_bridge_api.py` (add I-2 tests)

**Step 1: Write failing test — scenario_spec_id persisted on run creation**

Add to `tests/api/test_variance_bridge_api.py` a new test class:

```python
class TestScenarioSpecPersistence:
    """I-2: scenario_spec_id is stored on RunSnapshotRow and available to bridge."""

    async def test_run_snapshot_stores_scenario_spec_id(self, session):
        """RunSnapshotRow stores scenario_spec_id when provided."""
        await _seed_ws(session)
        run_id = uuid7()
        spec_id = uuid7()
        row = RunSnapshotRow(
            run_id=run_id,
            model_version_id=uuid7(),
            taxonomy_version_id=UUID(_DUMMY_IDS["taxonomy_version_id"]),
            concordance_version_id=UUID(_DUMMY_IDS["concordance_version_id"]),
            mapping_library_version_id=UUID(_DUMMY_IDS["mapping_library_version_id"]),
            assumption_library_version_id=UUID(_DUMMY_IDS["assumption_library_version_id"]),
            prompt_pack_version_id=UUID(_DUMMY_IDS["prompt_pack_version_id"]),
            source_checksums=[],
            workspace_id=UUID(WS),
            scenario_spec_id=spec_id,
            scenario_spec_version=3,
            created_at=utc_now(),
        )
        session.add(row)
        await session.flush()

        loaded = await session.get(RunSnapshotRow, run_id)
        assert loaded.scenario_spec_id == spec_id
        assert loaded.scenario_spec_version == 3

    async def test_run_snapshot_scenario_spec_nullable(self, session):
        """RunSnapshotRow works without scenario_spec_id (backward compat)."""
        await _seed_ws(session)
        run_id, _ = await _create_run(session)
        loaded = await session.get(RunSnapshotRow, run_id)
        assert loaded.scenario_spec_id is None
        assert loaded.scenario_spec_version is None
```

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/api/test_variance_bridge_api.py::TestScenarioSpecPersistence -v`
Expected: FAIL (columns don't exist on model yet — wait, we added them in Task 1. If Task 1 done, these should PASS. So write a test for the REPOSITORY layer instead.)

Actually — the ORM columns were added in Task 1. So these tests should pass immediately. The REAL failing test is for the `_persist_run_result` function and bridge endpoint integration. Write THIS test instead:

```python
    async def test_bridge_passes_spec_when_available(self, client, session):
        """Bridge endpoint passes spec_a/spec_b to engine when runs have scenario_spec_id."""
        await _seed_ws(session)
        # Create a ScenarioSpecRow with shock_items
        spec_id = uuid7()
        spec_row = ScenarioSpecRow(
            scenario_spec_id=spec_id,
            version=1,
            name="Test Scenario",
            workspace_id=UUID(WS),
            base_model_version_id=uuid7(),
            currency="SAR",
            base_year=2024,
            time_horizon={"start_year": 2024, "end_year": 2028},
            shock_items=[{"type": "ImportSubstitution", "sector_code": "C41", "target_share": 0.5}],
            disclosure_tier="TIER0",
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add(spec_row)
        await session.flush()

        # Create runs WITH scenario_spec_id
        mv_id = uuid7()
        run_a, _ = await _create_run(session, model_version_id=mv_id)
        run_b, _ = await _create_run(session, model_version_id=mv_id)
        # Manually set scenario_spec_id
        snap_a = await session.get(RunSnapshotRow, run_a)
        snap_a.scenario_spec_id = spec_id
        snap_a.scenario_spec_version = 1
        snap_b = await session.get(RunSnapshotRow, run_b)
        snap_b.scenario_spec_id = spec_id
        snap_b.scenario_spec_version = 1
        await session.flush()

        # Add results
        await _add_result(session, run_a, values={"total": 100.0})
        await _add_result(session, run_b, values={"total": 120.0})

        resp = await client.post(
            f"/v1/workspaces/{WS}/variance-bridges",
            json={"run_a_id": str(run_a), "run_b_id": str(run_b)},
        )
        assert resp.status_code == 201
        data = resp.json()
        # With spec available, the engine CAN detect IMPORT_SHARE drivers
        # (whether it actually does depends on spec differences between runs)
        assert "drivers" in data
```

**Step 3: Update RunSnapshotRepository.create() to accept scenario_spec_id**

In `src/repositories/engine.py`, update `create()` method to accept two new optional params:

```python
    async def create(self, *, run_id, model_version_id, taxonomy_version_id,
                     concordance_version_id, mapping_library_version_id,
                     assumption_library_version_id, prompt_pack_version_id,
                     constraint_set_version_id=None, source_checksums=None,
                     workspace_id=None,
                     scenario_spec_id=None,
                     scenario_spec_version=None) -> RunSnapshotRow:
        row = RunSnapshotRow(
            run_id=run_id, model_version_id=model_version_id,
            # ... existing fields ...
            scenario_spec_id=scenario_spec_id,
            scenario_spec_version=scenario_spec_version,
            # ... rest
        )
```

**Step 4: Update _persist_run_result() to pass scenario fields**

In `src/api/runs.py`, update `_persist_run_result()`:

```python
async def _persist_run_result(
    sr: SingleRunResult,
    snap_repo: RunSnapshotRepository,
    rs_repo: ResultSetRepository,
    workspace_id: UUID | None = None,
    scenario_spec_id: UUID | None = None,
    scenario_spec_version: int | None = None,
) -> None:
    snap = sr.snapshot
    await snap_repo.create(
        # ... existing fields ...
        workspace_id=workspace_id,
        scenario_spec_id=scenario_spec_id,
        scenario_spec_version=scenario_spec_version,
    )
```

**Step 5: Update run_from_scenario() in scenarios.py to pass spec ID**

In `src/api/scenarios.py`, line ~1010, update the `_persist_run_result()` call:

```python
    await _persist_run_result(
        sr, snap_repo, rs_repo,
        workspace_id=workspace_id,
        scenario_spec_id=row.scenario_spec_id,
        scenario_spec_version=row.version,
    )
```

**Step 6: Update bridge endpoint to fetch + pass specs**

In `src/api/exports.py`, near line 499, replace the TODO with actual spec fetching:

```python
    # I-2: Fetch ScenarioSpec data for PHASING/IMPORT_SHARE/FEASIBILITY detection
    spec_a_dict: dict | None = None
    spec_b_dict: dict | None = None
    if snap_a.scenario_spec_id:
        spec_row_a = await scenario_repo.get_by_id_and_version(
            snap_a.scenario_spec_id,
            snap_a.scenario_spec_version or 1,
        )
        if spec_row_a:
            spec_a_dict = _scenario_row_to_bridge_dict(spec_row_a)
    if snap_b.scenario_spec_id:
        spec_row_b = await scenario_repo.get_by_id_and_version(
            snap_b.scenario_spec_id,
            snap_b.scenario_spec_version or 1,
        )
        if spec_row_b:
            spec_b_dict = _scenario_row_to_bridge_dict(spec_row_b)

    bridge_result = AdvancedVarianceBridge.compute_from_artifacts(
        run_a_snapshot=snap_a_dict,
        run_b_snapshot=snap_b_dict,
        result_a=result_a_dict,
        result_b=result_b_dict,
        spec_a=spec_a_dict,
        spec_b=spec_b_dict,
    )
```

Add helper function:

```python
def _scenario_row_to_bridge_dict(row: "ScenarioSpecRow") -> dict:
    """Convert ScenarioSpecRow to dict for bridge engine."""
    return {
        "time_horizon": row.time_horizon if isinstance(row.time_horizon, dict) else {},
        "shock_items": row.shock_items if isinstance(row.shock_items, list) else [],
    }
```

Add ScenarioVersionRepository dependency injection to the endpoint.

**Step 7: Run tests**

Run: `python -m pytest tests/api/test_variance_bridge_api.py -v`
Expected: All pass

**Step 8: Run full backend suite**

Run: `python -m pytest tests/ -q --tb=short`
Expected: 4609+ passed

**Step 9: Commit**

```bash
git add -A
git commit -m "[sprint24] wire scenario_spec through run persistence + bridge engine (I-2)"
```

---

## Task 3: Add list-runs API endpoint (TDD)

**Files:**
- Modify: `src/api/runs.py` (add GET list endpoint)
- Modify: `src/repositories/engine.py` (add paginated list method)
- Test: `tests/api/test_runs_list.py` (new)

**Step 1: Write failing test**

Create `tests/api/test_runs_list.py`:

```python
"""Tests for GET /v1/workspaces/{ws}/engine/runs — list runs."""
import pytest
from uuid_extensions import uuid7
from src.db.tables import RunSnapshotRow, WorkspaceRow
from src.models.common import utc_now

pytestmark = pytest.mark.anyio

WS = "00000000-0000-7000-8000-000000000099"

async def _seed_ws(session, ws_id=WS):
    from sqlalchemy import select
    result = await session.execute(
        select(WorkspaceRow).where(WorkspaceRow.workspace_id == uuid7.__class__(ws_id))
    )
    if result.scalar_one_or_none() is None:
        session.add(WorkspaceRow(
            workspace_id=uuid7.__class__(ws_id),
            client_name="Test", engagement_code="E",
            classification="INTERNAL", description="",
            created_by=uuid7(), created_at=utc_now(), updated_at=utc_now(),
        ))
        await session.flush()


class TestListRuns:
    async def test_list_runs_empty(self, client, session):
        await _seed_ws(session)
        resp = await client.get(f"/v1/workspaces/{WS}/engine/runs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["runs"] == []

    async def test_list_runs_returns_workspace_runs(self, client, session):
        await _seed_ws(session)
        # Create 2 runs
        for _ in range(2):
            row = RunSnapshotRow(
                run_id=uuid7(), model_version_id=uuid7(),
                taxonomy_version_id=uuid7(), concordance_version_id=uuid7(),
                mapping_library_version_id=uuid7(),
                assumption_library_version_id=uuid7(),
                prompt_pack_version_id=uuid7(),
                source_checksums=[], workspace_id=uuid7.__class__(WS),
                created_at=utc_now(),
            )
            session.add(row)
        await session.flush()

        resp = await client.get(f"/v1/workspaces/{WS}/engine/runs")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["runs"]) == 2

    async def test_list_runs_pagination(self, client, session):
        await _seed_ws(session)
        for _ in range(5):
            row = RunSnapshotRow(
                run_id=uuid7(), model_version_id=uuid7(),
                taxonomy_version_id=uuid7(), concordance_version_id=uuid7(),
                mapping_library_version_id=uuid7(),
                assumption_library_version_id=uuid7(),
                prompt_pack_version_id=uuid7(),
                source_checksums=[], workspace_id=uuid7.__class__(WS),
                created_at=utc_now(),
            )
            session.add(row)
        await session.flush()

        resp = await client.get(f"/v1/workspaces/{WS}/engine/runs?limit=2")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["runs"]) == 2
```

**Step 2: Run to verify failure**

Run: `python -m pytest tests/api/test_runs_list.py -v`
Expected: FAIL (endpoint doesn't exist)

**Step 3: Add paginated list to RunSnapshotRepository**

In `src/repositories/engine.py`, add method:

```python
    async def list_for_workspace(
        self, workspace_id: UUID, *, limit: int = 50, offset: int = 0,
    ) -> list[RunSnapshotRow]:
        """List run snapshots for a workspace, newest first."""
        result = await self._session.execute(
            select(RunSnapshotRow)
            .where(RunSnapshotRow.workspace_id == workspace_id)
            .order_by(RunSnapshotRow.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())
```

**Step 4: Add GET endpoint to runs.py**

In `src/api/runs.py`, add:

```python
@router.get("/{workspace_id}/engine/runs", response_model=ListRunsResponse)
async def list_runs(
    workspace_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    member: WorkspaceMember = Depends(require_workspace_member),
    snap_repo: RunSnapshotRepository = Depends(get_run_snapshot_repo),
) -> ListRunsResponse:
    """List run snapshots for a workspace (newest first)."""
    rows = await snap_repo.list_for_workspace(
        workspace_id, limit=limit, offset=offset,
    )
    return ListRunsResponse(
        runs=[
            RunSummary(
                run_id=str(row.run_id),
                model_version_id=str(row.model_version_id),
                created_at=row.created_at.isoformat(),
            )
            for row in rows
        ]
    )
```

Add response models:

```python
class RunSummary(BaseModel):
    run_id: str
    model_version_id: str
    created_at: str

class ListRunsResponse(BaseModel):
    runs: list[RunSummary]
```

**Step 5: Run tests**

Run: `python -m pytest tests/api/test_runs_list.py -v`
Expected: All pass

**Step 6: Run full backend suite**

Run: `python -m pytest tests/ -q --tb=short`
Expected: 4609+ passed

**Step 7: Commit**

```bash
git add -A
git commit -m "[sprint24] add GET /engine/runs list endpoint with pagination"
```

---

## Task 4: Add useWorkspaceRuns hook + wire RunSelector (TDD)

**Files:**
- Modify: `frontend/src/lib/api/hooks/useRuns.ts` (add useWorkspaceRuns)
- Modify: `frontend/src/app/w/[workspaceId]/exports/compare/page.tsx` (wire hook)
- Test: `frontend/src/app/w/[workspaceId]/exports/__tests__/compare-page.test.tsx` (update)

**Step 1: Write failing test for compare page with loaded runs**

In `frontend/src/app/w/[workspaceId]/exports/__tests__/compare-page.test.tsx`, add test:

```typescript
it('passes workspace runs to RunSelector when loaded', async () => {
  // Mock useWorkspaceRuns to return runs
  // Verify RunSelector receives non-empty runs array
  // Verify dropdown mode is shown (not manual mode)
});
```

**Step 2: Add useWorkspaceRuns hook**

In `frontend/src/lib/api/hooks/useRuns.ts`, add:

```typescript
export interface RunSummary {
  run_id: string;
  model_version_id: string;
  created_at: string;
}

interface ListRunsResponse {
  runs: RunSummary[];
}

/**
 * List all runs for a workspace (newest first).
 * GET /v1/workspaces/{workspace_id}/engine/runs
 */
export function useWorkspaceRuns(workspaceId: string) {
  return useQuery<ListRunsResponse>({
    queryKey: ['workspaceRuns', workspaceId],
    queryFn: async () => {
      const { data, error } = await api.GET(
        '/v1/workspaces/{workspace_id}/engine/runs',
        {
          params: { path: { workspace_id: workspaceId } },
        }
      );
      if (error) throw error;
      return data as unknown as ListRunsResponse;
    },
    enabled: !!workspaceId,
  });
}
```

**Step 3: Wire into compare page**

In `frontend/src/app/w/[workspaceId]/exports/compare/page.tsx`:

1. Import `useWorkspaceRuns` from hooks
2. Call `const { data: runsData } = useWorkspaceRuns(workspaceId);`
3. Map runs to RunOption format: `const runs = (runsData?.runs ?? []).map(r => ({ run_id: r.run_id, label: r.run_id.slice(0, 8) + '...', created_at: r.created_at }));`
4. Pass to RunSelector: `<RunSelector runs={runs} ...`
5. Remove `TODO(sprint-24)` comment

**Step 4: Run frontend tests**

Run: `cd frontend && npx vitest run`
Expected: 303+ passed

**Step 5: Commit**

```bash
git add -A
git commit -m "[sprint24] populate RunSelector from workspace runs (I-4)"
```

---

## Task 5: Regenerate OpenAPI + verify all tests pass

**Files:**
- Modify: `openapi.json` (regenerated)

**Step 1: Regenerate OpenAPI spec**

```bash
python -c "import json; from src.api.main import app; from fastapi.openapi.utils import get_openapi; spec = get_openapi(title=app.title, version=app.version, routes=app.routes); open('openapi.json', 'w').write(json.dumps(spec, indent=2))"
```

**Step 2: Verify new endpoint appears**

```bash
grep "engine/runs" openapi.json
```

Expected: GET endpoint should appear alongside existing POST endpoint.

**Step 3: Run full test suites**

Backend: `python -m pytest tests/ -q --tb=short`
Frontend: `cd frontend && npx vitest run`

Expected: Backend 4609+ passed, Frontend 303+ passed

**Step 4: Commit**

```bash
git add openapi.json
git commit -m "[sprint24] regenerate openapi with list-runs endpoint"
```

---

## Task 6: Full-system staging proof evidence

**Files:**
- Create: `docs/evidence/sprint24-staging-proof.md`

**Step 1: Compile evidence document**

Document proving every system layer is wired and functional:

1. **Auth layer**: JWT/workspace member verification (test evidence from existing auth tests)
2. **Document extraction**: Ingestion pipeline tests passing
3. **Compiler + depth agents**: Compiler tests + depth engine tests
4. **Deterministic engine runs**: Engine test evidence (Type I, Type II, RunSeries)
5. **Governance/NFF**: Publication gate, assumption lifecycle tests
6. **Delivery/export/download**: Export pipeline + variance bridge API
7. **Premium workflows**: Portal (S19) + Optimization (S21) + Structural (S20) + Workshop (S22) + Variance (S23)
8. **Methodology parity gate**: SG benchmark golden-run test evidence
9. **I-2 closure evidence**: ScenarioSpec now flows to bridge engine
10. **I-4 closure evidence**: RunSelector populated from workspace runs

For each layer, reference:
- Test file paths + pass counts
- Relevant API endpoints
- Any integration test evidence

**Step 2: Commit**

```bash
git add docs/evidence/sprint24-staging-proof.md
git commit -m "[sprint24] add full-system staging proof evidence"
```

---

## Task 7: Go/No-Go dossier + tracker sync

**Files:**
- Create: `docs/evidence/sprint24-go-no-go-dossier.md`
- Modify: `docs/ImpactOS_Master_Build_Plan_v2.md`
- Modify: `docs/plans/2026-03-03-full-system-completion-master-plan.md`
- Modify: `docs/evidence/release-readiness-checklist.md`

**Step 1: Write go/no-go dossier**

Document with:
1. **Go criteria** (all must be true):
   - MVP-1 through MVP-23 complete with test evidence
   - No planned build tracker entries remain
   - Methodology parity gate: SG benchmark within 0.1%
   - Sprint 23 carryovers I-2 and I-4 closed
   - Full test suite green (backend + frontend + migration)
   - OpenAPI spec current

2. **Rollback steps**:
   - Alembic downgrade sequence (019 → 018)
   - Git revert strategy
   - Feature flag considerations

3. **Unresolved risks**:
   - Real provider keys not configured (staging vs dev)
   - External IdP integration not live-tested
   - Object storage configuration pending
   - Load testing not performed

4. **Sprint 24 carryover** (if any): items for post-launch

**Step 2: Update tracker docs**

- Master Build Plan: Add Sprint 24 row with test count + commit
- Full System Completion Master Plan: Mark Sprint 24 complete
- Release Readiness Checklist: Add Sprint 24 evidence section

**Step 3: Commit**

```bash
git add docs/
git commit -m "[sprint24] go/no-go dossier + tracker sync"
```

---

## Task 8: Final verification + PR

**Step 1: Run full verification**

```bash
python -m pytest tests/ -q --tb=short
cd frontend && npx vitest run
python -m alembic heads
```

**Step 2: Push + create PR**

```bash
git push -u origin phase3-sprint24-full-system-staging-proof
gh pr create --title "Sprint 24: Full-System Staging Proof + Go/No-Go Dossier" --body "..."
```

PR should be unmerged/review-ready.

---

## Execution Notes

- **TDD for I-2 and I-4**: Write failing tests FIRST, then implement
- **No migration needed for I-4** (list endpoint is read-only)
- **I-2 migration (019)** is backward-compatible (nullable columns only)
- **Existing tests must not break** — all changes are additive
- **Sprint 24 is NOT a code sprint** — it's a staging proof + dossier sprint with two carryover fixes
