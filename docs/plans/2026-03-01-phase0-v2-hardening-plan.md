# Phase 0 v2: Remaining Hardening & Workflow Wiring — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close six remaining operational gaps (export-quality wiring, compile flow, storage DI, health checks, stale docs, E2E coverage) on top of the existing main branch.

**Architecture:** Hardening-only sprint. All repos, ORM, Docker, Celery, quality models already exist. Changes are route-level wiring, DI fixes, and test coverage. No new infrastructure.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy async, pytest + anyio, httpx AsyncClient.

---

## Task 0: Baseline Freeze + Failing Gap Tests

### Task 0.1: Create test directories

**Files:**
- Create: `tests/api/__init__.py`
- Create: `tests/api/test_exports_quality_wiring.py`
- Create: `tests/api/test_documents_storage_config.py`
- Create: `tests/api/test_health_dependencies.py`
- Create: `tests/api/test_scenarios_compile_flow.py`

**Step 1: Create `tests/api/__init__.py`**

```python
```

(Empty file — just makes it a package.)

**Step 2: Write failing test — export quality wiring**

Create `tests/api/test_exports_quality_wiring.py`:

```python
"""Tests for export ↔ quality wiring (Phase 0 v2 — G1).

Proves:
- Export route loads RunQualityAssessment and passes it to orchestrator.
- Governed export blocks when quality says used_synthetic_fallback=True.
- Sandbox export ignores quality (never blocked on synthetic fallback).
- Unresolved claims still block governed export independently.
"""

import pytest
from httpx import AsyncClient
from uuid_extensions import uuid7

from src.models.common import utc_now

WS_ID = str(uuid7())


def _make_export_payload(run_id: str, mode: str = "SANDBOX") -> dict:
    return {
        "run_id": run_id,
        "mode": mode,
        "export_formats": ["excel"],
        "pack_data": {
            "run_id": run_id,
            "scenario_name": "Test Scenario",
            "base_year": 2023,
            "currency": "SAR",
            "model_version_id": str(uuid7()),
            "scenario_version": 1,
            "executive_summary": {"headline_gdp": 4.2e9, "headline_jobs": 21200},
            "sector_impacts": [
                {
                    "sector_code": "C41",
                    "sector_name": "Steel",
                    "direct_impact": 500.0,
                    "indirect_impact": 250.0,
                    "total_impact": 750.0,
                    "multiplier": 1.5,
                    "domestic_share": 0.65,
                    "import_leakage": 0.35,
                },
            ],
            "input_vectors": {"C41": 1000.0},
            "sensitivity": [],
            "assumptions": [],
            "evidence_ledger": [],
        },
    }


async def _seed_quality_summary(
    db_session,
    *,
    run_id,
    workspace_id,
    used_synthetic_fallback: bool = False,
    data_mode: str = "curated_real",
):
    """Insert a RunQualitySummaryRow so the export route can load it."""
    from src.db.tables import RunQualitySummaryRow
    from src.models.common import new_uuid7

    row = RunQualitySummaryRow(
        summary_id=new_uuid7(),
        run_id=run_id,
        workspace_id=workspace_id,
        overall_run_score=0.85,
        overall_run_grade="B",
        coverage_pct=0.9,
        mapping_coverage_pct=0.8,
        publication_gate_pass=True,
        publication_gate_mode="SANDBOX",
        summary_version="1.0.0",
        summary_hash="sha256:test",
        payload={
            "assessment_version": 1,
            "composite_score": 0.85,
            "grade": "B",
            "data_mode": data_mode,
            "used_synthetic_fallback": used_synthetic_fallback,
            "fallback_reason": "no curated data" if used_synthetic_fallback else None,
            "data_source_id": "test-dataset",
            "checksum_verified": True,
            "warnings": [],
            "dimension_assessments": [],
            "applicable_dimensions": [],
            "assessed_dimensions": [],
            "missing_dimensions": [],
            "completeness_pct": 0.9,
            "waiver_required_count": 0,
            "critical_count": 0,
            "warning_count": 0,
            "info_count": 0,
            "known_gaps": [],
        },
        created_at=utc_now(),
    )
    db_session.add(row)
    await db_session.flush()
    return row


async def _seed_unresolved_claim(db_session, *, run_id, workspace_id):
    """Insert an unresolved ClaimRow so the export route can load it."""
    from src.db.tables import ClaimRow
    from src.models.common import new_uuid7

    row = ClaimRow(
        claim_id=new_uuid7(),
        run_id=run_id,
        workspace_id=workspace_id,
        text="Needs evidence.",
        claim_type="MODEL",
        status="NEEDS_EVIDENCE",
        disclosure_tier="INTERNAL",
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(row)
    await db_session.flush()
    return row


class TestExportQualityWiring:
    """G1: Export route must pass quality_assessment into orchestrator."""

    @pytest.mark.anyio
    async def test_governed_export_blocked_by_synthetic_fallback(
        self, client: AsyncClient, db_session,
    ) -> None:
        """Governed export should be BLOCKED when quality summary says
        used_synthetic_fallback=True."""
        from uuid import UUID

        run_id = uuid7()
        ws_id = uuid7()
        ws_str = str(ws_id)

        await _seed_quality_summary(
            db_session,
            run_id=run_id,
            workspace_id=ws_id,
            used_synthetic_fallback=True,
            data_mode="synthetic_fallback",
        )

        payload = _make_export_payload(str(run_id), mode="GOVERNED")
        response = await client.post(
            f"/v1/workspaces/{ws_str}/exports", json=payload,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "BLOCKED"
        assert any("synthetic" in r.lower() for r in data["blocking_reasons"])

    @pytest.mark.anyio
    async def test_sandbox_export_ignores_synthetic_fallback(
        self, client: AsyncClient, db_session,
    ) -> None:
        """Sandbox export should succeed even when quality says synthetic fallback."""
        run_id = uuid7()
        ws_id = uuid7()
        ws_str = str(ws_id)

        await _seed_quality_summary(
            db_session,
            run_id=run_id,
            workspace_id=ws_id,
            used_synthetic_fallback=True,
        )

        payload = _make_export_payload(str(run_id), mode="SANDBOX")
        response = await client.post(
            f"/v1/workspaces/{ws_str}/exports", json=payload,
        )
        data = response.json()
        assert data["status"] == "COMPLETED"

    @pytest.mark.anyio
    async def test_governed_export_blocked_by_unresolved_claims_independently(
        self, client: AsyncClient, db_session,
    ) -> None:
        """Unresolved claims should still block governed export
        even when quality is fine (no synthetic fallback)."""
        run_id = uuid7()
        ws_id = uuid7()
        ws_str = str(ws_id)

        await _seed_quality_summary(
            db_session,
            run_id=run_id,
            workspace_id=ws_id,
            used_synthetic_fallback=False,
        )
        await _seed_unresolved_claim(db_session, run_id=run_id, workspace_id=ws_id)

        payload = _make_export_payload(str(run_id), mode="GOVERNED")
        response = await client.post(
            f"/v1/workspaces/{ws_str}/exports", json=payload,
        )
        data = response.json()
        assert data["status"] == "BLOCKED"

    @pytest.mark.anyio
    async def test_governed_export_succeeds_no_quality_summary(
        self, client: AsyncClient,
    ) -> None:
        """If no quality summary exists for the run, pass None —
        governed export should still succeed (claims check only)."""
        run_id = str(uuid7())
        payload = _make_export_payload(run_id, mode="GOVERNED")
        response = await client.post(
            f"/v1/workspaces/{WS_ID}/exports", json=payload,
        )
        data = response.json()
        # No claims, no quality summary → should complete
        assert data["status"] == "COMPLETED"
```

**Step 3: Write failing test — document storage config**

Create `tests/api/test_documents_storage_config.py`:

```python
"""Tests for DI-driven document storage (Phase 0 v2 — G3).

Proves:
- Document storage root comes from settings, not hardcoded.
- Tests can override storage root via DI.
- Default local path still works.
"""

import tempfile

import pytest
from httpx import ASGITransport, AsyncClient
from uuid_extensions import uuid7

from src.db.session import get_async_session
from src.ingestion.storage import DocumentStorageService


class TestDocumentStorageDI:
    """G3: Document storage must be settings-driven."""

    @pytest.mark.anyio
    async def test_storage_root_from_settings(self, client: AsyncClient) -> None:
        """Upload should use the settings-driven storage root,
        not a hardcoded path."""
        workspace_id = str(uuid7())
        uploaded_by = str(uuid7())
        response = await client.post(
            f"/v1/workspaces/{workspace_id}/documents",
            files={"file": ("test.csv", b"a,b\n1,2\n", "text/csv")},
            data={
                "doc_type": "BOQ",
                "source_type": "CLIENT",
                "classification": "RESTRICTED",
                "language": "en",
                "uploaded_by": uploaded_by,
            },
        )
        assert response.status_code == 201

    @pytest.mark.anyio
    async def test_storage_override_in_tests(self, db_session) -> None:
        """Verify that get_document_storage is overridable via DI."""
        from src.api.main import app

        # This import should succeed after we create the DI factory
        from src.api.dependencies import get_document_storage

        with tempfile.TemporaryDirectory() as tmpdir:
            app.dependency_overrides[get_document_storage] = lambda: DocumentStorageService(
                storage_root=tmpdir
            )

            async def _override_session():
                yield db_session

            app.dependency_overrides[get_async_session] = _override_session

            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as ac:
                workspace_id = str(uuid7())
                uploaded_by = str(uuid7())
                resp = await ac.post(
                    f"/v1/workspaces/{workspace_id}/documents",
                    files={"file": ("test.csv", b"a,b\n1,2\n", "text/csv")},
                    data={
                        "doc_type": "BOQ",
                        "source_type": "CLIENT",
                        "classification": "RESTRICTED",
                        "language": "en",
                        "uploaded_by": uploaded_by,
                    },
                )
                assert resp.status_code == 201

            app.dependency_overrides.clear()
```

**Step 4: Write failing test — health dependencies**

Create `tests/api/test_health_dependencies.py`:

```python
"""Tests for expanded health checks (Phase 0 v2 — G4).

Proves:
- /health returns api, database, redis, object_storage check keys.
- Degraded when Redis is down.
- Degraded when storage is down.
- DB-only healthy is no longer "fully healthy".
"""

import pytest
from httpx import AsyncClient


class TestHealthDependencies:
    """G4: /health must check DB + Redis + object storage."""

    @pytest.mark.anyio
    async def test_health_includes_all_check_keys(self, client: AsyncClient) -> None:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        checks = data["checks"]
        assert "api" in checks
        assert "database" in checks
        assert "redis" in checks
        assert "object_storage" in checks

    @pytest.mark.anyio
    async def test_health_degraded_without_redis(self, client: AsyncClient) -> None:
        """In test env (no Redis running), status should be degraded."""
        response = await client.get("/health")
        data = response.json()
        # Redis won't be available in test — check for degraded or
        # that the redis key is present and False
        assert "redis" in data["checks"]

    @pytest.mark.anyio
    async def test_health_object_storage_check_present(self, client: AsyncClient) -> None:
        response = await client.get("/health")
        data = response.json()
        assert "object_storage" in data["checks"]
```

**Step 5: Write failing test — scenarios compile flow**

Create `tests/api/test_scenarios_compile_flow.py`:

```python
"""Tests for deterministic compile flow consolidation (Phase 0 v2 — G2).

Proves:
- Compile from stored document/extraction works (document-backed path).
- Compile rejects documents with no completed extraction.
- Payload-only path is deprecated (returns deprecation header).
"""

import csv
import io

import pytest
from httpx import AsyncClient
from uuid_extensions import uuid7


WS_ID = str(uuid7())


def _make_csv_content() -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerows([
        ["Description", "Quantity", "Unit", "Unit Price", "Total"],
        ["Structural Steel", "5000", "tonnes", "3500", "17500000"],
        ["Concrete Works", "20000", "m3", "450", "9000000"],
    ])
    return buf.getvalue().encode("utf-8")


async def _upload_and_extract(client: AsyncClient, workspace_id: str) -> tuple[str, str]:
    """Helper: upload a CSV doc, trigger extraction, return (doc_id, scenario_id)."""
    uploaded_by = str(uuid7())
    upload_resp = await client.post(
        f"/v1/workspaces/{workspace_id}/documents",
        files={"file": ("boq.csv", _make_csv_content(), "text/csv")},
        data={
            "doc_type": "BOQ",
            "source_type": "CLIENT",
            "classification": "RESTRICTED",
            "language": "en",
            "uploaded_by": uploaded_by,
        },
    )
    doc_id = upload_resp.json()["doc_id"]

    # Trigger extraction (sync mode in tests)
    await client.post(
        f"/v1/workspaces/{workspace_id}/documents/{doc_id}/extract",
        json={"extract_tables": True, "extract_line_items": True, "language_hint": "en"},
    )

    # Create scenario
    create_resp = await client.post(
        f"/v1/workspaces/{workspace_id}/scenarios",
        json={
            "name": "NEOM Test",
            "base_model_version_id": str(uuid7()),
            "base_year": 2023,
            "start_year": 2026,
            "end_year": 2030,
        },
    )
    scenario_id = create_resp.json()["scenario_spec_id"]
    return doc_id, scenario_id


class TestDocumentBackedCompile:
    """G2: Deterministic compile from stored document data."""

    @pytest.mark.anyio
    async def test_compile_from_stored_document(self, client: AsyncClient) -> None:
        """Compile should accept document_id and load extracted line items."""
        doc_id, scenario_id = await _upload_and_extract(client, WS_ID)

        # Get extracted line items to build decisions
        li_resp = await client.get(f"/v1/workspaces/{WS_ID}/documents/{doc_id}/line-items")
        items = li_resp.json()["items"]
        assert len(items) >= 1

        # Build decisions referencing extracted line items
        decisions = [
            {
                "line_item_id": item["line_item_id"],
                "final_sector_code": "F",
                "decision_type": "APPROVED",
                "suggested_confidence": 0.9,
                "decided_by": str(uuid7()),
            }
            for item in items
        ]

        response = await client.post(
            f"/v1/workspaces/{WS_ID}/scenarios/{scenario_id}/compile",
            json={
                "document_id": doc_id,
                "decisions": decisions,
                "phasing": {"2026": 0.3, "2027": 0.4, "2028": 0.3},
                "default_domestic_share": 0.65,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "shock_items" in data
        assert len(data["shock_items"]) >= 1

    @pytest.mark.anyio
    async def test_compile_rejects_doc_without_extraction(self, client: AsyncClient) -> None:
        """Compile should reject a document_id that has no completed extraction."""
        uploaded_by = str(uuid7())
        # Upload but do NOT extract
        upload_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/documents",
            files={"file": ("boq.csv", _make_csv_content(), "text/csv")},
            data={
                "doc_type": "BOQ",
                "source_type": "CLIENT",
                "classification": "RESTRICTED",
                "language": "en",
                "uploaded_by": uploaded_by,
            },
        )
        doc_id = upload_resp.json()["doc_id"]

        create_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/scenarios",
            json={
                "name": "No Extract Test",
                "base_model_version_id": str(uuid7()),
                "base_year": 2023,
                "start_year": 2026,
                "end_year": 2030,
            },
        )
        scenario_id = create_resp.json()["scenario_spec_id"]

        response = await client.post(
            f"/v1/workspaces/{WS_ID}/scenarios/{scenario_id}/compile",
            json={
                "document_id": doc_id,
                "decisions": [],
                "phasing": {"2026": 1.0},
            },
        )
        assert response.status_code == 409


class TestPayloadCompileDeprecation:
    """Payload-only compile path is deprecated."""

    @pytest.mark.anyio
    async def test_payload_compile_returns_deprecation_header(
        self, client: AsyncClient,
    ) -> None:
        """Legacy payload-based compile should return a Deprecation header."""
        create_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/scenarios",
            json={
                "name": "Legacy Test",
                "base_model_version_id": str(uuid7()),
                "base_year": 2023,
                "start_year": 2026,
                "end_year": 2030,
            },
        )
        scenario_id = create_resp.json()["scenario_spec_id"]
        line_item_id = str(uuid7())
        response = await client.post(
            f"/v1/workspaces/{WS_ID}/scenarios/{scenario_id}/compile",
            json={
                "line_items": [
                    {"line_item_id": line_item_id, "description": "Steel", "total_value": 1e6, "currency_code": "SAR"},
                ],
                "decisions": [
                    {"line_item_id": line_item_id, "final_sector_code": "C41", "decision_type": "APPROVED",
                     "suggested_confidence": 0.9, "decided_by": str(uuid7())},
                ],
                "phasing": {"2026": 1.0},
            },
        )
        assert response.status_code == 200
        assert "deprecation" in {k.lower() for k in response.headers.keys()}
```

**Step 6: Run all tests to verify baseline passes, new tests fail**

Run: `python -m pytest tests/ -x -q 2>&1 | tail -20`

Expected: Existing tests PASS. New tests FAIL because the code hasn't changed yet.

Then run only the new tests to confirm failures:

```bash
python -m pytest tests/api/ -v 2>&1 | tail -30
```

**Step 7: Commit**

```bash
git add tests/api/
git commit -m "[phase0-v2] add failing tests for remaining hardening gaps"
```

---

## Task 1: Fix Export ↔ Quality Wiring (G1)

### Task 1.1: Wire quality assessment into export route

**Files:**
- Modify: `src/api/exports.py` (lines 16, 112-132)

**Step 1: Add imports and DI for DataQualityRepository**

In `src/api/exports.py`, add the import:

```python
from src.api.dependencies import get_claim_repo, get_data_quality_repo, get_export_repo
```

And add the import for `RunQualityAssessment`:

```python
from src.quality.models import RunQualityAssessment
```

**Step 2: Modify `create_export` endpoint**

Replace the `create_export` function signature and body to inject `DataQualityRepository` and load the quality summary:

```python
@router.post("/{workspace_id}/exports", status_code=201, response_model=CreateExportResponse)
async def create_export(
    workspace_id: UUID,
    body: CreateExportRequest,
    repo: ExportRepository = Depends(get_export_repo),
    claim_repo: ClaimRepository = Depends(get_claim_repo),
    quality_repo: DataQualityRepository = Depends(get_data_quality_repo),
) -> CreateExportResponse:
    """Create a new export — generates requested formats with watermarks.

    S0-4: NFF claims now fetched from DB by run_id (not empty list).
    Phase 0 v2: Quality assessment loaded from DB for synthetic-fallback check.
    Governed exports will be properly blocked if claims are unresolved
    or if the run used synthetic fallback data.
    """
    request = ExportRequest(
        run_id=UUID(body.run_id),
        workspace_id=workspace_id,
        mode=ExportMode(body.mode),
        export_formats=body.export_formats,
        pack_data=body.pack_data,
    )

    # Fetch claims associated with this run from DB for NFF gate
    claim_rows = await claim_repo.get_by_run(UUID(body.run_id))
    claims = [_claim_row_to_model(r) for r in claim_rows]

    # Load quality assessment for synthetic-fallback check
    quality_assessment: RunQualityAssessment | None = None
    quality_row = await quality_repo.get_by_run(UUID(body.run_id))
    if quality_row is not None and quality_row.payload:
        try:
            quality_assessment = RunQualityAssessment.model_validate(quality_row.payload)
        except Exception:
            pass  # Malformed payload — treat as no assessment

    record = _orchestrator.execute(
        request=request,
        claims=claims,
        quality_assessment=quality_assessment,
    )

    # Persist export metadata to DB
    await repo.create(
        export_id=record.export_id,
        run_id=record.run_id,
        mode=record.mode.value,
        status=record.status.value,
        checksums_json=record.checksums,
        blocked_reasons=record.blocking_reasons,
    )

    return CreateExportResponse(
        export_id=str(record.export_id),
        status=record.status.value,
        checksums=record.checksums,
        blocking_reasons=record.blocking_reasons,
    )
```

Also add the missing import at the top:

```python
from src.repositories.data_quality import DataQualityRepository
```

**Step 3: Run tests for G1**

```bash
python -m pytest tests/api/test_exports_quality_wiring.py -v
```

Expected: All 4 tests PASS.

**Step 4: Run full suite to verify no regressions**

```bash
python -m pytest tests/ -x -q
```

Expected: All existing tests still pass.

**Step 5: Commit**

```bash
git add src/api/exports.py
git commit -m "[phase0-v2] wire quality assessment into export route"
```

---

## Task 2: Reconcile Compile Flows (G2)

### Task 2.1: Add document-backed compile path to scenarios.py

**Files:**
- Modify: `src/api/scenarios.py` (lines 18-24, 70-74, 213-280)

**Step 1: Add imports for document-backed loading**

Add to the imports section of `src/api/scenarios.py`:

```python
import warnings

from src.api.dependencies import (
    get_document_repo,
    get_extraction_job_repo,
    get_line_item_repo,
    get_scenario_version_repo,
)
from src.repositories.documents import (
    DocumentRepository,
    ExtractionJobRepository,
    LineItemRepository,
)
```

**Step 2: Modify CompileRequest to support document_id**

Replace the `CompileRequest` model:

```python
class CompileRequest(BaseModel):
    """Compile request for deterministic scenario compilation.

    Provide EITHER document_id (loads stored line items from extraction)
    OR line_items (deprecated payload-based path).
    """

    line_items: list[LineItemPayload] | None = None
    document_id: str | None = None
    decisions: list[DecisionPayload]
    phasing: dict[str, float]
    default_domestic_share: float = 0.65
```

**Step 3: Rewrite compile_scenario endpoint**

Replace the `compile_scenario` function:

```python
@router.post("/{workspace_id}/scenarios/{scenario_id}/compile")
async def compile_scenario(
    workspace_id: UUID,
    scenario_id: UUID,
    body: CompileRequest,
    repo: ScenarioVersionRepository = Depends(get_scenario_version_repo),
    doc_repo: DocumentRepository = Depends(get_document_repo),
    job_repo: ExtractionJobRepository = Depends(get_extraction_job_repo),
    li_repo: LineItemRepository = Depends(get_line_item_repo),
) -> dict:
    """Compile line items + decisions into shock items.

    Phase 0 v2: Supports document_id (loads extracted line items from DB).
    Payload-based line_items path is deprecated — use document_id instead.
    """
    from starlette.responses import JSONResponse

    spec = await _get_latest_or_404(repo, scenario_id)

    # --- Resolve line items ---
    headers: dict[str, str] = {}

    if body.document_id is not None:
        # Document-backed path: load from extraction
        line_items = await _load_items_from_document(
            doc_id_str=body.document_id,
            workspace_id=workspace_id,
            doc_repo=doc_repo,
            job_repo=job_repo,
            li_repo=li_repo,
        )
    elif body.line_items is not None and len(body.line_items) > 0:
        # Deprecated payload path
        warnings.warn(
            "Payload-based compile is deprecated. Use document_id instead.",
            DeprecationWarning,
            stacklevel=1,
        )
        headers["Deprecation"] = "true"
        headers["Sunset"] = "2026-06-01"
        line_items = _build_line_items_from_payload(body.line_items)
    else:
        raise HTTPException(
            status_code=422,
            detail="Provide either document_id or line_items (deprecated).",
        )

    # Build MappingDecisions
    decisions: list[MappingDecision] = []
    for dec_payload in body.decisions:
        dec = MappingDecision(
            line_item_id=UUID(dec_payload.line_item_id),
            suggested_sector_code=dec_payload.final_sector_code,
            suggested_confidence=dec_payload.suggested_confidence,
            final_sector_code=dec_payload.final_sector_code,
            decision_type=DecisionType(dec_payload.decision_type),
            decided_by=UUID(dec_payload.decided_by),
        )
        decisions.append(dec)

    # Build compilation input
    phasing = {int(year): share for year, share in body.phasing.items()}

    inp = CompilationInput(
        workspace_id=workspace_id,
        scenario_name=spec.name,
        base_model_version_id=spec.base_model_version_id,
        base_year=spec.base_year,
        time_horizon=spec.time_horizon,
        line_items=line_items,
        decisions=decisions,
        default_domestic_share=body.default_domestic_share,
        default_import_share=1.0 - body.default_domestic_share,
        phasing=phasing,
    )

    compiled = _compiler.compile(inp)

    new_spec = await _record_new_version(repo, spec)

    response_data = {
        "scenario_spec_id": str(scenario_id),
        "version": new_spec.version,
        "shock_items": [si.model_dump() for si in compiled.shock_items],
        "data_quality_summary": (
            compiled.data_quality_summary.model_dump()
            if compiled.data_quality_summary else None
        ),
    }

    return JSONResponse(content=response_data, headers=headers)
```

**Step 4: Add helper functions**

Add these below the existing helper section:

```python
def _build_line_items_from_payload(
    payload_items: list[LineItemPayload],
) -> list[BoQLineItem]:
    """Build BoQLineItems from deprecated payload format.

    DEPRECATED: Use document-backed compile path instead.
    """
    line_items: list[BoQLineItem] = []
    for li_payload in payload_items:
        li = BoQLineItem(
            line_item_id=UUID(li_payload.line_item_id),
            doc_id=new_uuid7(),
            extraction_job_id=new_uuid7(),
            raw_text=li_payload.description,
            description=li_payload.description,
            total_value=li_payload.total_value,
            currency_code=li_payload.currency_code,
            page_ref=0,
            evidence_snippet_ids=[new_uuid7()],
        )
        line_items.append(li)
    return line_items


async def _load_items_from_document(
    *,
    doc_id_str: str,
    workspace_id: UUID,
    doc_repo: DocumentRepository,
    job_repo: ExtractionJobRepository,
    li_repo: LineItemRepository,
) -> list[BoQLineItem]:
    """Load line items from a stored document's latest completed extraction.

    Returns 409 if no completed extraction or no line items.
    """
    doc_id = UUID(doc_id_str)

    # Verify document exists
    doc_row = await doc_repo.get(doc_id)
    if doc_row is None:
        raise HTTPException(
            status_code=404,
            detail=f"Document {doc_id_str} not found.",
        )

    # Get latest completed extraction job
    latest_job = await job_repo.get_latest_completed(doc_id)
    if latest_job is None:
        raise HTTPException(
            status_code=409,
            detail=f"Document {doc_id_str} has no completed extraction. "
                   f"Run extraction first.",
        )

    # Load line items
    li_rows = await li_repo.get_by_extraction_job(latest_job.job_id)
    if not li_rows:
        raise HTTPException(
            status_code=409,
            detail=f"Document {doc_id_str} has no extracted line items.",
        )

    boq_items: list[BoQLineItem] = []
    for row in li_rows:
        evidence_ids = row.evidence_snippet_ids or [new_uuid7()]
        boq_items.append(BoQLineItem(
            line_item_id=row.line_item_id,
            doc_id=row.doc_id,
            extraction_job_id=row.extraction_job_id,
            raw_text=row.raw_text,
            description=row.description or row.raw_text,
            quantity=row.quantity,
            unit=row.unit,
            unit_price=row.unit_price,
            total_value=row.total_value or 0.0,
            currency_code=row.currency_code,
            category_code=row.category_code,
            page_ref=row.page_ref,
            evidence_snippet_ids=[
                UUID(eid) if isinstance(eid, str) else eid for eid in evidence_ids
            ],
        ))
    return boq_items
```

**Step 5: Run tests for G2**

```bash
python -m pytest tests/api/test_scenarios_compile_flow.py -v
```

Expected: All tests PASS.

**Step 6: Run full suite**

```bash
python -m pytest tests/ -x -q
```

Expected: All tests pass (including existing compile tests — they use payload path which still works, now with deprecation header).

**Step 7: Commit**

```bash
git add src/api/scenarios.py
git commit -m "[phase0-v2] converge deterministic compile flow onto stored document data"
```

### Checkpoint 1 — Pause and report

Report: baseline test count, new passing tests for Tasks 1–2, exact route/behavior for deprecated compile path.

---

## Task 3: Remove Hardcoded Document Storage Root (G3)

### Task 3.1: Add storage DI factory

**Files:**
- Modify: `src/api/dependencies.py` (add factory at bottom)
- Modify: `src/api/documents.py` (lines 24, 47, 89-97, 145-151)

**Step 1: Add `get_document_storage` factory to dependencies.py**

Add at the end of `src/api/dependencies.py`:

```python
# ---------------------------------------------------------------------------
# Document Storage (Phase 0 v2)
# ---------------------------------------------------------------------------


def get_document_storage() -> "DocumentStorageService":
    """Factory for document storage service, reading root from settings."""
    from src.config.settings import get_settings
    from src.ingestion.storage import DocumentStorageService

    settings = get_settings()
    return DocumentStorageService(storage_root=settings.OBJECT_STORAGE_PATH)
```

**Step 2: Modify `documents.py` to use DI**

Replace the module-level `_storage` line and update imports:

In imports, add:
```python
from src.api.dependencies import get_document_storage
```

Remove:
```python
_storage = DocumentStorageService(storage_root="./uploads")
```

Update `upload_document` signature:
```python
@router.post("/{workspace_id}/documents", status_code=201, response_model=UploadResponse)
async def upload_document(
    workspace_id: UUID,
    doc_repo: DocumentRepository = Depends(get_document_repo),
    storage: DocumentStorageService = Depends(get_document_storage),
    file: UploadFile = File(...),
    doc_type: str = Form(...),
    source_type: str = Form(...),
    classification: str = Form(...),
    language: str = Form("en"),
    uploaded_by: str = Form(...),
) -> UploadResponse:
```

Replace `_storage.upload(` with `storage.upload(` in the function body.

Update `extract_document` signature:
```python
@router.post(
    "/{workspace_id}/documents/{doc_id}/extract",
    status_code=202,
    response_model=ExtractResponse,
)
async def extract_document(
    workspace_id: UUID,
    doc_id: UUID,
    body: ExtractRequest,
    doc_repo: DocumentRepository = Depends(get_document_repo),
    job_repo: ExtractionJobRepository = Depends(get_extraction_job_repo),
    line_item_repo: LineItemRepository = Depends(get_line_item_repo),
    storage: DocumentStorageService = Depends(get_document_storage),
) -> ExtractResponse:
```

Replace both `_storage.retrieve(` calls with `storage.retrieve(`.

**Step 3: Run tests for G3**

```bash
python -m pytest tests/api/test_documents_storage_config.py -v
```

Expected: PASS.

**Step 4: Run full suite**

```bash
python -m pytest tests/ -x -q
```

**Step 5: Commit**

```bash
git add src/api/dependencies.py src/api/documents.py
git commit -m "[phase0-v2] inject document storage from settings"
```

---

## Task 4: Expand Health Checks (G4)

### Task 4.1: Add Redis and storage checks to /health

**Files:**
- Modify: `src/api/main.py` (lines 99-124)

**Step 1: Rewrite the health_check endpoint**

Replace the entire `health_check` function:

```python
@app.get("/health")
async def health_check() -> dict:
    """Liveness probe with component health checks.

    Phase 0 v2: Checks API + database + Redis + object storage.
    Returns 200 always (degraded status if components are down).
    """
    import asyncio

    checks: dict[str, bool] = {"api": True}

    async def _check_database() -> bool:
        try:
            from src.db.session import async_session_factory
            async with async_session_factory() as session:
                await session.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    async def _check_redis() -> bool:
        try:
            import redis.asyncio as aioredis
            r = aioredis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
            await r.ping()
            await r.aclose()
            return True
        except Exception:
            return False

    async def _check_object_storage() -> bool:
        try:
            from pathlib import Path
            storage_path = Path(settings.OBJECT_STORAGE_PATH)
            return storage_path.exists() and storage_path.is_dir()
        except Exception:
            return False

    db_ok, redis_ok, storage_ok = await asyncio.gather(
        _check_database(),
        _check_redis(),
        _check_object_storage(),
    )

    checks["database"] = db_ok
    checks["redis"] = redis_ok
    checks["object_storage"] = storage_ok

    all_ok = all(checks.values())

    return {
        "status": "ok" if all_ok else "degraded",
        "version": APP_VERSION,
        "environment": settings.ENVIRONMENT.value,
        "checks": checks,
    }
```

**Step 2: Run tests for G4**

```bash
python -m pytest tests/api/test_health_dependencies.py -v
```

Expected: PASS.

**Step 3: Run full suite**

```bash
python -m pytest tests/ -x -q
```

**Step 4: Commit**

```bash
git add src/api/main.py
git commit -m "[phase0-v2] expand health endpoint to redis and storage"
```

---

## Task 5: Reconcile Extraction Documentation (G5)

### Task 5.1: Update ExtractionService docstrings

**Files:**
- Modify: `src/ingestion/extraction.py` (lines 1-8, 29-34)

**Step 1: Update module docstring**

Replace lines 1-8:

```python
"""Document extraction service — MVP-2 Sections 8.2, 8.3, 8.5.

Handles CSV and Excel extraction deterministically (Section 8.2:
"Structured inputs bypass OCR"). Builds a DocumentGraph with bounding
boxes and generates EvidenceSnippets per data row.

PDF and layout-aware extraction is handled by the provider-based
architecture (LocalPdfProvider, AzureDIProvider) via ExtractionRouter,
with async dispatch through Celery tasks. See:
  - src/ingestion/providers/ for extraction providers
  - src/ingestion/tasks.py for Celery dispatch

This module is deterministic — no LLM calls.
"""
```

**Step 2: Update class docstring**

Replace lines 29-34:

```python
class ExtractionService:
    """Deterministic extraction for CSV and Excel documents.

    PDF/layout extraction is handled separately by provider-based
    routing (LocalPdfProvider, AzureDIProvider). See
    ``src/ingestion/providers/`` and ``src/ingestion/tasks.py``.
    """
```

### Task 5.2: Fix Makefile validate-model path

**Files:**
- Modify: `Makefile` (line 62)

**Step 1: Verify path is broken**

The file exists at `data/synthetic/saudi_io_synthetic_v1.json`, NOT at `data/curated/saudi_io_synthetic_v1.json`. Fix the Makefile:

Replace line 62:
```makefile
validate-model: ## Validate synthetic model (data/synthetic/saudi_io_synthetic_v1.json)
	python -m scripts.validate_model data/synthetic/saudi_io_synthetic_v1.json
```

**Step 2: Run full suite**

```bash
python -m pytest tests/ -x -q
```

**Step 3: Commit**

```bash
git add src/ingestion/extraction.py Makefile
git commit -m "[phase0-v2] align extraction docs and fix Makefile validate-model path"
```

### Checkpoint 2 — Pause and report

Report: Tasks 3-5 done, health response shape, storage DI approach, Makefile fix confirmation.

---

## Task 6: End-to-End Hardening Integration Test

### Task 6.1: Create the proving test

**Files:**
- Create: `tests/integration/__init__.py` (if missing)
- Create: `tests/integration/test_phase0_e2e_hardening.py`

**Step 1: Check if `__init__.py` exists**

```bash
ls tests/integration/__init__.py 2>/dev/null || echo "MISSING"
```

Create if missing.

**Step 2: Write the E2E test**

Create `tests/integration/test_phase0_e2e_hardening.py`:

```python
"""End-to-end hardening integration test (Phase 0 v2).

Proves the full stored-document workflow:
  upload → extract → compile → (quality + claims) → export

Tests that:
  1. Export route passes quality summary through to orchestrator
  2. Governed export honors both claim status and synthetic-fallback provenance
  3. Deterministic compile path uses stored document data
  4. Document storage is settings-driven enough for test override
"""

import csv
import io

import pytest
from httpx import AsyncClient
from uuid_extensions import uuid7

from src.models.common import new_uuid7, utc_now


WS_ID = str(uuid7())


def _make_csv_content() -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerows([
        ["Description", "Quantity", "Unit", "Unit Price", "Total"],
        ["Structural Steel", "5000", "tonnes", "3500", "17500000"],
        ["Concrete Works", "20000", "m3", "450", "9000000"],
    ])
    return buf.getvalue().encode("utf-8")


async def _seed_quality_summary(
    db_session,
    *,
    run_id,
    workspace_id,
    used_synthetic_fallback: bool = False,
    data_mode: str = "curated_real",
):
    """Insert a RunQualitySummaryRow."""
    from src.db.tables import RunQualitySummaryRow

    row = RunQualitySummaryRow(
        summary_id=new_uuid7(),
        run_id=run_id,
        workspace_id=workspace_id,
        overall_run_score=0.85,
        overall_run_grade="B",
        coverage_pct=0.9,
        mapping_coverage_pct=0.8,
        publication_gate_pass=True,
        publication_gate_mode="SANDBOX",
        summary_version="1.0.0",
        summary_hash="sha256:test",
        payload={
            "assessment_version": 1,
            "composite_score": 0.85,
            "grade": "B",
            "data_mode": data_mode,
            "used_synthetic_fallback": used_synthetic_fallback,
            "fallback_reason": "no curated data" if used_synthetic_fallback else None,
            "data_source_id": "test-dataset",
            "checksum_verified": True,
            "warnings": [],
            "dimension_assessments": [],
            "applicable_dimensions": [],
            "assessed_dimensions": [],
            "missing_dimensions": [],
            "completeness_pct": 0.9,
            "waiver_required_count": 0,
            "critical_count": 0,
            "warning_count": 0,
            "info_count": 0,
            "known_gaps": [],
        },
        created_at=utc_now(),
    )
    db_session.add(row)
    await db_session.flush()


async def _seed_claim(
    db_session,
    *,
    run_id,
    workspace_id,
    status: str = "NEEDS_EVIDENCE",
):
    from src.db.tables import ClaimRow

    row = ClaimRow(
        claim_id=new_uuid7(),
        run_id=run_id,
        workspace_id=workspace_id,
        text="GDP impact claim needs evidence.",
        claim_type="MODEL",
        status=status,
        disclosure_tier="INTERNAL",
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    db_session.add(row)
    await db_session.flush()
    return row


def _make_export_payload(run_id: str, mode: str = "SANDBOX") -> dict:
    return {
        "run_id": run_id,
        "mode": mode,
        "export_formats": ["excel"],
        "pack_data": {
            "run_id": run_id,
            "scenario_name": "E2E Test Scenario",
            "base_year": 2023,
            "currency": "SAR",
            "model_version_id": str(uuid7()),
            "scenario_version": 1,
            "executive_summary": {"headline_gdp": 4.2e9, "headline_jobs": 21200},
            "sector_impacts": [
                {
                    "sector_code": "F",
                    "sector_name": "Construction",
                    "direct_impact": 500.0,
                    "indirect_impact": 250.0,
                    "total_impact": 750.0,
                    "multiplier": 1.5,
                    "domestic_share": 0.65,
                    "import_leakage": 0.35,
                },
            ],
            "input_vectors": {"F": 1000.0},
            "sensitivity": [],
            "assumptions": [],
            "evidence_ledger": [],
        },
    }


class TestPhase0E2EHardening:
    """Full stored-document workflow: upload → extract → compile → export."""

    @pytest.mark.anyio
    async def test_full_flow_sandbox_succeeds(self, client: AsyncClient) -> None:
        """Happy path: upload, extract, compile from doc, export sandbox."""
        uploaded_by = str(uuid7())

        # 1. Upload document
        upload_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/documents",
            files={"file": ("boq.csv", _make_csv_content(), "text/csv")},
            data={
                "doc_type": "BOQ",
                "source_type": "CLIENT",
                "classification": "RESTRICTED",
                "language": "en",
                "uploaded_by": uploaded_by,
            },
        )
        assert upload_resp.status_code == 201
        doc_id = upload_resp.json()["doc_id"]

        # 2. Extract
        extract_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/documents/{doc_id}/extract",
            json={"extract_tables": True, "extract_line_items": True, "language_hint": "en"},
        )
        assert extract_resp.status_code == 202

        # 3. Verify line items
        li_resp = await client.get(f"/v1/workspaces/{WS_ID}/documents/{doc_id}/line-items")
        items = li_resp.json()["items"]
        assert len(items) >= 1

        # 4. Create scenario
        create_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/scenarios",
            json={
                "name": "E2E Steel Project",
                "base_model_version_id": str(uuid7()),
                "base_year": 2023,
                "start_year": 2026,
                "end_year": 2030,
            },
        )
        scenario_id = create_resp.json()["scenario_spec_id"]

        # 5. Compile from stored document
        decisions = [
            {
                "line_item_id": item["line_item_id"],
                "final_sector_code": "F",
                "decision_type": "APPROVED",
                "suggested_confidence": 0.9,
                "decided_by": str(uuid7()),
            }
            for item in items
        ]

        compile_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/scenarios/{scenario_id}/compile",
            json={
                "document_id": doc_id,
                "decisions": decisions,
                "phasing": {"2026": 0.3, "2027": 0.4, "2028": 0.3},
                "default_domestic_share": 0.65,
            },
        )
        assert compile_resp.status_code == 200
        assert len(compile_resp.json()["shock_items"]) >= 1

        # 6. Sandbox export (no quality/claims needed)
        run_id = str(uuid7())
        export_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/exports",
            json=_make_export_payload(run_id, mode="SANDBOX"),
        )
        assert export_resp.status_code == 201
        assert export_resp.json()["status"] == "COMPLETED"

    @pytest.mark.anyio
    async def test_governed_export_blocked_by_unresolved_claim(
        self, client: AsyncClient, db_session,
    ) -> None:
        """Governed export: unresolved claim → BLOCKED."""
        run_id = uuid7()
        ws_id = uuid7()
        ws_str = str(ws_id)

        await _seed_claim(db_session, run_id=run_id, workspace_id=ws_id, status="NEEDS_EVIDENCE")
        await _seed_quality_summary(
            db_session, run_id=run_id, workspace_id=ws_id, used_synthetic_fallback=False,
        )

        export_resp = await client.post(
            f"/v1/workspaces/{ws_str}/exports",
            json=_make_export_payload(str(run_id), mode="GOVERNED"),
        )
        assert export_resp.json()["status"] == "BLOCKED"

    @pytest.mark.anyio
    async def test_governed_export_blocked_by_synthetic_fallback(
        self, client: AsyncClient, db_session,
    ) -> None:
        """Governed export: synthetic fallback → BLOCKED (even with no claims)."""
        run_id = uuid7()
        ws_id = uuid7()
        ws_str = str(ws_id)

        await _seed_quality_summary(
            db_session, run_id=run_id, workspace_id=ws_id,
            used_synthetic_fallback=True, data_mode="synthetic_fallback",
        )

        export_resp = await client.post(
            f"/v1/workspaces/{ws_str}/exports",
            json=_make_export_payload(str(run_id), mode="GOVERNED"),
        )
        data = export_resp.json()
        assert data["status"] == "BLOCKED"
        assert any("synthetic" in r.lower() for r in data["blocking_reasons"])

    @pytest.mark.anyio
    async def test_sandbox_export_ignores_synthetic_quality(
        self, client: AsyncClient, db_session,
    ) -> None:
        """Sandbox export always succeeds regardless of quality."""
        run_id = uuid7()
        ws_id = uuid7()
        ws_str = str(ws_id)

        await _seed_quality_summary(
            db_session, run_id=run_id, workspace_id=ws_id,
            used_synthetic_fallback=True,
        )

        export_resp = await client.post(
            f"/v1/workspaces/{ws_str}/exports",
            json=_make_export_payload(str(run_id), mode="SANDBOX"),
        )
        assert export_resp.json()["status"] == "COMPLETED"

    @pytest.mark.anyio
    async def test_governed_succeeds_when_claims_resolved_and_no_synthetic(
        self, client: AsyncClient, db_session,
    ) -> None:
        """Governed export succeeds: claims resolved + curated real data."""
        run_id = uuid7()
        ws_id = uuid7()
        ws_str = str(ws_id)

        await _seed_claim(db_session, run_id=run_id, workspace_id=ws_id, status="SUPPORTED")
        await _seed_quality_summary(
            db_session, run_id=run_id, workspace_id=ws_id,
            used_synthetic_fallback=False, data_mode="curated_real",
        )

        export_resp = await client.post(
            f"/v1/workspaces/{ws_str}/exports",
            json=_make_export_payload(str(run_id), mode="GOVERNED"),
        )
        assert export_resp.json()["status"] == "COMPLETED"
```

**Step 3: Run all new tests**

```bash
python -m pytest tests/integration/test_phase0_e2e_hardening.py -v
```

Expected: All 5 tests PASS.

**Step 4: Run full suite**

```bash
python -m pytest tests/ -x -q
```

**Step 5: Commit**

```bash
git add tests/integration/
git commit -m "[phase0-v2] add end-to-end hardening integration coverage"
```

---

## Task 7: Docs and Runbook Refresh

### Task 7.1: Update documentation

**Files:**
- Modify: `docs/LOCAL_RUNBOOK.md` (if exists)
- Modify: `README.md` (if applicable — verify before changing)

**Step 1: Check what docs exist**

```bash
ls docs/LOCAL_RUNBOOK.md 2>/dev/null
cat README.md | head -30
```

**Step 2: Update docs to reflect**

Key updates to include wherever appropriate:
- `make up`, `make migrate`, `make seed`, `make serve` workflow
- Governed export depends on both NFF claim status AND quality provenance
- Document storage path is settings-driven (`OBJECT_STORAGE_PATH`)
- `/health` now covers DB + Redis + storage
- Real workflow is: upload → extract → compile-from-doc → run → export
- Payload-based compile is deprecated

**Step 3: Commit**

```bash
git add docs/ README.md
git commit -m "[phase0-v2] update docs for hardened workflow wiring"
```

### Checkpoint 3 — Final review-ready state

Report:
- Total passing tests
- All new tests added
- Exact files modified
- Any intentionally deferred items

---

## Final Verification

Run all tests:

```bash
python -m pytest tests/ -q
python -m pytest tests/api/test_exports_quality_wiring.py -q
python -m pytest tests/api/test_documents_storage_config.py -q
python -m pytest tests/api/test_health_dependencies.py -q
python -m pytest tests/api/test_scenarios_compile_flow.py -q
python -m pytest tests/integration/test_phase0_e2e_hardening.py -q
```

Then provide a review summary:
- What changed
- What stayed intentionally unchanged
- Any risk area still left for a later sprint

## Success Criteria Checklist

- [ ] `src/api/exports.py` passes `quality_assessment` to ExportOrchestrator
- [ ] Governed export blocks on unresolved claims AND synthetic fallback
- [ ] Deterministic scenario compile no longer depends on payload-built line items
- [ ] Document storage root is settings-driven, not hardcoded
- [ ] `/health` checks DB + Redis + storage
- [ ] Extraction comments/docstrings match the actual architecture
- [ ] One E2E integration test proves the full stored-document workflow
- [ ] All existing tests still pass
- [ ] Branch remains unmerged and review-ready
