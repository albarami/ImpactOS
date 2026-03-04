"""B-12: Tests for export artifact download endpoint.

TDD — these tests are written before the endpoint implementation.
Tests cover: success (excel/pptx), blocked/pending/generating exports (409),
wrong workspace (404), missing format (404), and bytes round-trip fidelity.
"""

import tempfile

import pytest
from uuid_extensions import uuid7

from src.api.dependencies import get_export_artifact_storage
from src.db.tables import ExportRow, RunQualitySummaryRow, RunSnapshotRow
from src.export.artifact_storage import ExportArtifactStorage
from src.models.common import new_uuid7, utc_now
from src.repositories.exports import ExportRepository

WS_ID = uuid7()
OTHER_WS_ID = uuid7()


@pytest.fixture
def _artifact_storage(client):
    """Override export artifact storage with a temp directory for tests."""
    from src.api.main import app

    tmpdir = tempfile.mkdtemp()
    store = ExportArtifactStorage(storage_root=tmpdir)
    app.dependency_overrides[get_export_artifact_storage] = lambda: store
    yield store
    app.dependency_overrides.pop(get_export_artifact_storage, None)


async def _seed_run_snapshot(db_session, *, run_id, workspace_id=WS_ID):
    """Create a minimal RunSnapshotRow + ModelVersionRow so provenance check passes."""
    from src.db.tables import ModelVersionRow
    mid = uuid7()
    mv = ModelVersionRow(
        model_version_id=mid, base_year=2023, source="test",
        sector_count=2, checksum="sha256:" + "a" * 64,
        provenance_class="curated_real", created_at=utc_now(),
    )
    db_session.add(mv)
    row = RunSnapshotRow(
        run_id=run_id,
        model_version_id=mid,
        taxonomy_version_id=uuid7(),
        concordance_version_id=uuid7(),
        mapping_library_version_id=uuid7(),
        assumption_library_version_id=uuid7(),
        prompt_pack_version_id=uuid7(),
        workspace_id=workspace_id,
        source_checksums=[],
        created_at=utc_now(),
    )
    db_session.add(row)
    await db_session.flush()
    return row


async def _seed_completed_export(
    db_session, *, workspace_id=WS_ID,
    artifact_refs=None, status="COMPLETED",
    artifact_store: ExportArtifactStorage | None = None,
):
    """Seed a run snapshot + export row with optional artifact refs.

    If artifact_store is provided, writes dummy bytes for each ref.
    """
    run_id = uuid7()
    export_id = uuid7()
    await _seed_run_snapshot(db_session, run_id=run_id, workspace_id=workspace_id)

    if artifact_refs and artifact_store:
        for fmt, key in artifact_refs.items():
            artifact_store.store(key, f"dummy-{fmt}-bytes".encode())

    row = ExportRow(
        export_id=export_id,
        run_id=run_id,
        template_version="v1.0",
        mode="SANDBOX",
        disclosure_tier="TIER0",
        status=status,
        checksums_json={"excel": "sha256:abc", "pptx": "sha256:def"},
        blocked_reasons=[],
        artifact_refs_json=artifact_refs,
        created_at=utc_now(),
    )
    db_session.add(row)
    await db_session.flush()
    return export_id, run_id


class TestExportDownload:
    """B-12: GET /v1/workspaces/{ws}/exports/{eid}/download/{format}."""

    @pytest.mark.anyio
    async def test_download_excel_success(self, client, db_session, _artifact_storage):
        artifact_refs = {
            "excel": "exports/test/excel.xlsx",
            "pptx": "exports/test/report.pptx",
        }
        export_id, _ = await _seed_completed_export(
            db_session, artifact_refs=artifact_refs,
            artifact_store=_artifact_storage,
        )

        resp = await client.get(
            f"/v1/workspaces/{WS_ID}/exports/{export_id}/download/excel"
        )
        assert resp.status_code == 200
        excel_mime = (
            "application/vnd.openxmlformats-officedocument"
            ".spreadsheetml.sheet"
        )
        assert resp.headers["content-type"] == excel_mime
        assert "content-disposition" in resp.headers
        assert "attachment" in resp.headers["content-disposition"]
        assert len(resp.content) > 0

    @pytest.mark.anyio
    async def test_download_pptx_success(self, client, db_session, _artifact_storage):
        artifact_refs = {
            "excel": "exports/test/excel.xlsx",
            "pptx": "exports/test/report.pptx",
        }
        export_id, _ = await _seed_completed_export(
            db_session, artifact_refs=artifact_refs,
            artifact_store=_artifact_storage,
        )

        resp = await client.get(
            f"/v1/workspaces/{WS_ID}/exports/{export_id}/download/pptx"
        )
        assert resp.status_code == 200
        pptx_mime = (
            "application/vnd.openxmlformats-officedocument"
            ".presentationml.presentation"
        )
        assert resp.headers["content-type"] == pptx_mime
        assert "attachment" in resp.headers["content-disposition"]

    @pytest.mark.anyio
    async def test_download_blocked_export_returns_409(self, client, db_session, _artifact_storage):
        export_id, _ = await _seed_completed_export(
            db_session, status="BLOCKED",
            artifact_refs={"excel": "x"},
        )
        resp = await client.get(
            f"/v1/workspaces/{WS_ID}/exports/{export_id}/download/excel"
        )
        assert resp.status_code == 409

    @pytest.mark.anyio
    async def test_download_pending_export_returns_409(self, client, db_session, _artifact_storage):
        export_id, _ = await _seed_completed_export(
            db_session, status="PENDING",
        )
        resp = await client.get(
            f"/v1/workspaces/{WS_ID}/exports/{export_id}/download/excel"
        )
        assert resp.status_code == 409

    @pytest.mark.anyio
    async def test_download_generating_export_returns_409(
        self, client, db_session, _artifact_storage,
    ):
        export_id, _ = await _seed_completed_export(
            db_session, status="GENERATING",
        )
        resp = await client.get(
            f"/v1/workspaces/{WS_ID}/exports/{export_id}/download/excel"
        )
        assert resp.status_code == 409

    @pytest.mark.anyio
    async def test_download_failed_export_returns_409(self, client, db_session, _artifact_storage):
        export_id, _ = await _seed_completed_export(
            db_session, status="FAILED",
        )
        resp = await client.get(
            f"/v1/workspaces/{WS_ID}/exports/{export_id}/download/excel"
        )
        assert resp.status_code == 409

    @pytest.mark.anyio
    async def test_download_wrong_workspace_returns_404(
        self, client, db_session, _artifact_storage,
    ):
        export_id, _ = await _seed_completed_export(
            db_session, workspace_id=OTHER_WS_ID,
            artifact_refs={"excel": "x"},
        )
        resp = await client.get(
            f"/v1/workspaces/{WS_ID}/exports/{export_id}/download/excel"
        )
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_download_missing_export_returns_404(self, client, _artifact_storage):
        fake_id = uuid7()
        resp = await client.get(
            f"/v1/workspaces/{WS_ID}/exports/{fake_id}/download/excel"
        )
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_download_missing_format_returns_404(self, client, db_session, _artifact_storage):
        export_id, _ = await _seed_completed_export(
            db_session, artifact_refs={"excel": "x"},
        )
        resp = await client.get(
            f"/v1/workspaces/{WS_ID}/exports/{export_id}/download/pptx"
        )
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_artifact_bytes_round_trip(self, client, db_session, _artifact_storage):
        """Persist artifact bytes at create-export, then download exact bytes."""
        run_id = uuid7()
        await _seed_run_snapshot(db_session, run_id=run_id, workspace_id=WS_ID)

        quality_row = RunQualitySummaryRow(
            summary_id=new_uuid7(),
            run_id=run_id,
            workspace_id=WS_ID,
            overall_run_score=0.8,
            overall_run_grade="B",
            coverage_pct=0.9,
            publication_gate_pass=True,
            publication_gate_mode="ADVISORY",
            payload={"assessment_version": 1, "used_synthetic_fallback": False, "data_mode": "curated_real"},
            created_at=utc_now(),
        )
        db_session.add(quality_row)
        await db_session.flush()

        payload = {
            "run_id": str(run_id),
            "mode": "SANDBOX",
            "export_formats": ["excel", "pptx"],
            "pack_data": {
                "run_id": str(run_id),
                "scenario_name": "RoundTrip",
                "base_year": 2023,
                "currency": "SAR",
                "model_version_id": str(uuid7()),
                "scenario_version": 1,
                "executive_summary": {"headline_gdp": 1e9, "headline_jobs": 5000},
                "sector_impacts": [{
                    "sector_code": "F",
                    "sector_name": "Construction",
                    "direct_impact": 100.0,
                    "indirect_impact": 50.0,
                    "total_impact": 150.0,
                    "multiplier": 1.5,
                    "domestic_share": 0.65,
                    "import_leakage": 0.35,
                }],
                "input_vectors": {"F": 200.0},
            },
        }

        create_resp = await client.post(
            f"/v1/workspaces/{WS_ID}/exports", json=payload,
        )
        assert create_resp.status_code == 201
        export_id = create_resp.json()["export_id"]

        dl_excel = await client.get(
            f"/v1/workspaces/{WS_ID}/exports/{export_id}/download/excel"
        )
        assert dl_excel.status_code == 200
        assert len(dl_excel.content) > 0

        dl_pptx = await client.get(
            f"/v1/workspaces/{WS_ID}/exports/{export_id}/download/pptx"
        )
        assert dl_pptx.status_code == 200
        assert len(dl_pptx.content) > 0


class TestExportStatusWorkspaceScope:
    """Export status endpoint workspace enforcement."""

    @pytest.mark.anyio
    async def test_status_correct_workspace_returns_200(self, client, db_session):
        export_id, _ = await _seed_completed_export(db_session, workspace_id=WS_ID)
        resp = await client.get(
            f"/v1/workspaces/{WS_ID}/exports/{export_id}"
        )
        assert resp.status_code == 200
        assert resp.json()["export_id"] == str(export_id)

    @pytest.mark.anyio
    async def test_status_wrong_workspace_returns_404(self, client, db_session):
        export_id, _ = await _seed_completed_export(
            db_session, workspace_id=OTHER_WS_ID,
        )
        resp = await client.get(
            f"/v1/workspaces/{WS_ID}/exports/{export_id}"
        )
        assert resp.status_code == 404


class TestExportRepoWorkspaceScope:
    """Repository-level tests for workspace-safe export access."""

    @pytest.mark.anyio
    async def test_get_for_workspace_returns_row(self, db_session):
        repo = ExportRepository(db_session)
        run_id = uuid7()
        await _seed_run_snapshot(db_session, run_id=run_id, workspace_id=WS_ID)

        row = await repo.create(
            export_id=uuid7(), run_id=run_id, mode="SANDBOX", status="COMPLETED",
        )
        fetched = await repo.get_for_workspace(row.export_id, WS_ID)
        assert fetched is not None
        assert fetched.export_id == row.export_id

    @pytest.mark.anyio
    async def test_get_for_workspace_wrong_ws_returns_none(self, db_session):
        repo = ExportRepository(db_session)
        run_id = uuid7()
        await _seed_run_snapshot(db_session, run_id=run_id, workspace_id=OTHER_WS_ID)

        row = await repo.create(
            export_id=uuid7(), run_id=run_id, mode="SANDBOX", status="COMPLETED",
        )
        fetched = await repo.get_for_workspace(row.export_id, WS_ID)
        assert fetched is None

    @pytest.mark.anyio
    async def test_set_artifact_refs(self, db_session):
        repo = ExportRepository(db_session)
        row = await repo.create(
            export_id=uuid7(), run_id=uuid7(), mode="SANDBOX", status="COMPLETED",
        )
        refs = {"excel": "exports/test.xlsx", "pptx": "exports/test.pptx"}
        updated = await repo.set_artifact_refs(row.export_id, refs)
        assert updated is not None
        assert updated.artifact_refs_json == refs
