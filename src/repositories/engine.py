"""Engine repositories — model versions, model data, run snapshots, results, batches."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.tables import (
    ModelVersionRow,
    ModelDataRow,
    RunSnapshotRow,
    ResultSetRow,
    BatchRow,
)
from src.models.common import utc_now


class ModelVersionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, model_version_id: UUID, base_year: int,
                     source: str, sector_count: int, checksum: str) -> ModelVersionRow:
        row = ModelVersionRow(
            model_version_id=model_version_id, base_year=base_year,
            source=source, sector_count=sector_count, checksum=checksum,
            created_at=utc_now(),
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self, model_version_id: UUID) -> ModelVersionRow | None:
        return await self._session.get(ModelVersionRow, model_version_id)

    async def list_all(self) -> list[ModelVersionRow]:
        result = await self._session.execute(select(ModelVersionRow))
        return list(result.scalars().all())


class ModelDataRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, model_version_id: UUID, z_matrix_json: list,
                     x_vector_json: list, sector_codes: list,
                     storage_format: str = "json") -> ModelDataRow:
        row = ModelDataRow(
            model_version_id=model_version_id,
            z_matrix_json=z_matrix_json,
            x_vector_json=x_vector_json,
            sector_codes=sector_codes,
            storage_format=storage_format,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self, model_version_id: UUID) -> ModelDataRow | None:
        return await self._session.get(ModelDataRow, model_version_id)


class RunSnapshotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, run_id: UUID, model_version_id: UUID,
                     taxonomy_version_id: UUID, concordance_version_id: UUID,
                     mapping_library_version_id: UUID,
                     assumption_library_version_id: UUID,
                     prompt_pack_version_id: UUID,
                     constraint_set_version_id: UUID | None = None,
                     source_checksums: list | None = None) -> RunSnapshotRow:
        row = RunSnapshotRow(
            run_id=run_id, model_version_id=model_version_id,
            taxonomy_version_id=taxonomy_version_id,
            concordance_version_id=concordance_version_id,
            mapping_library_version_id=mapping_library_version_id,
            assumption_library_version_id=assumption_library_version_id,
            prompt_pack_version_id=prompt_pack_version_id,
            constraint_set_version_id=constraint_set_version_id,
            source_checksums=source_checksums or [],
            created_at=utc_now(),
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self, run_id: UUID) -> RunSnapshotRow | None:
        return await self._session.get(RunSnapshotRow, run_id)


class ResultSetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, result_id: UUID, run_id: UUID,
                     metric_type: str, values: dict,
                     sector_breakdowns: dict | None = None) -> ResultSetRow:
        row = ResultSetRow(
            result_id=result_id, run_id=run_id,
            metric_type=metric_type, values=values,
            sector_breakdowns=sector_breakdowns or {},
            created_at=utc_now(),
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get_by_run(self, run_id: UUID) -> list[ResultSetRow]:
        result = await self._session.execute(
            select(ResultSetRow).where(ResultSetRow.run_id == run_id)
        )
        return list(result.scalars().all())


class BatchRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, *, batch_id: UUID, run_ids: list,
                     status: str = "COMPLETED",
                     workspace_id: UUID | None = None) -> BatchRow:
        row = BatchRow(
            batch_id=batch_id, run_ids=run_ids,
            status=status, workspace_id=workspace_id,
            created_at=utc_now(),
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self, batch_id: UUID) -> BatchRow | None:
        return await self._session.get(BatchRow, batch_id)

    async def update_status(self, batch_id: UUID, status: str) -> BatchRow | None:
        """Update batch status (PENDING → RUNNING → COMPLETED/FAILED)."""
        row = await self.get(batch_id)
        if row is not None:
            row.status = status
            await self._session.flush()
        return row
