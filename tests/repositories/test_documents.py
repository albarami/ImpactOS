"""Tests for Document, ExtractionJob, and LineItem repositories."""

import pytest
from uuid_extensions import uuid7

from src.repositories.documents import (
    DocumentRepository,
    ExtractionJobRepository,
    LineItemRepository,
)
from src.models.common import utc_now


@pytest.fixture
def doc_repo(db_session):
    return DocumentRepository(db_session)


@pytest.fixture
def job_repo(db_session):
    return ExtractionJobRepository(db_session)


@pytest.fixture
def line_item_repo(db_session):
    return LineItemRepository(db_session)


class TestDocumentRepository:

    @pytest.mark.anyio
    async def test_create_and_get(self, doc_repo: DocumentRepository) -> None:
        did = uuid7()
        wid = uuid7()
        row = await doc_repo.create(
            doc_id=did, workspace_id=wid, filename="boq.csv",
            mime_type="text/csv", size_bytes=1024, hash_sha256="sha256:" + "a" * 64,
            storage_key="uploads/test.csv", uploaded_by=uuid7(),
            doc_type="BOQ", source_type="CLIENT", classification="RESTRICTED",
        )
        assert row.doc_id == did

        fetched = await doc_repo.get(did)
        assert fetched is not None
        assert fetched.filename == "boq.csv"

    @pytest.mark.anyio
    async def test_list_by_workspace(self, doc_repo: DocumentRepository) -> None:
        wid = uuid7()
        for _ in range(3):
            await doc_repo.create(
                doc_id=uuid7(), workspace_id=wid, filename="f.csv",
                mime_type="text/csv", size_bytes=100, hash_sha256="sha256:" + "b" * 64,
                storage_key="uploads/f.csv", uploaded_by=uuid7(),
                doc_type="BOQ", source_type="CLIENT", classification="RESTRICTED",
            )
        rows = await doc_repo.list_by_workspace(wid)
        assert len(rows) == 3


class TestExtractionJobRepository:

    @pytest.mark.anyio
    async def test_create_and_update(self, job_repo: ExtractionJobRepository) -> None:
        jid = uuid7()
        row = await job_repo.create(
            job_id=jid, doc_id=uuid7(), workspace_id=uuid7(), status="QUEUED",
        )
        assert row.status == "QUEUED"

        updated = await job_repo.update_status(jid, "COMPLETED")
        assert updated is not None
        assert updated.status == "COMPLETED"


class TestLineItemRepository:

    @pytest.mark.anyio
    async def test_create_many_and_get_by_doc(self, line_item_repo: LineItemRepository) -> None:
        did = uuid7()
        now = utc_now()
        items = [
            {
                "line_item_id": uuid7(), "doc_id": did, "extraction_job_id": uuid7(),
                "raw_text": "Steel", "description": "Structural Steel",
                "quantity": 5000.0, "unit": "tonnes", "unit_price": 3500.0,
                "total_value": 17500000.0, "currency_code": "SAR",
                "page_ref": 0, "evidence_snippet_ids": [str(uuid7())],
                "created_at": now,
            },
            {
                "line_item_id": uuid7(), "doc_id": did, "extraction_job_id": uuid7(),
                "raw_text": "Concrete", "description": "Concrete Works",
                "quantity": 20000.0, "unit": "m3", "unit_price": 450.0,
                "total_value": 9000000.0, "currency_code": "SAR",
                "page_ref": 0, "evidence_snippet_ids": [str(uuid7())],
                "created_at": now,
            },
        ]
        rows = await line_item_repo.create_many(items)
        assert len(rows) == 2

        fetched = await line_item_repo.get_by_doc(did)
        assert len(fetched) == 2
