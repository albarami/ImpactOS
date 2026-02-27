"""Tests for engine repositories — ModelVersion, ModelData, RunSnapshot, ResultSet, Batch."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_extensions import uuid7

from src.repositories.engine import (
    ModelVersionRepository,
    ModelDataRepository,
    RunSnapshotRepository,
    ResultSetRepository,
    BatchRepository,
)


class TestModelVersionRepository:
    @pytest.mark.anyio
    async def test_create_and_get(self, db_session: AsyncSession) -> None:
        repo = ModelVersionRepository(db_session)
        mvid = uuid7()
        row = await repo.create(
            model_version_id=mvid, base_year=2023,
            source="test", sector_count=3, checksum="sha256:abc",
        )
        assert row.model_version_id == mvid

        fetched = await repo.get(mvid)
        assert fetched is not None
        assert fetched.sector_count == 3

    @pytest.mark.anyio
    async def test_list_all(self, db_session: AsyncSession) -> None:
        repo = ModelVersionRepository(db_session)
        await repo.create(model_version_id=uuid7(), base_year=2023, source="a", sector_count=2, checksum="sha256:1")
        await repo.create(model_version_id=uuid7(), base_year=2024, source="b", sector_count=3, checksum="sha256:2")
        rows = await repo.list_all()
        assert len(rows) == 2


class TestModelDataRepository:
    @pytest.mark.anyio
    async def test_create_and_get(self, db_session: AsyncSession) -> None:
        mv_repo = ModelVersionRepository(db_session)
        mvid = uuid7()
        await mv_repo.create(model_version_id=mvid, base_year=2023, source="t", sector_count=2, checksum="sha256:x")

        data_repo = ModelDataRepository(db_session)
        row = await data_repo.create(
            model_version_id=mvid,
            z_matrix_json=[[1.0, 2.0], [3.0, 4.0]],
            x_vector_json=[10.0, 20.0],
            sector_codes=["S1", "S2"],
        )
        assert row.model_version_id == mvid

        fetched = await data_repo.get(mvid)
        assert fetched is not None
        assert fetched.z_matrix_json == [[1.0, 2.0], [3.0, 4.0]]
        assert fetched.sector_codes == ["S1", "S2"]


class TestRunSnapshotRepository:
    @pytest.mark.anyio
    async def test_create_and_get(self, db_session: AsyncSession) -> None:
        repo = RunSnapshotRepository(db_session)
        rid = uuid7()
        row = await repo.create(
            run_id=rid, model_version_id=uuid7(),
            taxonomy_version_id=uuid7(), concordance_version_id=uuid7(),
            mapping_library_version_id=uuid7(),
            assumption_library_version_id=uuid7(),
            prompt_pack_version_id=uuid7(),
        )
        assert row.run_id == rid

        fetched = await repo.get(rid)
        assert fetched is not None


class TestResultSetRepository:
    @pytest.mark.anyio
    async def test_create_and_get_by_run(self, db_session: AsyncSession) -> None:
        repo = ResultSetRepository(db_session)
        rid = uuid7()
        await repo.create(
            result_id=uuid7(), run_id=rid,
            metric_type="total_output",
            values={"S1": 100.0, "S2": 200.0},
        )
        await repo.create(
            result_id=uuid7(), run_id=rid,
            metric_type="employment",
            values={"S1": 10.0, "S2": 20.0},
        )
        rows = await repo.get_by_run(rid)
        assert len(rows) == 2
        types = {r.metric_type for r in rows}
        assert types == {"total_output", "employment"}


class TestBatchRepository:
    @pytest.mark.anyio
    async def test_create_and_get(self, db_session: AsyncSession) -> None:
        repo = BatchRepository(db_session)
        bid = uuid7()
        r1, r2 = str(uuid7()), str(uuid7())
        row = await repo.create(batch_id=bid, run_ids=[r1, r2])
        assert row.batch_id == bid

        fetched = await repo.get(bid)
        assert fetched is not None
        assert len(fetched.run_ids) == 2

    @pytest.mark.anyio
    async def test_get_nonexistent(self, db_session: AsyncSession) -> None:
        repo = BatchRepository(db_session)
        assert await repo.get(uuid7()) is None
