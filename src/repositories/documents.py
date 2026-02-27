"""Document, extraction job, and line item repositories."""

from uuid import UUID

from sqlalchemy import select
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


class ExtractionJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, job_id: UUID, doc_id: UUID, workspace_id: UUID,
                     status: str = "QUEUED", extract_tables: bool = True,
                     extract_line_items: bool = True,
                     language_hint: str = "en",
                     error_message: str | None = None) -> ExtractionJobRow:
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

    async def update_status(self, job_id: UUID, status: str,
                            error_message: str | None = None) -> ExtractionJobRow | None:
        row = await self.get(job_id)
        if row is not None:
            row.status = status
            row.error_message = error_message
            row.updated_at = utc_now()
            await self._session.flush()
        return row


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

    async def get_by_doc(self, doc_id: UUID) -> list[LineItemRow]:
        result = await self._session.execute(
            select(LineItemRow).where(LineItemRow.doc_id == doc_id)
        )
        return list(result.scalars().all())
