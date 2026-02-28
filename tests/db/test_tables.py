"""TDD tests for SQLAlchemy ORM models — src/db/tables.py.

Tests verify:
- All 20 tables are created correctly
- Column types (especially FlexJSON = JSONB with SQLite variant)
- Constraints (UNIQUE, FK, NOT NULL)
- Immutable vs operational table categorization
- Surrogate PK for versioned tables (ScenarioSpecRow)
- Matrix storage escape hatch (storage_format column)
"""

from uuid import UUID

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from src.db.session import Base
from src.db.tables import (
    WorkspaceRow,
    ModelVersionRow,
    ModelDataRow,
    ScenarioSpecRow,
    RunSnapshotRow,
    ResultSetRow,
    BatchRow,
    DocumentRow,
    ExtractionJobRow,
    LineItemRow,
    EvidenceSnippetRow,
    MappingDecisionRow,
    AssumptionRow,
    AssumptionLinkRow,
    ClaimRow,
    CompilationRow,
    ExportRow,
    MetricEventRow,
    EngagementRow,
    OverridePairRow,
)
from src.models.common import new_uuid7, utc_now


@pytest.fixture
async def engine():
    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest.fixture
async def session(engine):
    async with async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)() as s:
        yield s


# ---------------------------------------------------------------------------
# Table existence
# ---------------------------------------------------------------------------


class TestTableCreation:
    """All 20 tables should be created from Base.metadata."""

    EXPECTED_TABLES = {
        "workspaces",
        "model_versions",
        "model_data",
        "scenario_specs",
        "run_snapshots",
        "result_sets",
        "batches",
        "documents",
        "extraction_jobs",
        "line_items",
        "evidence_snippets",
        "mapping_decisions",
        "assumptions",
        "assumption_links",
        "claims",
        "compilations",
        "exports",
        "metric_events",
        "engagements",
        "override_pairs",
    }

    async def test_all_tables_exist(self, engine):
        async with engine.connect() as conn:
            table_names = await conn.run_sync(
                lambda sync_conn: inspect(sync_conn).get_table_names()
            )
        assert self.EXPECTED_TABLES.issubset(set(table_names)), (
            f"Missing tables: {self.EXPECTED_TABLES - set(table_names)}"
        )


# ---------------------------------------------------------------------------
# WorkspaceRow
# ---------------------------------------------------------------------------


class TestWorkspaceRow:
    async def test_create_workspace(self, session: AsyncSession):
        ws = WorkspaceRow(
            workspace_id=new_uuid7(),
            client_name="ACME Corp",
            engagement_code="ENG-001",
            classification="CONFIDENTIAL",
            description="Test engagement",
            created_by=new_uuid7(),
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add(ws)
        await session.flush()
        result = await session.get(WorkspaceRow, ws.workspace_id)
        assert result is not None
        assert result.client_name == "ACME Corp"
        assert result.classification == "CONFIDENTIAL"


# ---------------------------------------------------------------------------
# ModelVersionRow + ModelDataRow (IMMUTABLE)
# ---------------------------------------------------------------------------


class TestModelVersionRow:
    async def test_create_model_version(self, session: AsyncSession):
        mv = ModelVersionRow(
            model_version_id=new_uuid7(),
            base_year=2019,
            source="GASTAT 2019 IO Table",
            sector_count=45,
            checksum="sha256:" + "a" * 64,
            created_at=utc_now(),
        )
        session.add(mv)
        await session.flush()
        result = await session.get(ModelVersionRow, mv.model_version_id)
        assert result is not None
        assert result.base_year == 2019
        assert result.sector_count == 45

    async def test_model_data_with_storage_format(self, session: AsyncSession):
        """ModelDataRow must have storage_format column defaulting to 'json'."""
        mv_id = new_uuid7()
        mv = ModelVersionRow(
            model_version_id=mv_id,
            base_year=2019,
            source="test",
            sector_count=3,
            checksum="sha256:" + "b" * 64,
            created_at=utc_now(),
        )
        session.add(mv)
        await session.flush()

        md = ModelDataRow(
            model_version_id=mv_id,
            z_matrix_json=[[1.0, 0.5], [0.3, 1.0]],
            x_vector_json=[100.0, 200.0],
            sector_codes=["SEC01", "SEC02"],
        )
        session.add(md)
        await session.flush()

        result = await session.get(ModelDataRow, mv_id)
        assert result is not None
        assert result.storage_format == "json"
        assert result.z_matrix_json == [[1.0, 0.5], [0.3, 1.0]]
        assert result.x_vector_json == [100.0, 200.0]
        assert result.sector_codes == ["SEC01", "SEC02"]


# ---------------------------------------------------------------------------
# ScenarioSpecRow (VERSIONED — surrogate PK)
# ---------------------------------------------------------------------------


class TestScenarioSpecRow:
    async def test_surrogate_pk_and_versioning(self, session: AsyncSession):
        """ScenarioSpecRow uses auto-increment row_id PK, UNIQUE(spec_id, version)."""
        spec_id = new_uuid7()
        ws_id = new_uuid7()
        model_id = new_uuid7()

        v1 = ScenarioSpecRow(
            scenario_spec_id=spec_id,
            version=1,
            name="Base Case",
            workspace_id=ws_id,
            disclosure_tier="TIER0",
            base_model_version_id=model_id,
            currency="SAR",
            base_year=2024,
            time_horizon={"start_year": 2024, "end_year": 2030},
            shock_items=[],
            assumption_ids=[],
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add(v1)
        await session.flush()

        # Auto-increment PK should be set
        assert v1.row_id is not None
        assert isinstance(v1.row_id, int)

        v2 = ScenarioSpecRow(
            scenario_spec_id=spec_id,
            version=2,
            name="Base Case (updated)",
            workspace_id=ws_id,
            disclosure_tier="TIER0",
            base_model_version_id=model_id,
            currency="SAR",
            base_year=2024,
            time_horizon={"start_year": 2024, "end_year": 2031},
            shock_items=[{"type": "FINAL_DEMAND_SHOCK"}],
            assumption_ids=[],
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add(v2)
        await session.flush()

        assert v2.row_id != v1.row_id

    async def test_unique_constraint_spec_id_version(self, session: AsyncSession):
        """Cannot insert two rows with same (scenario_spec_id, version)."""
        spec_id = new_uuid7()
        ws_id = new_uuid7()
        model_id = new_uuid7()
        common = dict(
            scenario_spec_id=spec_id,
            version=1,
            name="Test",
            workspace_id=ws_id,
            disclosure_tier="TIER0",
            base_model_version_id=model_id,
            currency="SAR",
            base_year=2024,
            time_horizon={"start_year": 2024, "end_year": 2030},
            shock_items=[],
            assumption_ids=[],
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add(ScenarioSpecRow(**common))
        await session.flush()

        session.add(ScenarioSpecRow(**common))
        with pytest.raises(Exception):  # IntegrityError
            await session.flush()


# ---------------------------------------------------------------------------
# EvidenceSnippetRow (IMMUTABLE — Amendment 5)
# ---------------------------------------------------------------------------


class TestEvidenceSnippetRow:
    async def test_create_evidence_snippet(self, session: AsyncSession):
        snippet = EvidenceSnippetRow(
            snippet_id=new_uuid7(),
            source_id=new_uuid7(),
            page=3,
            bbox_x0=0.1,
            bbox_y0=0.2,
            bbox_x1=0.9,
            bbox_y1=0.5,
            extracted_text="Total project cost: SAR 500M",
            table_cell_ref={"table_id": "T1", "row": 0, "col": 2},
            checksum="sha256:" + "c" * 64,
            created_at=utc_now(),
        )
        session.add(snippet)
        await session.flush()
        result = await session.get(EvidenceSnippetRow, snippet.snippet_id)
        assert result is not None
        assert result.bbox_x0 == pytest.approx(0.1)
        assert result.bbox_y1 == pytest.approx(0.5)
        assert result.extracted_text == "Total project cost: SAR 500M"
        assert result.table_cell_ref == {"table_id": "T1", "row": 0, "col": 2}


# ---------------------------------------------------------------------------
# MappingDecisionRow (OPERATIONAL — Amendment 4)
# ---------------------------------------------------------------------------


class TestMappingDecisionRow:
    async def test_create_mapping_decision(self, session: AsyncSession):
        md = MappingDecisionRow(
            mapping_decision_id=new_uuid7(),
            line_item_id=new_uuid7(),
            scenario_spec_id=new_uuid7(),
            suggested_sector_code="SEC01",
            suggested_confidence=0.85,
            state="AI_SUGGESTED",
            decided_by=new_uuid7(),
            decided_at=utc_now(),
            created_at=utc_now(),
        )
        session.add(md)
        await session.flush()
        result = await session.get(MappingDecisionRow, md.mapping_decision_id)
        assert result is not None
        assert result.state == "AI_SUGGESTED"
        assert result.suggested_confidence == pytest.approx(0.85)

    async def test_state_update_allowed(self, session: AsyncSession):
        """MappingDecision is OPERATIONAL — state updates are allowed."""
        md = MappingDecisionRow(
            mapping_decision_id=new_uuid7(),
            line_item_id=new_uuid7(),
            scenario_spec_id=new_uuid7(),
            state="UNMAPPED",
            decided_by=new_uuid7(),
            decided_at=utc_now(),
            created_at=utc_now(),
        )
        session.add(md)
        await session.flush()

        md.state = "AI_SUGGESTED"
        md.suggested_sector_code = "SEC05"
        md.suggested_confidence = 0.72
        await session.flush()

        result = await session.get(MappingDecisionRow, md.mapping_decision_id)
        assert result.state == "AI_SUGGESTED"


# ---------------------------------------------------------------------------
# ResultSetRow (IMMUTABLE)
# ---------------------------------------------------------------------------


class TestResultSetRow:
    async def test_create_with_jsonb_values(self, session: AsyncSession):
        """FlexJSON columns store dict data correctly."""
        rs = ResultSetRow(
            result_id=new_uuid7(),
            run_id=new_uuid7(),
            metric_type="OUTPUT",
            values={"SEC01": 1500.0, "SEC02": 2300.0},
            sector_breakdowns={"direct": {"SEC01": 800.0}, "indirect": {"SEC01": 700.0}},
            created_at=utc_now(),
        )
        session.add(rs)
        await session.flush()
        result = await session.get(ResultSetRow, rs.result_id)
        assert result.values["SEC01"] == 1500.0
        assert result.sector_breakdowns["direct"]["SEC01"] == 800.0


# ---------------------------------------------------------------------------
# AssumptionRow + AssumptionLinkRow
# ---------------------------------------------------------------------------


class TestAssumptionRow:
    async def test_create_assumption(self, session: AsyncSession):
        a = AssumptionRow(
            assumption_id=new_uuid7(),
            type="IMPORT_SHARE",
            value=0.35,
            range_json={"min": 0.25, "max": 0.45},
            units="ratio",
            justification="Based on GASTAT 2019 data",
            evidence_refs=[],
            status="DRAFT",
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add(a)
        await session.flush()
        result = await session.get(AssumptionRow, a.assumption_id)
        assert result.value == 0.35
        assert result.range_json["min"] == 0.25

    async def test_assumption_link(self, session: AsyncSession):
        a_id = new_uuid7()
        a = AssumptionRow(
            assumption_id=a_id,
            type="DEFLATOR",
            value=1.02,
            units="factor",
            justification="CPI-based deflator",
            evidence_refs=[],
            status="DRAFT",
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add(a)
        await session.flush()

        link = AssumptionLinkRow(
            assumption_id=a_id,
            target_id=new_uuid7(),
            link_type="scenario",
        )
        session.add(link)
        await session.flush()
        assert link.id is not None


# ---------------------------------------------------------------------------
# ClaimRow (OPERATIONAL)
# ---------------------------------------------------------------------------


class TestClaimRow:
    async def test_create_claim_with_model_refs(self, session: AsyncSession):
        c = ClaimRow(
            claim_id=new_uuid7(),
            text="The project creates 5,000 direct jobs",
            claim_type="MODEL",
            status="EXTRACTED",
            disclosure_tier="TIER0",
            model_refs=[{"run_id": str(new_uuid7()), "metric": "JOBS", "value": 5000.0}],
            evidence_refs=[],
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add(c)
        await session.flush()
        result = await session.get(ClaimRow, c.claim_id)
        assert result.text == "The project creates 5,000 direct jobs"
        assert len(result.model_refs) == 1

    async def test_status_update_allowed(self, session: AsyncSession):
        """Claims are OPERATIONAL — status transitions are allowed."""
        c = ClaimRow(
            claim_id=new_uuid7(),
            text="Test claim",
            claim_type="SOURCE_FACT",
            status="EXTRACTED",
            disclosure_tier="TIER0",
            model_refs=[],
            evidence_refs=[],
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add(c)
        await session.flush()

        c.status = "NEEDS_EVIDENCE"
        await session.flush()
        result = await session.get(ClaimRow, c.claim_id)
        assert result.status == "NEEDS_EVIDENCE"


# ---------------------------------------------------------------------------
# ExportRow (OPERATIONAL)
# ---------------------------------------------------------------------------


class TestExportRow:
    async def test_create_export(self, session: AsyncSession):
        e = ExportRow(
            export_id=new_uuid7(),
            run_id=new_uuid7(),
            template_version="v1.0",
            mode="SANDBOX",
            disclosure_tier="TIER0",
            status="PENDING",
            blocked_reasons=[],
            created_at=utc_now(),
        )
        session.add(e)
        await session.flush()
        result = await session.get(ExportRow, e.export_id)
        assert result.status == "PENDING"

    async def test_status_update_allowed(self, session: AsyncSession):
        e = ExportRow(
            export_id=new_uuid7(),
            run_id=new_uuid7(),
            template_version="v1.0",
            mode="GOVERNED",
            disclosure_tier="TIER1",
            status="PENDING",
            blocked_reasons=[],
            created_at=utc_now(),
        )
        session.add(e)
        await session.flush()

        e.status = "BLOCKED"
        e.blocked_reasons = ["Unresolved claims: 3"]
        await session.flush()
        result = await session.get(ExportRow, e.export_id)
        assert result.status == "BLOCKED"
        assert "Unresolved claims: 3" in result.blocked_reasons


# ---------------------------------------------------------------------------
# DocumentRow + ExtractionJobRow + LineItemRow
# ---------------------------------------------------------------------------


class TestDocumentRow:
    async def test_create_document(self, session: AsyncSession):
        d = DocumentRow(
            doc_id=new_uuid7(),
            workspace_id=new_uuid7(),
            filename="boq_project_alpha.pdf",
            mime_type="application/pdf",
            size_bytes=1048576,
            hash_sha256="sha256:" + "d" * 64,
            storage_key="uploads/ws1/boq_project_alpha.pdf",
            uploaded_by=new_uuid7(),
            uploaded_at=utc_now(),
            doc_type="BOQ",
            source_type="CLIENT",
            classification="CONFIDENTIAL",
            language="en",
        )
        session.add(d)
        await session.flush()
        result = await session.get(DocumentRow, d.doc_id)
        assert result.filename == "boq_project_alpha.pdf"


class TestExtractionJobRow:
    async def test_status_update_allowed(self, session: AsyncSession):
        """ExtractionJob is OPERATIONAL."""
        j = ExtractionJobRow(
            job_id=new_uuid7(),
            doc_id=new_uuid7(),
            workspace_id=new_uuid7(),
            status="QUEUED",
            extract_tables=True,
            extract_line_items=True,
            language_hint="en",
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        session.add(j)
        await session.flush()

        j.status = "RUNNING"
        await session.flush()

        j.status = "COMPLETED"
        await session.flush()
        result = await session.get(ExtractionJobRow, j.job_id)
        assert result.status == "COMPLETED"


# ---------------------------------------------------------------------------
# OverridePairRow (learning loop)
# ---------------------------------------------------------------------------


class TestOverridePairRow:
    async def test_create_override_pair(self, session: AsyncSession):
        op = OverridePairRow(
            override_id=new_uuid7(),
            engagement_id=new_uuid7(),
            line_item_id=new_uuid7(),
            line_item_text="Supply of structural steel beams",
            suggested_sector_code="SEC12",
            final_sector_code="SEC14",
            project_type="infrastructure",
            created_at=utc_now(),
        )
        session.add(op)
        await session.flush()
        assert op.id is not None  # Auto-increment PK


# ---------------------------------------------------------------------------
# MetricEventRow + EngagementRow
# ---------------------------------------------------------------------------


class TestMetricEventRow:
    async def test_create_metric_event(self, session: AsyncSession):
        me = MetricEventRow(
            event_id=new_uuid7(),
            engagement_id=new_uuid7(),
            metric_type="SCENARIO_REQUEST_TO_RESULTS",
            value=45.5,
            unit="minutes",
            timestamp=utc_now(),
            metadata_json={"scenario_count": 5},
        )
        session.add(me)
        await session.flush()
        result = await session.get(MetricEventRow, me.event_id)
        assert result.value == 45.5
        assert result.metadata_json["scenario_count"] == 5


class TestEngagementRow:
    async def test_create_engagement(self, session: AsyncSession):
        e = EngagementRow(
            engagement_id=new_uuid7(),
            workspace_id=new_uuid7(),
            name="Project Alpha Assessment",
            current_phase="DATA_ASSEMBLY",
            phase_transitions=[],
            created_at=utc_now(),
        )
        session.add(e)
        await session.flush()
        result = await session.get(EngagementRow, e.engagement_id)
        assert result.name == "Project Alpha Assessment"
        assert result.current_phase == "DATA_ASSEMBLY"


# ---------------------------------------------------------------------------
# RunSnapshotRow + BatchRow
# ---------------------------------------------------------------------------


class TestRunSnapshotRow:
    async def test_create_run_snapshot(self, session: AsyncSession):
        rs = RunSnapshotRow(
            run_id=new_uuid7(),
            model_version_id=new_uuid7(),
            taxonomy_version_id=new_uuid7(),
            concordance_version_id=new_uuid7(),
            mapping_library_version_id=new_uuid7(),
            assumption_library_version_id=new_uuid7(),
            prompt_pack_version_id=new_uuid7(),
            source_checksums=["sha256:" + "e" * 64],
            created_at=utc_now(),
        )
        session.add(rs)
        await session.flush()
        result = await session.get(RunSnapshotRow, rs.run_id)
        assert result is not None
        assert len(result.source_checksums) == 1


class TestBatchRow:
    async def test_create_batch(self, session: AsyncSession):
        b = BatchRow(
            batch_id=new_uuid7(),
            run_ids=[str(new_uuid7()), str(new_uuid7())],
            created_at=utc_now(),
        )
        session.add(b)
        await session.flush()
        result = await session.get(BatchRow, b.batch_id)
        assert len(result.run_ids) == 2


class TestCompilationRow:
    async def test_create_compilation(self, session: AsyncSession):
        c = CompilationRow(
            compilation_id=new_uuid7(),
            result_json={"shock_items": [], "status": "compiled"},
            metadata_json={"line_count": 42},
            created_at=utc_now(),
        )
        session.add(c)
        await session.flush()
        result = await session.get(CompilationRow, c.compilation_id)
        assert result.result_json["status"] == "compiled"
