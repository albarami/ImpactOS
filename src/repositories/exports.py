"""Export repository — stores export metadata in the database."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.tables import ExportRow, RunSnapshotRow, VarianceBridgeAnalysisRow
from src.models.common import utc_now
from src.models.export import VarianceBridgeAnalysis


class ExportRepository:
    """DB-backed export store. Replaces in-memory _export_store dict."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        export_id: UUID,
        run_id: UUID,
        mode: str,
        status: str,
        template_version: str = "v1.0",
        disclosure_tier: str = "TIER0",
        checksums_json: dict | None = None,
        blocked_reasons: list[str] | None = None,
        artifact_refs_json: dict | None = None,
    ) -> ExportRow:
        row = ExportRow(
            export_id=export_id,
            run_id=run_id,
            template_version=template_version,
            mode=mode,
            disclosure_tier=disclosure_tier,
            status=status,
            checksums_json=checksums_json,
            blocked_reasons=blocked_reasons or [],
            artifact_refs_json=artifact_refs_json,
            created_at=utc_now(),
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def get(self, export_id: UUID) -> ExportRow | None:
        return await self._session.get(ExportRow, export_id)

    async def get_for_workspace(
        self, export_id: UUID, workspace_id: UUID,
    ) -> ExportRow | None:
        """Get export only if its run belongs to the given workspace."""
        result = await self._session.execute(
            select(ExportRow)
            .join(RunSnapshotRow, ExportRow.run_id == RunSnapshotRow.run_id)
            .where(
                ExportRow.export_id == export_id,
                RunSnapshotRow.workspace_id == workspace_id,
            )
        )
        return result.scalar_one_or_none()

    async def set_artifact_refs(
        self, export_id: UUID, artifact_refs: dict[str, str],
    ) -> ExportRow | None:
        """Set artifact storage references on an existing export."""
        row = await self.get(export_id)
        if row is not None:
            row.artifact_refs_json = artifact_refs
            await self._session.flush()
        return row

    async def list_all(self) -> list[ExportRow]:
        result = await self._session.execute(select(ExportRow))
        return list(result.scalars().all())

    async def update_status(self, export_id: UUID, status: str) -> ExportRow | None:
        row = await self.get(export_id)
        if row is not None:
            row.status = status
            await self._session.flush()
        return row


# ---------------------------------------------------------------------------
# Variance Bridge Analysis (Sprint 23)
# ---------------------------------------------------------------------------


class VarianceBridgeRepository:
    """Workspace-scoped variance bridge analytics repository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, analysis: VarianceBridgeAnalysis,
    ) -> VarianceBridgeAnalysis:
        """Create or return existing (idempotent by config_hash)."""
        existing = await self.get_by_config_hash(
            analysis.workspace_id, analysis.config_hash,
        )
        if existing:
            return existing

        row = VarianceBridgeAnalysisRow(
            analysis_id=analysis.analysis_id,
            workspace_id=analysis.workspace_id,
            run_a_id=analysis.run_a_id,
            run_b_id=analysis.run_b_id,
            metric_type=analysis.metric_type,
            analysis_version=analysis.analysis_version,
            config_json=analysis.config_json,
            config_hash=analysis.config_hash,
            result_json=analysis.result_json,
            result_checksum=analysis.result_checksum,
            created_at=analysis.created_at,
        )
        self._session.add(row)
        await self._session.flush()
        return analysis

    async def get(
        self, workspace_id: UUID, analysis_id: UUID,
    ) -> VarianceBridgeAnalysis | None:
        """Get by ID, workspace-scoped."""
        stmt = select(VarianceBridgeAnalysisRow).where(
            VarianceBridgeAnalysisRow.analysis_id == analysis_id,
            VarianceBridgeAnalysisRow.workspace_id == workspace_id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _row_to_bridge(row) if row else None

    async def get_by_config_hash(
        self, workspace_id: UUID, config_hash: str,
    ) -> VarianceBridgeAnalysis | None:
        """Get by config_hash, workspace-scoped."""
        stmt = select(VarianceBridgeAnalysisRow).where(
            VarianceBridgeAnalysisRow.workspace_id == workspace_id,
            VarianceBridgeAnalysisRow.config_hash == config_hash,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _row_to_bridge(row) if row else None

    async def list_for_workspace(
        self,
        workspace_id: UUID,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[VarianceBridgeAnalysis]:
        """List all bridges for workspace."""
        stmt = (
            select(VarianceBridgeAnalysisRow)
            .where(VarianceBridgeAnalysisRow.workspace_id == workspace_id)
            .order_by(VarianceBridgeAnalysisRow.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_row_to_bridge(r) for r in rows]


def _row_to_bridge(row: VarianceBridgeAnalysisRow) -> VarianceBridgeAnalysis:
    """Convert ORM row to Pydantic model."""
    return VarianceBridgeAnalysis(
        analysis_id=row.analysis_id,
        workspace_id=row.workspace_id,
        run_a_id=row.run_a_id,
        run_b_id=row.run_b_id,
        metric_type=row.metric_type,
        analysis_version=row.analysis_version,
        config_json=row.config_json,
        config_hash=row.config_hash,
        result_json=row.result_json,
        result_checksum=row.result_checksum,
        created_at=row.created_at,
    )
