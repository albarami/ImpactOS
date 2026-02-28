"""Workforce repositories — MVP-11.

4 repos: EmploymentCoefficients, SectorOccupationBridge,
SaudizationRules, WorkforceResult.

Repos take AsyncSession, call add()/flush() only — never commit().
The session dependency handles commit/rollback (Unit-of-Work).

Amendment 9: WorkforceResultRepository.get_existing() for idempotency.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.tables import (
    EmploymentCoefficientsRow,
    SaudizationRulesRow,
    SectorOccupationBridgeRow,
    WorkforceResultRow,
)
from src.models.common import utc_now


class EmploymentCoefficientsRepository:
    """Repository for versioned employment coefficients (append-only)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        employment_coefficients_id: UUID,
        version: int,
        model_version_id: UUID,
        workspace_id: UUID,
        output_unit: str,
        base_year: int,
        coefficients: list,
    ) -> EmploymentCoefficientsRow:
        row = EmploymentCoefficientsRow(
            employment_coefficients_id=employment_coefficients_id,
            version=version,
            model_version_id=model_version_id,
            workspace_id=workspace_id,
            output_unit=output_unit,
            base_year=base_year,
            coefficients=coefficients,
            created_at=utc_now(),
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def get(
        self, employment_coefficients_id: UUID, version: int,
    ) -> EmploymentCoefficientsRow | None:
        result = await self._session.execute(
            select(EmploymentCoefficientsRow).where(
                EmploymentCoefficientsRow.employment_coefficients_id == employment_coefficients_id,
                EmploymentCoefficientsRow.version == version,
            )
        )
        return result.scalar_one_or_none()

    async def get_latest(
        self, employment_coefficients_id: UUID,
    ) -> EmploymentCoefficientsRow | None:
        result = await self._session.execute(
            select(EmploymentCoefficientsRow)
            .where(
                EmploymentCoefficientsRow.employment_coefficients_id == employment_coefficients_id,
            )
            .order_by(EmploymentCoefficientsRow.version.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_by_workspace(
        self, workspace_id: UUID,
    ) -> list[EmploymentCoefficientsRow]:
        result = await self._session.execute(
            select(EmploymentCoefficientsRow)
            .where(EmploymentCoefficientsRow.workspace_id == workspace_id)
            .order_by(EmploymentCoefficientsRow.created_at.desc())
        )
        return list(result.scalars().all())


class SectorOccupationBridgeRepository:
    """Repository for versioned sector-occupation bridge (append-only)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        bridge_id: UUID,
        version: int,
        model_version_id: UUID,
        workspace_id: UUID,
        entries: list,
    ) -> SectorOccupationBridgeRow:
        row = SectorOccupationBridgeRow(
            bridge_id=bridge_id,
            version=version,
            model_version_id=model_version_id,
            workspace_id=workspace_id,
            entries=entries,
            created_at=utc_now(),
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def get(
        self, bridge_id: UUID, version: int,
    ) -> SectorOccupationBridgeRow | None:
        result = await self._session.execute(
            select(SectorOccupationBridgeRow).where(
                SectorOccupationBridgeRow.bridge_id == bridge_id,
                SectorOccupationBridgeRow.version == version,
            )
        )
        return result.scalar_one_or_none()

    async def get_latest(
        self, bridge_id: UUID,
    ) -> SectorOccupationBridgeRow | None:
        result = await self._session.execute(
            select(SectorOccupationBridgeRow)
            .where(SectorOccupationBridgeRow.bridge_id == bridge_id)
            .order_by(SectorOccupationBridgeRow.version.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_by_workspace(
        self, workspace_id: UUID,
    ) -> list[SectorOccupationBridgeRow]:
        result = await self._session.execute(
            select(SectorOccupationBridgeRow)
            .where(SectorOccupationBridgeRow.workspace_id == workspace_id)
            .order_by(SectorOccupationBridgeRow.created_at.desc())
        )
        return list(result.scalars().all())


class SaudizationRulesRepository:
    """Repository for versioned saudization rules (append-only)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        rules_id: UUID,
        version: int,
        workspace_id: UUID,
        tier_assignments: list,
        sector_targets: list,
    ) -> SaudizationRulesRow:
        row = SaudizationRulesRow(
            rules_id=rules_id,
            version=version,
            workspace_id=workspace_id,
            tier_assignments=tier_assignments,
            sector_targets=sector_targets,
            created_at=utc_now(),
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return row

    async def get(
        self, rules_id: UUID, version: int,
    ) -> SaudizationRulesRow | None:
        result = await self._session.execute(
            select(SaudizationRulesRow).where(
                SaudizationRulesRow.rules_id == rules_id,
                SaudizationRulesRow.version == version,
            )
        )
        return result.scalar_one_or_none()

    async def get_latest(
        self, rules_id: UUID,
    ) -> SaudizationRulesRow | None:
        result = await self._session.execute(
            select(SaudizationRulesRow)
            .where(SaudizationRulesRow.rules_id == rules_id)
            .order_by(SaudizationRulesRow.version.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_by_workspace(
        self, workspace_id: UUID,
    ) -> list[SaudizationRulesRow]:
        result = await self._session.execute(
            select(SaudizationRulesRow)
            .where(SaudizationRulesRow.workspace_id == workspace_id)
            .order_by(SaudizationRulesRow.created_at.desc())
        )
        return list(result.scalars().all())


class WorkforceResultRepository:
    """Repository for immutable workforce results.

    Amendment 9: get_existing() for idempotency.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        workforce_result_id: UUID,
        workspace_id: UUID,
        run_id: UUID,
        employment_coefficients_id: UUID,
        employment_coefficients_version: int,
        bridge_id: UUID | None = None,
        bridge_version: int | None = None,
        rules_id: UUID | None = None,
        rules_version: int | None = None,
        results: dict,
        confidence_summary: dict,
        data_quality_notes: list,
        satellite_coefficients_hash: str,
        delta_x_source: str,
        feasibility_result_id: UUID | None = None,
    ) -> WorkforceResultRow:
        row = WorkforceResultRow(
            workforce_result_id=workforce_result_id,
            workspace_id=workspace_id,
            run_id=run_id,
            employment_coefficients_id=employment_coefficients_id,
            employment_coefficients_version=employment_coefficients_version,
            bridge_id=bridge_id,
            bridge_version=bridge_version,
            rules_id=rules_id,
            rules_version=rules_version,
            results=results,
            confidence_summary=confidence_summary,
            data_quality_notes=data_quality_notes,
            satellite_coefficients_hash=satellite_coefficients_hash,
            delta_x_source=delta_x_source,
            feasibility_result_id=feasibility_result_id,
            created_at=utc_now(),
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self, workforce_result_id: UUID) -> WorkforceResultRow | None:
        return await self._session.get(WorkforceResultRow, workforce_result_id)

    async def get_by_run(self, run_id: UUID) -> list[WorkforceResultRow]:
        result = await self._session.execute(
            select(WorkforceResultRow)
            .where(WorkforceResultRow.run_id == run_id)
            .order_by(WorkforceResultRow.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_workspace(self, workspace_id: UUID) -> list[WorkforceResultRow]:
        result = await self._session.execute(
            select(WorkforceResultRow)
            .where(WorkforceResultRow.workspace_id == workspace_id)
            .order_by(WorkforceResultRow.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_existing(
        self,
        *,
        run_id: UUID,
        employment_coefficients_id: UUID,
        employment_coefficients_version: int,
        delta_x_source: str,
    ) -> WorkforceResultRow | None:
        """Amendment 9: Idempotency check — find existing result with same inputs."""
        result = await self._session.execute(
            select(WorkforceResultRow).where(
                WorkforceResultRow.run_id == run_id,
                WorkforceResultRow.employment_coefficients_id == employment_coefficients_id,
                WorkforceResultRow.employment_coefficients_version
                == employment_coefficients_version,
                WorkforceResultRow.delta_x_source == delta_x_source,
            )
        )
        return result.scalar_one_or_none()
