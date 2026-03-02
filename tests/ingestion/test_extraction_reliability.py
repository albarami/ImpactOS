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
        assert resp.status_code == 200
        assert resp.json()["items"] == []

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
        assert job.attempt_count == 1
        await repo.increment_attempt(job.job_id)
        row = await repo.get(job.job_id)
        assert row is not None
        assert row.attempt_count == 2

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
    async def test_default_attempt_count_is_1(self, db_session):
        repo = ExtractionJobRepository(db_session)
        doc_id = await _seed_doc(db_session)
        job = await repo.create(
            job_id=uuid7(), doc_id=doc_id, workspace_id=WS_A,
        )
        assert job.attempt_count == 1

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
