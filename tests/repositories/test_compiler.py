"""Tests for CompilationRepository and OverridePairRepository."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_extensions import uuid7

from src.repositories.compiler import CompilationRepository, OverridePairRepository


class TestCompilationRepository:
    """CRUD for compilations."""

    @pytest.mark.anyio
    async def test_create_and_get(self, db_session: AsyncSession) -> None:
        repo = CompilationRepository(db_session)
        cid = uuid7()
        row = await repo.create(
            compilation_id=cid,
            result_json={"mapping_suggestions": [], "high_confidence_count": 0},
            metadata_json={"line_items": []},
        )
        assert row.compilation_id == cid

        fetched = await repo.get(cid)
        assert fetched is not None
        assert fetched.result_json["high_confidence_count"] == 0

    @pytest.mark.anyio
    async def test_get_nonexistent(self, db_session: AsyncSession) -> None:
        repo = CompilationRepository(db_session)
        assert await repo.get(uuid7()) is None

    @pytest.mark.anyio
    async def test_result_json_stores_complex_data(self, db_session: AsyncSession) -> None:
        repo = CompilationRepository(db_session)
        result = {
            "mapping_suggestions": [
                {"line_item_id": str(uuid7()), "sector_code": "F", "confidence": 0.95, "explanation": "concrete"},
            ],
            "high_confidence_count": 1,
            "medium_confidence_count": 0,
            "low_confidence_count": 0,
            "assumption_drafts": [],
        }
        row = await repo.create(
            compilation_id=uuid7(),
            result_json=result,
            metadata_json={"decisions": {}},
        )
        fetched = await repo.get(row.compilation_id)
        assert fetched is not None
        assert len(fetched.result_json["mapping_suggestions"]) == 1
        assert fetched.result_json["mapping_suggestions"][0]["sector_code"] == "F"


class TestOverridePairRepository:
    """CRUD for override pairs."""

    @pytest.mark.anyio
    async def test_create_and_list(self, db_session: AsyncSession) -> None:
        repo = OverridePairRepository(db_session)
        eid = uuid7()
        await repo.create(
            override_id=uuid7(), engagement_id=eid,
            line_item_id=uuid7(), line_item_text="concrete works",
            suggested_sector_code="F", final_sector_code="F",
        )
        await repo.create(
            override_id=uuid7(), engagement_id=eid,
            line_item_id=uuid7(), line_item_text="steel",
            suggested_sector_code="C", final_sector_code="F",
        )
        all_rows = await repo.list_all()
        assert len(all_rows) == 2

    @pytest.mark.anyio
    async def test_get_by_engagement(self, db_session: AsyncSession) -> None:
        repo = OverridePairRepository(db_session)
        eid1 = uuid7()
        eid2 = uuid7()
        await repo.create(
            override_id=uuid7(), engagement_id=eid1,
            line_item_id=uuid7(), line_item_text="concrete",
            suggested_sector_code="F", final_sector_code="F",
        )
        await repo.create(
            override_id=uuid7(), engagement_id=eid2,
            line_item_id=uuid7(), line_item_text="steel",
            suggested_sector_code="C", final_sector_code="C",
        )
        rows = await repo.get_by_engagement(eid1)
        assert len(rows) == 1
        assert rows[0].engagement_id == eid1

    @pytest.mark.anyio
    async def test_override_with_actor(self, db_session: AsyncSession) -> None:
        repo = OverridePairRepository(db_session)
        actor = uuid7()
        row = await repo.create(
            override_id=uuid7(), engagement_id=uuid7(),
            line_item_id=uuid7(), line_item_text="plumbing",
            suggested_sector_code="F", final_sector_code="F",
            project_type="infrastructure", actor=actor,
        )
        assert row.actor == actor
        assert row.project_type == "infrastructure"
