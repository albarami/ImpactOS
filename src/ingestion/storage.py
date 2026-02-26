"""Document storage service — MVP-2 Section 8.1.

Handles file upload to local (dev) or S3-compatible (prod) object storage,
SHA-256 checksum computation, and Document model creation.

This is a deterministic service — no LLM calls.
"""

import hashlib
from pathlib import Path
from uuid import UUID

from src.models.common import DataClassification
from src.models.document import (
    Document,
    DocumentType,
    LanguageCode,
    SourceType,
    new_uuid7,
)


class DocumentStorageService:
    """Local filesystem-backed document storage.

    In production this would be replaced with an S3-compatible backend,
    but the interface (upload/retrieve) remains the same.
    """

    def __init__(self, storage_root: str) -> None:
        self._root = Path(storage_root)
        self._root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _compute_sha256(content: bytes) -> str:
        """Compute SHA-256 and return in canonical 'sha256:<hex>' format."""
        digest = hashlib.sha256(content).hexdigest()
        return f"sha256:{digest}"

    def upload(
        self,
        *,
        workspace_id: UUID,
        filename: str,
        content: bytes,
        mime_type: str,
        uploaded_by: UUID,
        doc_type: DocumentType,
        source_type: SourceType,
        classification: DataClassification,
        language: LanguageCode = LanguageCode.EN,
    ) -> Document:
        """Store document content and return a Document with metadata.

        Args:
            workspace_id: Owning workspace.
            filename: Original filename.
            content: Raw file bytes (must be non-empty).
            mime_type: MIME type string.
            uploaded_by: User ID performing the upload.
            doc_type: Document classification (BOQ, CAPEX, etc.).
            source_type: Provenance (CLIENT, PUBLIC, INTERNAL).
            classification: Data sensitivity tier.
            language: Document language (default EN).

        Returns:
            A fully populated Document model.

        Raises:
            ValueError: If content is empty.
        """
        if len(content) == 0:
            msg = "Document content must not be empty."
            raise ValueError(msg)

        doc_id = new_uuid7()
        hash_sha256 = self._compute_sha256(content)

        # Build storage key: workspace_id/doc_id/filename
        storage_key = f"{workspace_id}/{doc_id}/{filename}"

        # Write to disk
        dest = self._root / storage_key
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)

        return Document(
            doc_id=doc_id,
            workspace_id=workspace_id,
            filename=filename,
            mime_type=mime_type,
            size_bytes=len(content),
            hash_sha256=hash_sha256,
            storage_key=storage_key,
            uploaded_by=uploaded_by,
            doc_type=doc_type,
            source_type=source_type,
            classification=classification,
            language=language,
        )

    def retrieve(self, storage_key: str) -> bytes:
        """Read stored document bytes by storage key.

        Raises:
            FileNotFoundError: If the storage key does not exist.
        """
        path = self._root / storage_key
        if not path.exists():
            msg = f"Document not found at storage key: {storage_key}"
            raise FileNotFoundError(msg)
        return path.read_bytes()
