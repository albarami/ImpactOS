"""Assumption, claim, and evidence snippet repositories."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.tables import AssumptionRow, AssumptionLinkRow, ClaimRow, EvidenceSnippetRow
from src.models.common import utc_now


class AssumptionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, assumption_id: UUID, type: str, value: float,
                     units: str, justification: str,
                     evidence_refs: list | None = None,
                     range_json: dict | None = None,
                     status: str = "DRAFT") -> AssumptionRow:
        now = utc_now()
        row = AssumptionRow(
            assumption_id=assumption_id, type=type, value=value,
            range_json=range_json, units=units, justification=justification,
            evidence_refs=evidence_refs or [], status=status,
            created_at=now, updated_at=now,
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
