"""Sprint 8: Extraction reliability tests.

TDD for workspace ownership, failure metadata, idempotent persistence,
and lifecycle transitions.
"""

import pytest
from uuid_extensions import uuid7

from src.db.tables import DocumentRow
from src.models.common import utc_now
from src.repositories.documents import (
    ExtractionJobRepository,
    LineItemRepository,
)

WS_A = uuid7()
WS_B = uuid7()


async def _seed_doc(db_session, *, workspace_id=WS_A):
    doc_id = uuid7()
    row = DocumentRow(
        doc_id=doc_id, workspace_id=workspace_id,
        filename="test.pdf", mime_type="application/pdf",
        size_bytes=100, hash_sha256="sha256:abc",
        storage_key=f"{workspace_id}/{doc_id}/test.pdf",
        uploaded_by=uuid7(), uploaded_at=utc_now(),
        doc_type="BOQ", source_type="UPLOAD",
        classification="INTERNAL", language="en",
    )
    db_session.add(row)
    await db_session.flush()
    return doc_id


async def _seed_job(db_session, *, doc_id, workspace_id=WS_A):
    repo = ExtractionJobRepository(db_session)
    return await repo.create(
        job_id=uuid7(), doc_id=doc_id, workspace_id=workspace_id,
    )


async def _seed_line_items(db_session, *, doc_id, job_id, count=3):
    items = []
    for _ in range(count):
        items.append({
            "line_item_id": uuid7(),
            "doc_id": doc_id,
            "extraction_job_id": job_id,
            "raw_text": "test item",
            "description": "test",
            "total_value": 100.0,
            "currency_code": "SAR",
            "page_ref": 1,
            "evidence_snippet_ids": [],
            "created_at": utc_now(),
        })
    repo = LineItemRepository(db_session)
    return await repo.create_many(items)


class TestWorkspaceOwnership:
    """S8-1: Extract/job/line-items enforce workspace."""

    @pytest.mark.anyio
    async def test_extract_wrong_workspace_404(self, client, db_session):
        doc_id = await _seed_doc(db_session, workspace_id=WS_B)
        resp = await client.post(
            f"/v1/workspaces/{WS_A}/documents/{doc_id}/extract",
            json={"extract_tables": True, "extract_line_items": True},
        )
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_job_status_wrong_workspace_404(self, client, db_session):
        doc_id = await _seed_doc(db_session, workspace_id=WS_B)
        job = await _seed_job(db_session, doc_id=doc_id, workspace_id=WS_B)
        resp = await client.get(
            f"/v1/workspaces/{WS_A}/jobs/{job.job_id}",
        )
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_line_items_wrong_workspace_404(self, client, db_session):
        doc_id = await _seed_doc(db_session, workspace_id=WS_B)
        resp = await client.get(
            f"/v1/workspaces/{WS_A}/documents/{doc_id}/line-items",
        )
        assert resp.status_code == 404

    @pytest.mark.anyio
    async def test_job_status_correct_workspace_200(
        self, client, db_session,
    ):
        doc_id = await _seed_doc(db_session, workspace_id=WS_A)
        job = await _seed_job(
            db_session, doc_id=doc_id, workspace_id=WS_A,
        )
        resp = await client.get(
            f"/v1/workspaces/{WS_A}/jobs/{job.job_id}",
        )
        assert resp.status_code == 200


class TestFailureMetadata:
    """S8-2: Deterministic failure metadata on job row."""

    @pytest.mark.anyio
    async def test_update_status_with_error_code(self, db_session):
        repo = ExtractionJobRepository(db_session)
        doc_id = await _seed_doc(db_session)
        job = await repo.create(
            job_id=uuid7(), doc_id=doc_id, workspace_id=WS_A,
        )
        await repo.update_status(
            job.job_id, "FAILED",
            error_message="Provider timeout",
            error_code="PROVIDER_TIMEOUT",
            provider_name="azure-di",
        )
        row = await repo.get(job.job_id)
        assert row is not None
        assert row.status == "FAILED"
        assert row.error_code == "PROVIDER_TIMEOUT"
        assert row.provider_name == "azure-di"

    @pytest.mark.anyio
    async def test_fallback_provider_recorded(self, db_session):
        repo = ExtractionJobRepository(db_session)
        doc_id = await _seed_doc(db_session)
        job = await repo.create(
            job_id=uuid7(), doc_id=doc_id, workspace_id=WS_A,
        )
        await repo.update_status(
            job.job_id, "COMPLETED",
            provider_name="azure-di",
            fallback_provider_name="local-pdf",
        )
        row = await repo.get(job.job_id)
        assert row is not None
        assert row.provider_name == "azure-di"
        assert row.fallback_provider_name == "local-pdf"

    @pytest.mark.anyio
    async def test_attempt_count_increments(self, db_session):
        repo = ExtractionJobRepository(db_session)
        doc_id = await _seed_doc(db_session)
        job = await repo.create(
            job_id=uuid7(), doc_id=doc_id, workspace_id=WS_A,
        )
        assert job.attempt_count == 0
        await repo.increment_attempt(job.job_id)
        row = await repo.get(job.job_id)
        assert row is not None
        assert row.attempt_count == 1

    @pytest.mark.anyio
    async def test_lifecycle_timestamps(self, db_session):
        repo = ExtractionJobRepository(db_session)
        doc_id = await _seed_doc(db_session)
        job = await repo.create(
            job_id=uuid7(), doc_id=doc_id, workspace_id=WS_A,
        )
        assert job.started_at is None
        assert job.completed_at is None

        await repo.update_status(job.job_id, "RUNNING")
        row = await repo.get(job.job_id)
        assert row.started_at is not None
        assert row.completed_at is None

        await repo.update_status(job.job_id, "COMPLETED")
        row = await repo.get(job.job_id)
        assert row.completed_at is not None


class TestIdempotentPersistence:
    """S8-3: Retries must not duplicate artifacts."""

    @pytest.mark.anyio
    async def test_delete_by_job_clears_line_items(self, db_session):
        li_repo = LineItemRepository(db_session)
        doc_id = await _seed_doc(db_session)
        job_id = uuid7()
        await _seed_line_items(
            db_session, doc_id=doc_id, job_id=job_id, count=5,
        )
        items = await li_repo.get_by_extraction_job(job_id)
        assert len(items) == 5

        deleted = await li_repo.delete_by_job(job_id)
        assert deleted == 5

        items_after = await li_repo.get_by_extraction_job(job_id)
        assert len(items_after) == 0

    @pytest.mark.anyio
    async def test_retry_with_delete_produces_no_duplicates(
        self, db_session,
    ):
        li_repo = LineItemRepository(db_session)
        doc_id = await _seed_doc(db_session)
        job_id = uuid7()

        await _seed_line_items(
            db_session, doc_id=doc_id, job_id=job_id, count=3,
        )
        await li_repo.delete_by_job(job_id)
        await _seed_line_items(
            db_session, doc_id=doc_id, job_id=job_id, count=4,
        )

        items = await li_repo.get_by_extraction_job(job_id)
        assert len(items) == 4


class TestMigrationBackwardCompat:
    """Migration 009: new columns have defaults, existing rows work."""

    @pytest.mark.anyio
    async def test_default_attempt_count_is_0(self, db_session):
        repo = ExtractionJobRepository(db_session)
        doc_id = await _seed_doc(db_session)
        job = await repo.create(
            job_id=uuid7(), doc_id=doc_id, workspace_id=WS_A,
        )
        assert job.attempt_count == 0

    @pytest.mark.anyio
    async def test_new_columns_nullable(self, db_session):
        repo = ExtractionJobRepository(db_session)
        doc_id = await _seed_doc(db_session)
        job = await repo.create(
            job_id=uuid7(), doc_id=doc_id, workspace_id=WS_A,
        )
        assert job.error_code is None
        assert job.provider_name is None
        assert job.fallback_provider_name is None
        assert job.started_at is None
        assert job.completed_at is None


class TestSyncAsyncParity:
    """S8-4: run_extraction produces same side effects in both paths."""

    @pytest.mark.anyio
    async def test_sync_path_persists_provider_and_status(
        self, db_session,
    ):
        """Sync run_extraction must set provider_name and terminal status."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from src.ingestion.tasks import run_extraction

        doc_id = await _seed_doc(db_session)
        job_repo = ExtractionJobRepository(db_session)
        li_repo = LineItemRepository(db_session)
        job = await job_repo.create(
            job_id=uuid7(), doc_id=doc_id, workspace_id=WS_A,
        )

        mock_graph = MagicMock()
        mock_graph.pages = []
        mock_graph.tables = []

        mock_provider = AsyncMock()
        mock_provider.name = "test-provider"
        mock_provider.extract = AsyncMock(return_value=mock_graph)

        with patch(
            "src.ingestion.tasks.ExtractionRouter"
        ) as mock_router_cls:
            mock_router_cls.return_value.select_provider.return_value = (
                mock_provider
            )
            status = await run_extraction(
                job_id=job.job_id,
                doc_id=doc_id,
                workspace_id=WS_A,
                document_bytes=b"fake",
                mime_type="application/pdf",
                filename="test.pdf",
                classification="INTERNAL",
                doc_checksum="sha256:test",
                job_repo=job_repo,
                line_item_repo=li_repo,
                evidence_snippet_repo=None,
            )

        assert status == "COMPLETED"
        row = await job_repo.get(job.job_id)
        assert row is not None
        assert row.status == "COMPLETED"
        assert row.provider_name == "test-provider"
        assert row.completed_at is not None

    @pytest.mark.anyio
    async def test_successful_run_does_not_increment_attempt(
        self, db_session,
    ):
        """Successful run_extraction keeps attempt_count at 0."""
        from unittest.mock import AsyncMock, MagicMock, patch

        from src.ingestion.tasks import run_extraction

        doc_id = await _seed_doc(db_session)
        job_repo = ExtractionJobRepository(db_session)
        li_repo = LineItemRepository(db_session)
        job = await job_repo.create(
            job_id=uuid7(), doc_id=doc_id, workspace_id=WS_A,
        )
        assert job.attempt_count == 0

        mock_graph = MagicMock()
        mock_graph.pages = []
        mock_graph.tables = []

        mock_provider = AsyncMock()
        mock_provider.name = "test-provider"
        mock_provider.extract = AsyncMock(return_value=mock_graph)

        with patch(
            "src.ingestion.tasks.ExtractionRouter",
        ) as mock_router_cls:
            mock_router_cls.return_value.select_provider.return_value = (
                mock_provider
            )
            status = await run_extraction(
                job_id=job.job_id,
                doc_id=doc_id,
                workspace_id=WS_A,
                document_bytes=b"fake",
                mime_type="application/pdf",
                filename="test.pdf",
                classification="INTERNAL",
                doc_checksum="sha256:test",
                job_repo=job_repo,
                line_item_repo=li_repo,
                evidence_snippet_repo=None,
            )

        assert status == "COMPLETED"
        row = await job_repo.get(job.job_id)
        assert row is not None
        assert row.attempt_count == 0

    @pytest.mark.anyio
    async def test_failed_run_increments_attempt_and_reraises(
        self, db_session,
    ):
        """Failed run_extraction increments attempt_count and re-raises."""
        from unittest.mock import AsyncMock, patch

        import pytest as pt

        from src.ingestion.tasks import run_extraction

        doc_id = await _seed_doc(db_session)
        job_repo = ExtractionJobRepository(db_session)
        job = await job_repo.create(
            job_id=uuid7(), doc_id=doc_id, workspace_id=WS_A,
        )

        mock_provider = AsyncMock()
        mock_provider.name = "local-pdf"
        mock_provider.extract = AsyncMock(
            side_effect=RuntimeError("crash"),
        )

        with patch(
            "src.ingestion.tasks.ExtractionRouter",
        ) as mock_router_cls:
            mock_router_cls.return_value.select_provider.return_value = (
                mock_provider
            )
            with pt.raises(RuntimeError, match="crash"):
                await run_extraction(
                    job_id=job.job_id,
                    doc_id=doc_id,
                    workspace_id=WS_A,
                    document_bytes=b"fake",
                    mime_type="application/pdf",
                    filename="test.pdf",
                    classification="INTERNAL",
                    doc_checksum="sha256:test",
                    job_repo=job_repo,
                    line_item_repo=None,
                    evidence_snippet_repo=None,
                )

        row = await job_repo.get(job.job_id)
        assert row is not None
        assert row.status == "FAILED"
        assert row.attempt_count == 1
        assert row.error_code == "RuntimeError"

    @pytest.mark.anyio
    async def test_run_extraction_failure_records_error_code(
        self, db_session,
    ):
        """Failed extraction records error_code and re-raises."""
        from unittest.mock import AsyncMock, patch

        import pytest as pt

        from src.ingestion.tasks import run_extraction

        doc_id = await _seed_doc(db_session)
        job_repo = ExtractionJobRepository(db_session)
        job = await job_repo.create(
            job_id=uuid7(), doc_id=doc_id, workspace_id=WS_A,
        )

        mock_provider = AsyncMock()
        mock_provider.name = "local-pdf"
        mock_provider.extract = AsyncMock(
            side_effect=RuntimeError("provider crash"),
        )

        with patch(
            "src.ingestion.tasks.ExtractionRouter",
        ) as mock_router_cls:
            mock_router_cls.return_value.select_provider.return_value = (
                mock_provider
            )
            with pt.raises(RuntimeError, match="provider crash"):
                await run_extraction(
                    job_id=job.job_id,
                    doc_id=doc_id,
                    workspace_id=WS_A,
                    document_bytes=b"fake",
                    mime_type="application/pdf",
                    filename="test.pdf",
                    classification="INTERNAL",
                    doc_checksum="sha256:test",
                    job_repo=job_repo,
                    line_item_repo=None,
                    evidence_snippet_repo=None,
                )

        row = await job_repo.get(job.job_id)
        assert row is not None
        assert row.error_code == "RuntimeError"
        assert row.provider_name == "local-pdf"


class TestEvidenceSnippetIdempotency:
    """S8.1-2: Evidence snippets must not duplicate on retry."""

    @pytest.mark.anyio
    async def test_delete_by_source_clears_snippets(self, db_session):
        from src.db.tables import EvidenceSnippetRow
        from src.repositories.governance import EvidenceSnippetRepository

        repo = EvidenceSnippetRepository(db_session)
        source_id = uuid7()
        now = utc_now()

        for i in range(3):
            db_session.add(EvidenceSnippetRow(
                snippet_id=uuid7(),
                source_id=source_id,
                page=i,
                bbox_x0=0.0, bbox_y0=0.0, bbox_x1=1.0, bbox_y1=1.0,
                extracted_text=f"text {i}",
                checksum=f"sha256:{'a' * 64}",
                created_at=now,
            ))
        await db_session.flush()

        deleted = await repo.delete_by_source(source_id)
        assert deleted == 3

    @pytest.mark.anyio
    async def test_retry_does_not_duplicate_snippets(self, db_session):
        """Calling delete_by_source + create_many twice = no duplicates."""
        from src.db.tables import EvidenceSnippetRow
        from src.repositories.governance import EvidenceSnippetRepository

        repo = EvidenceSnippetRepository(db_session)
        source_id = uuid7()
        now = utc_now()

        def _make_snippets(n):
            return [
                {
                    "snippet_id": uuid7(),
                    "source_id": source_id,
                    "page": i,
                    "bbox_x0": 0.0, "bbox_y0": 0.0,
                    "bbox_x1": 1.0, "bbox_y1": 1.0,
                    "extracted_text": f"text {i}",
                    "checksum": f"sha256:{'b' * 64}",
                    "created_at": now,
                }
                for i in range(n)
            ]

        await repo.delete_by_source(source_id)
        await repo.create_many(_make_snippets(3))

        await repo.delete_by_source(source_id)
        await repo.create_many(_make_snippets(4))

        from sqlalchemy import func, select
        count = await db_session.execute(
            select(func.count()).where(
                EvidenceSnippetRow.source_id == source_id,
            )
        )
        assert count.scalar_one() == 4
