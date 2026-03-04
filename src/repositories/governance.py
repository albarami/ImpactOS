"""Assumption, claim, and evidence snippet repositories."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.tables import (
    AssumptionLinkRow,
    AssumptionRow,
    ClaimRow,
    DocumentRow,
    EvidenceSnippetRow,
    RunSnapshotRow,
)
from src.models.common import utc_now


class AssumptionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, assumption_id: UUID, type: str, value: float,
                     units: str, justification: str,
                     evidence_refs: list | None = None,
                     range_json: dict | None = None,
                     status: str = "DRAFT",
                     workspace_id: UUID | None = None) -> AssumptionRow:
        now = utc_now()
        row = AssumptionRow(
            assumption_id=assumption_id, type=type, value=value,
            range_json=range_json, units=units, justification=justification,
            evidence_refs=evidence_refs or [], workspace_id=workspace_id,
            status=status, created_at=now, updated_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self, assumption_id: UUID) -> AssumptionRow | None:
        return await self._session.get(AssumptionRow, assumption_id)

    async def list_all(self) -> list[AssumptionRow]:
        result = await self._session.execute(select(AssumptionRow))
        return list(result.scalars().all())

    async def list_by_status(self, status: str) -> list[AssumptionRow]:
        result = await self._session.execute(
            select(AssumptionRow).where(AssumptionRow.status == status)
        )
        return list(result.scalars().all())

    async def approve(self, assumption_id: UUID, range_json: dict,
                      actor: UUID) -> AssumptionRow | None:
        row = await self.get(assumption_id)
        if row is not None:
            now = utc_now()
            row.status = "APPROVED"
            row.range_json = range_json
            row.approved_by = actor
            row.approved_at = now
            row.updated_at = now
            await self._session.flush()
        return row

    async def reject(self, assumption_id: UUID) -> AssumptionRow | None:
        row = await self.get(assumption_id)
        if row is not None:
            row.status = "REJECTED"
            row.updated_at = utc_now()
            await self._session.flush()
        return row

    async def link(self, assumption_id: UUID, target_id: UUID,
                   link_type: str) -> AssumptionLinkRow:
        row = AssumptionLinkRow(
            assumption_id=assumption_id,
            target_id=target_id,
            link_type=link_type,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_links(self, assumption_id: UUID, link_type: str) -> list[AssumptionLinkRow]:
        result = await self._session.execute(
            select(AssumptionLinkRow).where(
                AssumptionLinkRow.assumption_id == assumption_id,
                AssumptionLinkRow.link_type == link_type,
            )
        )
        return list(result.scalars().all())

    async def get_for_workspace(
        self, assumption_id: UUID, workspace_id: UUID,
    ) -> AssumptionRow | None:
        """Get assumption only if it belongs to the given workspace.

        Returns None for wrong workspace or legacy NULL workspace_id rows.
        """
        result = await self._session.execute(
            select(AssumptionRow).where(
                AssumptionRow.assumption_id == assumption_id,
                AssumptionRow.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_workspace(
        self, workspace_id: UUID, *,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AssumptionRow], int]:
        """List assumptions scoped to workspace with optional status filter.

        Returns (page_rows, total_count). Excludes NULL workspace_id rows.
        Orders by created_at DESC, assumption_id DESC.
        """
        base = select(AssumptionRow).where(
            AssumptionRow.workspace_id == workspace_id,
        )
        if status is not None:
            base = base.where(AssumptionRow.status == status)

        count_result = await self._session.execute(
            select(func.count()).select_from(base.subquery())
        )
        total = count_result.scalar_one()

        rows_result = await self._session.execute(
            base.order_by(
                AssumptionRow.created_at.desc(),
                AssumptionRow.assumption_id.desc(),
            ).limit(limit).offset(offset)
        )
        return list(rows_result.scalars().all()), total


class ClaimRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, claim_id: UUID, text: str, claim_type: str,
                     status: str = "EXTRACTED", disclosure_tier: str = "TIER0",
                     model_refs: list | None = None,
                     evidence_refs: list | None = None,
                     run_id: UUID | None = None) -> ClaimRow:
        now = utc_now()
        row = ClaimRow(
            claim_id=claim_id, text=text, claim_type=claim_type,
            status=status, disclosure_tier=disclosure_tier,
            model_refs=model_refs or [], evidence_refs=evidence_refs or [],
            run_id=run_id, created_at=now, updated_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self, claim_id: UUID) -> ClaimRow | None:
        return await self._session.get(ClaimRow, claim_id)

    async def get_by_run(self, run_id: UUID) -> list[ClaimRow]:
        result = await self._session.execute(
            select(ClaimRow).where(ClaimRow.run_id == run_id)
        )
        return list(result.scalars().all())

    async def update_status(self, claim_id: UUID, status: str) -> ClaimRow | None:
        row = await self.get(claim_id)
        if row is not None:
            row.status = status
            row.updated_at = utc_now()
            await self._session.flush()
        return row

    async def list_all(self) -> list[ClaimRow]:
        result = await self._session.execute(select(ClaimRow))
        return list(result.scalars().all())

    async def get_for_workspace(
        self, claim_id: UUID, workspace_id: UUID,
    ) -> ClaimRow | None:
        """Get a claim only if its run belongs to the given workspace."""
        result = await self._session.execute(
            select(ClaimRow)
            .join(RunSnapshotRow, ClaimRow.run_id == RunSnapshotRow.run_id)
            .where(
                ClaimRow.claim_id == claim_id,
                RunSnapshotRow.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_run_for_workspace(
        self, run_id: UUID, workspace_id: UUID,
    ) -> list[ClaimRow]:
        """Get claims for a run, only if the run belongs to the workspace."""
        result = await self._session.execute(
            select(ClaimRow)
            .join(RunSnapshotRow, ClaimRow.run_id == RunSnapshotRow.run_id)
            .where(
                ClaimRow.run_id == run_id,
                RunSnapshotRow.workspace_id == workspace_id,
            )
        )
        return list(result.scalars().all())

    async def link_evidence(self, claim_id: UUID, snippet_id: UUID) -> ClaimRow | None:
        """Append a snippet_id to the claim's evidence_refs list."""
        row = await self.get(claim_id)
        if row is not None:
            refs = list(row.evidence_refs or [])
            sid = str(snippet_id)
            if sid not in refs:
                refs.append(sid)
            row.evidence_refs = refs
            row.updated_at = utc_now()
            await self._session.flush()
        return row

    async def link_evidence_many(
        self, claim_id: UUID, snippet_ids: list[UUID],
    ) -> ClaimRow | None:
        """Append multiple snippet_ids to a claim's evidence_refs with dedupe."""
        row = await self.get(claim_id)
        if row is not None:
            refs = list(row.evidence_refs or [])
            for sid in snippet_ids:
                sid_str = str(sid)
                if sid_str not in refs:
                    refs.append(sid_str)
            row.evidence_refs = refs
            row.updated_at = utc_now()
            await self._session.flush()
        return row


class EvidenceSnippetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        snippet_id: UUID,
        source_id: UUID,
        page: int,
        bbox_x0: float,
        bbox_y0: float,
        bbox_x1: float,
        bbox_y1: float,
        extracted_text: str,
        table_cell_ref: dict | None = None,
        checksum: str,
    ) -> EvidenceSnippetRow:
        now = utc_now()
        row = EvidenceSnippetRow(
            snippet_id=snippet_id,
            source_id=source_id,
            page=page,
            bbox_x0=bbox_x0,
            bbox_y0=bbox_y0,
            bbox_x1=bbox_x1,
            bbox_y1=bbox_y1,
            extracted_text=extracted_text,
            table_cell_ref=table_cell_ref,
            checksum=checksum,
            created_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def create_many(self, snippets: list[dict]) -> list[EvidenceSnippetRow]:
        """Bulk-insert evidence snippets from dicts."""
        rows = []
        now = utc_now()
        for s in snippets:
            s.setdefault("created_at", now)
            row = EvidenceSnippetRow(**s)
            self._session.add(row)
            rows.append(row)
        await self._session.flush()
        return rows

    async def delete_by_source(self, source_id: UUID) -> int:
        """Delete all snippets for a source (idempotent retry support)."""
        from sqlalchemy import delete
        result = await self._session.execute(
            delete(EvidenceSnippetRow).where(
                EvidenceSnippetRow.source_id == source_id,
            )
        )
        await self._session.flush()
        return result.rowcount  # type: ignore[return-value]

    async def get(self, snippet_id: UUID) -> EvidenceSnippetRow | None:
        return await self._session.get(EvidenceSnippetRow, snippet_id)

    async def list_by_source(self, source_id: UUID) -> list[EvidenceSnippetRow]:
        result = await self._session.execute(
            select(EvidenceSnippetRow)
            .where(EvidenceSnippetRow.source_id == source_id)
            .order_by(EvidenceSnippetRow.page.asc(), EvidenceSnippetRow.snippet_id.asc())
        )
        return list(result.scalars().all())

    async def list_by_source_ids(self, source_ids: list[UUID]) -> list[EvidenceSnippetRow]:
        """Get all snippets for multiple source documents."""
        if not source_ids:
            return []
        result = await self._session.execute(
            select(EvidenceSnippetRow)
            .where(EvidenceSnippetRow.source_id.in_(source_ids))
            .order_by(EvidenceSnippetRow.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_for_workspace(
        self, snippet_id: UUID, workspace_id: UUID,
    ) -> EvidenceSnippetRow | None:
        """Get a snippet only if its source document belongs to the workspace."""
        result = await self._session.execute(
            select(EvidenceSnippetRow)
            .join(DocumentRow, EvidenceSnippetRow.source_id == DocumentRow.doc_id)
            .where(
                EvidenceSnippetRow.snippet_id == snippet_id,
                DocumentRow.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_workspace(
        self, workspace_id: UUID,
    ) -> list[EvidenceSnippetRow]:
        """Get all snippets for documents belonging to a workspace."""
        result = await self._session.execute(
            select(EvidenceSnippetRow)
            .join(DocumentRow, EvidenceSnippetRow.source_id == DocumentRow.doc_id)
            .where(DocumentRow.workspace_id == workspace_id)
            .order_by(EvidenceSnippetRow.created_at.asc())
        )
        return list(result.scalars().all())

    async def list_by_run_for_workspace(
        self, run_id: UUID, workspace_id: UUID,
    ) -> list[EvidenceSnippetRow]:
        """Get evidence snippets for a run's source documents.

        Resolves run → source_checksums → workspace documents matching those
        checksums → all evidence snippets for those documents.
        """
        snapshot_result = await self._session.execute(
            select(RunSnapshotRow).where(
                RunSnapshotRow.run_id == run_id,
                RunSnapshotRow.workspace_id == workspace_id,
            )
        )
        snapshot = snapshot_result.scalar_one_or_none()
        if snapshot is None:
            return []

        checksums: list[str] = snapshot.source_checksums or []
        if not checksums:
            return []

        doc_result = await self._session.execute(
            select(DocumentRow.doc_id).where(
                DocumentRow.workspace_id == workspace_id,
                DocumentRow.hash_sha256.in_(checksums),
            )
        )
        doc_ids = list(doc_result.scalars().all())
        if not doc_ids:
            return []

        result = await self._session.execute(
            select(EvidenceSnippetRow)
            .where(EvidenceSnippetRow.source_id.in_(doc_ids))
            .order_by(EvidenceSnippetRow.created_at.asc())
        )
        return list(result.scalars().all())
