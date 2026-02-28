"""Data quality repository — MVP-13.

Repos take AsyncSession, call add()/flush() only — never commit().
The session dependency handles commit/rollback (Unit-of-Work).

One summary per run (UniqueConstraint on run_id). save_summary is idempotent:
it deletes any existing row for the same run_id before inserting.
"""

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.tables import RunQualitySummaryRow
from src.models.common import utc_now


class DataQualityRepository:
    """Repository for immutable run-level data quality summaries."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_summary(
        self,
        *,
        summary_id: UUID,
        run_id: UUID,
        workspace_id: UUID,
        overall_run_score: float,
        overall_run_grade: str,
        coverage_pct: float,
        mapping_coverage_pct: float | None = None,
        publication_gate_pass: bool,
        publication_gate_mode: str,
        summary_version: str = "1.0.0",
        summary_hash: str = "",
        payload: dict,
    ) -> RunQualitySummaryRow:
        """Save (or replace) a run quality summary.

        Idempotent: deletes any existing summary for the same run_id first.
        """
        # Delete existing (idempotent upsert)
        await self._session.execute(
            delete(RunQualitySummaryRow).where(
                RunQualitySummaryRow.run_id == run_id,
            )
        )
        await self._session.flush()

        row = RunQualitySummaryRow(
            summary_id=summary_id,
            run_id=run_id,
            workspace_id=workspace_id,
            overall_run_score=overall_run_score,
            overall_run_grade=overall_run_grade,
            coverage_pct=coverage_pct,
            mapping_coverage_pct=mapping_coverage_pct,
            publication_gate_pass=publication_gate_pass,
            publication_gate_mode=publication_gate_mode,
            summary_version=summary_version,
            summary_hash=summary_hash,
            payload=payload,
            created_at=utc_now(),
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def get_by_run(self, run_id: UUID) -> RunQualitySummaryRow | None:
        """Get the quality summary for a specific run."""
        result = await self._session.execute(
            select(RunQualitySummaryRow).where(
                RunQualitySummaryRow.run_id == run_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_workspace(
        self, workspace_id: UUID,
    ) -> list[RunQualitySummaryRow]:
        """Get all quality summaries for a workspace, newest first."""
        result = await self._session.execute(
            select(RunQualitySummaryRow)
            .where(RunQualitySummaryRow.workspace_id == workspace_id)
            .order_by(RunQualitySummaryRow.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_failing_gate(
        self, workspace_id: UUID,
    ) -> list[RunQualitySummaryRow]:
        """Get all summaries where publication gate failed for a workspace."""
        result = await self._session.execute(
            select(RunQualitySummaryRow)
            .where(
                RunQualitySummaryRow.workspace_id == workspace_id,
                RunQualitySummaryRow.publication_gate_pass.is_(False),
            )
            .order_by(RunQualitySummaryRow.created_at.desc())
        )
        return list(result.scalars().all())

    async def delete_by_run(self, run_id: UUID) -> bool:
        """Delete the quality summary for a run. Returns True if deleted."""
        result = await self._session.execute(
            delete(RunQualitySummaryRow).where(
                RunQualitySummaryRow.run_id == run_id,
            )
        )
        await self._session.flush()
        return result.rowcount > 0
