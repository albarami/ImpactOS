"""Tests for document storage service (MVP-2 Section 8.1).

Covers: upload, SHA-256 checksum, Document creation, duplicate detection.
"""

import os
from pathlib import Path
from uuid import UUID

import pytest
from uuid_extensions import uuid7

from src.models.common import DataClassification
from src.models.document import (
    Document,
    DocumentType,
    LanguageCode,
    SourceType,
)
from src.ingestion.storage import DocumentStorageService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_storage(tmp_path: Path) -> DocumentStorageService:
    """Create a storage service backed by a temp directory."""
    return DocumentStorageService(storage_root=str(tmp_path))


@pytest.fixture
def sample_pdf_bytes() -> bytes:
    """Minimal PDF-like bytes for testing."""
    return b"%PDF-1.4 fake content for testing purposes " + os.urandom(256)


@pytest.fixture
def sample_xlsx_bytes() -> bytes:
    """Minimal XLSX-like bytes for testing."""
    return b"PK\x03\x04 fake xlsx " + os.urandom(256)


@pytest.fixture
def workspace_id() -> UUID:
    return uuid7()


@pytest.fixture
def user_id() -> UUID:
    return uuid7()


# ===================================================================
# Upload and checksum
# ===================================================================


class TestDocumentUpload:
    """Uploading a document stores it and returns a Document with SHA-256."""

    def test_upload_returns_document(
        self,
        tmp_storage: DocumentStorageService,
        sample_pdf_bytes: bytes,
        workspace_id: UUID,
        user_id: UUID,
    ) -> None:
        doc = tmp_storage.upload(
            workspace_id=workspace_id,
            filename="boq.pdf",
            content=sample_pdf_bytes,
            mime_type="application/pdf",
            uploaded_by=user_id,
            doc_type=DocumentType.BOQ,
            source_type=SourceType.CLIENT,
            classification=DataClassification.RESTRICTED,
            language=LanguageCode.EN,
        )
        assert isinstance(doc, Document)
        assert isinstance(doc.doc_id, UUID)

    def test_upload_computes_sha256(
        self,
        tmp_storage: DocumentStorageService,
        sample_pdf_bytes: bytes,
        workspace_id: UUID,
        user_id: UUID,
    ) -> None:
        doc = tmp_storage.upload(
            workspace_id=workspace_id,
            filename="boq.pdf",
            content=sample_pdf_bytes,
            mime_type="application/pdf",
            uploaded_by=user_id,
            doc_type=DocumentType.BOQ,
            source_type=SourceType.CLIENT,
            classification=DataClassification.RESTRICTED,
        )
        assert doc.hash_sha256.startswith("sha256:")
        assert len(doc.hash_sha256) == len("sha256:") + 64

    def test_upload_stores_file_on_disk(
        self,
        tmp_storage: DocumentStorageService,
        sample_pdf_bytes: bytes,
        workspace_id: UUID,
        user_id: UUID,
        tmp_path: Path,
    ) -> None:
        doc = tmp_storage.upload(
            workspace_id=workspace_id,
            filename="boq.pdf",
            content=sample_pdf_bytes,
            mime_type="application/pdf",
            uploaded_by=user_id,
            doc_type=DocumentType.BOQ,
            source_type=SourceType.CLIENT,
            classification=DataClassification.RESTRICTED,
        )
        stored_path = tmp_path / doc.storage_key
        assert stored_path.exists()
        assert stored_path.read_bytes() == sample_pdf_bytes

    def test_upload_records_size(
        self,
        tmp_storage: DocumentStorageService,
        sample_pdf_bytes: bytes,
        workspace_id: UUID,
        user_id: UUID,
    ) -> None:
        doc = tmp_storage.upload(
            workspace_id=workspace_id,
            filename="boq.pdf",
            content=sample_pdf_bytes,
            mime_type="application/pdf",
            uploaded_by=user_id,
            doc_type=DocumentType.BOQ,
            source_type=SourceType.CLIENT,
            classification=DataClassification.RESTRICTED,
        )
        assert doc.size_bytes == len(sample_pdf_bytes)

    def test_upload_sets_metadata(
        self,
        tmp_storage: DocumentStorageService,
        sample_pdf_bytes: bytes,
        workspace_id: UUID,
        user_id: UUID,
    ) -> None:
        doc = tmp_storage.upload(
            workspace_id=workspace_id,
            filename="budget_2025.xlsx",
            content=sample_pdf_bytes,
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            uploaded_by=user_id,
            doc_type=DocumentType.CAPEX,
            source_type=SourceType.PUBLIC,
            classification=DataClassification.INTERNAL,
            language=LanguageCode.AR,
        )
        assert doc.workspace_id == workspace_id
        assert doc.uploaded_by == user_id
        assert doc.doc_type == DocumentType.CAPEX
        assert doc.source_type == SourceType.PUBLIC
        assert doc.classification == DataClassification.INTERNAL
        assert doc.language == LanguageCode.AR
        assert doc.filename == "budget_2025.xlsx"

    def test_deterministic_checksum(
        self,
        tmp_storage: DocumentStorageService,
        workspace_id: UUID,
        user_id: UUID,
    ) -> None:
        """Same content always produces same checksum."""
        content = b"deterministic content"
        doc1 = tmp_storage.upload(
            workspace_id=workspace_id,
            filename="a.pdf",
            content=content,
            mime_type="application/pdf",
            uploaded_by=user_id,
            doc_type=DocumentType.BOQ,
            source_type=SourceType.CLIENT,
            classification=DataClassification.RESTRICTED,
        )
        doc2 = tmp_storage.upload(
            workspace_id=workspace_id,
            filename="b.pdf",
            content=content,
            mime_type="application/pdf",
            uploaded_by=user_id,
            doc_type=DocumentType.BOQ,
            source_type=SourceType.CLIENT,
            classification=DataClassification.RESTRICTED,
        )
        assert doc1.hash_sha256 == doc2.hash_sha256

    def test_different_content_different_checksum(
        self,
        tmp_storage: DocumentStorageService,
        workspace_id: UUID,
        user_id: UUID,
    ) -> None:
        doc1 = tmp_storage.upload(
            workspace_id=workspace_id,
            filename="a.pdf",
            content=b"content_A",
            mime_type="application/pdf",
            uploaded_by=user_id,
            doc_type=DocumentType.BOQ,
            source_type=SourceType.CLIENT,
            classification=DataClassification.RESTRICTED,
        )
        doc2 = tmp_storage.upload(
            workspace_id=workspace_id,
            filename="b.pdf",
            content=b"content_B",
            mime_type="application/pdf",
            uploaded_by=user_id,
            doc_type=DocumentType.BOQ,
            source_type=SourceType.CLIENT,
            classification=DataClassification.RESTRICTED,
        )
        assert doc1.hash_sha256 != doc2.hash_sha256

    def test_empty_content_rejected(
        self,
        tmp_storage: DocumentStorageService,
        workspace_id: UUID,
        user_id: UUID,
    ) -> None:
        with pytest.raises(ValueError, match="empty"):
            tmp_storage.upload(
                workspace_id=workspace_id,
                filename="empty.pdf",
                content=b"",
                mime_type="application/pdf",
                uploaded_by=user_id,
                doc_type=DocumentType.BOQ,
                source_type=SourceType.CLIENT,
                classification=DataClassification.RESTRICTED,
            )


# ===================================================================
# Retrieval
# ===================================================================


class TestDocumentRetrieval:
    """Retrieve stored document content."""

    def test_retrieve_returns_original_bytes(
        self,
        tmp_storage: DocumentStorageService,
        sample_pdf_bytes: bytes,
        workspace_id: UUID,
        user_id: UUID,
    ) -> None:
        doc = tmp_storage.upload(
            workspace_id=workspace_id,
            filename="boq.pdf",
            content=sample_pdf_bytes,
            mime_type="application/pdf",
            uploaded_by=user_id,
            doc_type=DocumentType.BOQ,
            source_type=SourceType.CLIENT,
            classification=DataClassification.RESTRICTED,
        )
        content = tmp_storage.retrieve(doc.storage_key)
        assert content == sample_pdf_bytes

    def test_retrieve_missing_raises(
        self,
        tmp_storage: DocumentStorageService,
    ) -> None:
        with pytest.raises(FileNotFoundError):
            tmp_storage.retrieve("nonexistent/path/file.pdf")
