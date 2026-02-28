"""Tests for ExportRepository — TDD for exports rewiring."""

import pytest
from uuid_extensions import uuid7

from src.repositories.exports import ExportRepository


@pytest.fixture
def repo(db_session):
    return ExportRepository(db_session)


class TestExportRepository:
    """ExportRepository CRUD operations."""

    @pytest.mark.anyio
    async def test_create_and_get(self, repo: ExportRepository) -> None:
        eid = uuid7()
        rid = uuid7()
        row = await repo.create(
            export_id=eid,
            run_id=rid,
            mode="SANDBOX",
            status="COMPLETED",
            checksums_json={"excel": "sha256:abc123"},
            blocked_reasons=[],
        )
        assert row.export_id == eid
        assert row.run_id == rid
        assert row.status == "COMPLETED"

        fetched = await repo.get(eid)
        assert fetched is not None
        assert fetched.export_id == eid

    @pytest.mark.anyio
    async def test_get_nonexistent_returns_none(self, repo: ExportRepository) -> None:
        result = await repo.get(uuid7())
        assert result is None

    @pytest.mark.anyio
    async def test_list_all(self, repo: ExportRepository) -> None:
        for _ in range(3):
            await repo.create(
                export_id=uuid7(),
                run_id=uuid7(),
                mode="SANDBOX",
                status="COMPLETED",
            )
        rows = await repo.list_all()
        assert len(rows) == 3

    @pytest.mark.anyio
    async def test_update_status(self, repo: ExportRepository) -> None:
        eid = uuid7()
        await repo.create(
            export_id=eid,
            run_id=uuid7(),
            mode="SANDBOX",
            status="PENDING",
        )
        updated = await repo.update_status(eid, "COMPLETED")
        assert updated is not None
        assert updated.status == "COMPLETED"

    @pytest.mark.anyio
    async def test_checksums_persisted(self, repo: ExportRepository) -> None:
        eid = uuid7()
        checksums = {"excel": "sha256:aaa", "pptx": "sha256:bbb"}
        await repo.create(
            export_id=eid,
            run_id=uuid7(),
            mode="SANDBOX",
            status="COMPLETED",
            checksums_json=checksums,
        )
        fetched = await repo.get(eid)
        assert fetched is not None
        assert fetched.checksums_json == checksums

    @pytest.mark.anyio
    async def test_blocked_reasons_persisted(self, repo: ExportRepository) -> None:
        eid = uuid7()
        reasons = ["Unresolved claim C1", "Missing assumption A2"]
        await repo.create(
            export_id=eid,
            run_id=uuid7(),
            mode="GOVERNED",
            status="BLOCKED",
            blocked_reasons=reasons,
        )
        fetched = await repo.get(eid)
        assert fetched is not None
        assert fetched.blocked_reasons == reasons
