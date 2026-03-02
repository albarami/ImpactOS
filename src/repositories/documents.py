"""Document, extraction job, and line item repositories."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.tables import DocumentRow, ExtractionJobRow, LineItemRow
from src.models.common import utc_now


class DocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, doc_id: UUID, workspace_id: UUID, filename: str,
                     mime_type: str, size_bytes: int, hash_sha256: str,
                     storage_key: str, uploaded_by: UUID, doc_type: str,
                     source_type: str, classification: str, language: str = "en") -> DocumentRow:
        now = utc_now()
        row = DocumentRow(
            doc_id=doc_id, workspace_id=workspace_id, filename=filename,
            mime_type=mime_type, size_bytes=size_bytes, hash_sha256=hash_sha256,
            storage_key=storage_key, uploaded_by=uploaded_by, uploaded_at=now,
            doc_type=doc_type, source_type=source_type,
            classification=classification, language=language,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self, doc_id: UUID) -> DocumentRow | None:
        return await self._session.get(DocumentRow, doc_id)

    async def list_by_workspace(self, workspace_id: UUID) -> list[DocumentRow]:
        result = await self._session.execute(
            select(DocumentRow).where(DocumentRow.workspace_id == workspace_id)
        )
        return list(result.scalars().all())

    async def list_by_workspace_paginated(
        self,
        workspace_id: UUID,
        *,
        limit: int = 20,
        cursor_uploaded_at: str | None = None,
        cursor_doc_id: str | None = None,
    ) -> tuple[list[DocumentRow], int]:
        """Paginated document list for a workspace.

        Returns (rows, total_count). Cursor-based on (uploaded_at, doc_id).
        """
        base = select(DocumentRow).where(
            DocumentRow.workspace_id == workspace_id,
        )

        # Total count (unfiltered by cursor)
        count_result = await self._session.execute(
            select(func.count()).select_from(
                base.subquery(),
            )
        )
        total = count_result.scalar_one()

        # Apply cursor filter
        query = base.order_by(
            DocumentRow.uploaded_at.asc(), DocumentRow.doc_id.asc(),
        )
        if cursor_uploaded_at is not None and cursor_doc_id is not None:
            from datetime import datetime
            ts = datetime.fromisoformat(cursor_uploaded_at)
            cid = UUID(cursor_doc_id)
            query = query.where(
                (DocumentRow.uploaded_at > ts)
                | (
                    (DocumentRow.uploaded_at == ts)
                    & (DocumentRow.doc_id > cid)
                ),
            )

        query = query.limit(limit)
        result = await self._session.execute(query)
        return list(result.scalars().all()), total

    async def get_by_workspace(
        self, workspace_id: UUID, doc_id: UUID,
    ) -> DocumentRow | None:
        """Get a document only if it belongs to the given workspace."""
        result = await self._session.execute(
            select(DocumentRow).where(
                DocumentRow.doc_id == doc_id,
                DocumentRow.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none()


class ExtractionJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, *, job_id: UUID, doc_id: UUID, workspace_id: UUID,
        status: str = "QUEUED", extract_tables: bool = True,
        extract_line_items: bool = True, language_hint: str = "en",
        error_message: str | None = None,
    ) -> ExtractionJobRow:
        now = utc_now()
        row = ExtractionJobRow(
            job_id=job_id, doc_id=doc_id, workspace_id=workspace_id,
            status=status, extract_tables=extract_tables,
            extract_line_items=extract_line_items,
            language_hint=language_hint,
            error_message=error_message,
            created_at=now, updated_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self, job_id: UUID) -> ExtractionJobRow | None:
        return await self._session.get(ExtractionJobRow, job_id)

    async def get_for_workspace(
        self, job_id: UUID, workspace_id: UUID,
    ) -> ExtractionJobRow | None:
        """Get job only if it belongs to the given workspace."""
        result = await self._session.execute(
            select(ExtractionJobRow).where(
                ExtractionJobRow.job_id == job_id,
                ExtractionJobRow.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none()

    async def update_status(
        self, job_id: UUID, status: str, *,
        error_message: str | None = None,
        error_code: str | None = None,
        provider_name: str | None = None,
        fallback_provider_name: str | None = None,
    ) -> ExtractionJobRow | None:
        row = await self.get(job_id)
        if row is not None:
            now = utc_now()
            row.status = status
            row.error_message = error_message
            row.updated_at = now
            if error_code is not None:
                row.error_code = error_code
            if provider_name is not None:
                row.provider_name = provider_name
            if fallback_provider_name is not None:
                row.fallback_provider_name = fallback_provider_name
            if status == "RUNNING":
                row.started_at = now
            if status in ("COMPLETED", "FAILED"):
                row.completed_at = now
            await self._session.flush()
        return row

    async def increment_attempt(self, job_id: UUID) -> None:
        """Increment attempt_count for retries."""
        row = await self.get(job_id)
        if row is not None:
            row.attempt_count = (row.attempt_count or 0) + 1
            row.updated_at = utc_now()
            await self._session.flush()

    async def get_latest_completed(
        self, doc_id: UUID,
    ) -> ExtractionJobRow | None:
        result = await self._session.execute(
            select(ExtractionJobRow)
            .where(ExtractionJobRow.doc_id == doc_id)
            .where(ExtractionJobRow.status == "COMPLETED")
            .order_by(ExtractionJobRow.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_latest_by_doc(
        self, doc_id: UUID,
    ) -> ExtractionJobRow | None:
        result = await self._session.execute(
            select(ExtractionJobRow)
            .where(ExtractionJobRow.doc_id == doc_id)
            .order_by(ExtractionJobRow.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


class LineItemRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_many(self, items: list[dict]) -> list[LineItemRow]:
        rows = []
        for item in items:
            row = LineItemRow(**item)
            self._session.add(row)
            rows.append(row)
        await self._session.flush()
        return rows

    async def delete_by_job(self, job_id: UUID) -> int:
        """Delete all line items for a job (idempotent retry support)."""
        from sqlalchemy import delete
        result = await self._session.execute(
            delete(LineItemRow).where(
                LineItemRow.extraction_job_id == job_id,
            )
        )
        await self._session.flush()
        return result.rowcount  # type: ignore[return-value]

    async def get_by_doc(self, doc_id: UUID) -> list[LineItemRow]:
        result = await self._session.execute(
            select(LineItemRow).where(LineItemRow.doc_id == doc_id)
        )
        return list(result.scalars().all())

    async def get_by_doc_for_workspace(
        self, doc_id: UUID, workspace_id: UUID,
    ) -> list[LineItemRow]:
        """Get line items only if the doc belongs to the workspace."""
        result = await self._session.execute(
            select(LineItemRow)
            .join(DocumentRow, LineItemRow.doc_id == DocumentRow.doc_id)
            .where(
                LineItemRow.doc_id == doc_id,
                DocumentRow.workspace_id == workspace_id,
            )
        )
        return list(result.scalars().all())

    async def get_by_extraction_job(
        self, job_id: UUID,
    ) -> list[LineItemRow]:
        result = await self._session.execute(
            select(LineItemRow).where(
                LineItemRow.extraction_job_id == job_id,
            )
        )
        return list(result.scalars().all())

    async def count_by_doc(self, doc_id: UUID) -> int:
        result = await self._session.execute(
            select(func.count()).where(LineItemRow.doc_id == doc_id)
        )
        return result.scalar_one()
