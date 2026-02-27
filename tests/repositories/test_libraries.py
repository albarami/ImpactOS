"""Tests for Knowledge Flywheel repositories (MVP-12).

MappingLibraryRepository, AssumptionLibraryRepository, ScenarioPatternRepository.
"""

import pytest
from uuid_extensions import uuid7

from src.models.common import new_uuid7, utc_now


# ---------------------------------------------------------------------------
# MappingLibraryRepository
# ---------------------------------------------------------------------------


class TestMappingLibraryRepository:
    @pytest.mark.anyio
    async def test_create_entry_and_get(self, db_session) -> None:
        from src.repositories.libraries import MappingLibraryRepository

        repo = MappingLibraryRepository(db_session)
        eid = new_uuid7()
        ws = new_uuid7()
        row = await repo.create_entry(
            entry_id=eid,
            workspace_id=ws,
            pattern="concrete reinforcement",
            sector_code="F",
            confidence=0.9,
            tags=["construction"],
        )
        assert row.entry_id == eid
        assert row.sector_code == "F"
        assert row.status == "DRAFT"

        fetched = await repo.get_entry(eid)
        assert fetched is not None
        assert fetched.pattern == "concrete reinforcement"

    @pytest.mark.anyio
    async def test_get_entry_nonexistent(self, db_session) -> None:
        from src.repositories.libraries import MappingLibraryRepository

        repo = MappingLibraryRepository(db_session)
        assert await repo.get_entry(uuid7()) is None

    @pytest.mark.anyio
    async def test_get_entries_by_workspace(self, db_session) -> None:
        from src.repositories.libraries import MappingLibraryRepository

        repo = MappingLibraryRepository(db_session)
        ws = new_uuid7()
        await repo.create_entry(
            entry_id=new_uuid7(), workspace_id=ws,
            pattern="test1", sector_code="F", confidence=0.9,
        )
        await repo.create_entry(
            entry_id=new_uuid7(), workspace_id=ws,
            pattern="test2", sector_code="C", confidence=0.8,
        )
        rows = await repo.get_entries_by_workspace(ws)
        assert len(rows) == 2

    @pytest.mark.anyio
    async def test_get_entries_workspace_isolation(self, db_session) -> None:
        from src.repositories.libraries import MappingLibraryRepository

        repo = MappingLibraryRepository(db_session)
        ws1, ws2 = new_uuid7(), new_uuid7()
        await repo.create_entry(
            entry_id=new_uuid7(), workspace_id=ws1,
            pattern="test", sector_code="F", confidence=0.9,
        )
        assert await repo.get_entries_by_workspace(ws2) == []

    @pytest.mark.anyio
    async def test_update_usage(self, db_session) -> None:
        from src.repositories.libraries import MappingLibraryRepository

        repo = MappingLibraryRepository(db_session)
        eid = new_uuid7()
        await repo.create_entry(
            entry_id=eid, workspace_id=new_uuid7(),
            pattern="test", sector_code="F", confidence=0.9,
        )
        now = utc_now()
        updated = await repo.update_usage(eid, usage_count=5, last_used_at=now)
        assert updated is not None
        assert updated.usage_count == 5

    @pytest.mark.anyio
    async def test_update_usage_nonexistent(self, db_session) -> None:
        from src.repositories.libraries import MappingLibraryRepository

        repo = MappingLibraryRepository(db_session)
        result = await repo.update_usage(
            uuid7(), usage_count=1, last_used_at=utc_now(),
        )
        assert result is None

    @pytest.mark.anyio
    async def test_update_status(self, db_session) -> None:
        """Amendment 7: Status can be updated."""
        from src.repositories.libraries import MappingLibraryRepository

        repo = MappingLibraryRepository(db_session)
        eid = new_uuid7()
        await repo.create_entry(
            entry_id=eid, workspace_id=new_uuid7(),
            pattern="test", sector_code="F", confidence=0.9,
        )
        updated = await repo.update_status(eid, status="PUBLISHED")
        assert updated is not None
        assert updated.status == "PUBLISHED"

    @pytest.mark.anyio
    async def test_create_version(self, db_session) -> None:
        from src.repositories.libraries import MappingLibraryRepository

        repo = MappingLibraryRepository(db_session)
        ws = new_uuid7()
        vid = new_uuid7()
        row = await repo.create_version(
            library_version_id=vid,
            workspace_id=ws,
            version=1,
            entry_ids=[str(new_uuid7())],
            entry_count=1,
        )
        assert row.version == 1
        assert row.entry_count == 1

    @pytest.mark.anyio
    async def test_get_latest_version(self, db_session) -> None:
        from src.repositories.libraries import MappingLibraryRepository

        repo = MappingLibraryRepository(db_session)
        ws = new_uuid7()
        await repo.create_version(
            library_version_id=new_uuid7(), workspace_id=ws,
            version=1, entry_ids=[], entry_count=0,
        )
        await repo.create_version(
            library_version_id=new_uuid7(), workspace_id=ws,
            version=2, entry_ids=[str(new_uuid7())], entry_count=1,
        )
        latest = await repo.get_latest_version(ws)
        assert latest is not None
        assert latest.version == 2

    @pytest.mark.anyio
    async def test_get_versions_by_workspace(self, db_session) -> None:
        from src.repositories.libraries import MappingLibraryRepository

        repo = MappingLibraryRepository(db_session)
        ws = new_uuid7()
        await repo.create_version(
            library_version_id=new_uuid7(), workspace_id=ws,
            version=1, entry_ids=[], entry_count=0,
        )
        rows = await repo.get_versions_by_workspace(ws)
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# AssumptionLibraryRepository
# ---------------------------------------------------------------------------


class TestAssumptionLibraryRepository:
    @pytest.mark.anyio
    async def test_create_entry_and_get(self, db_session) -> None:
        from src.repositories.libraries import AssumptionLibraryRepository

        repo = AssumptionLibraryRepository(db_session)
        eid = new_uuid7()
        row = await repo.create_entry(
            entry_id=eid,
            workspace_id=new_uuid7(),
            assumption_type="IMPORT_SHARE",
            sector_code="F",
            default_value=0.35,
            range_low=0.20,
            range_high=0.50,
            unit="fraction",
            confidence="ESTIMATED",
        )
        assert row.entry_id == eid
        fetched = await repo.get_entry(eid)
        assert fetched is not None

    @pytest.mark.anyio
    async def test_get_entry_nonexistent(self, db_session) -> None:
        from src.repositories.libraries import AssumptionLibraryRepository

        repo = AssumptionLibraryRepository(db_session)
        assert await repo.get_entry(uuid7()) is None

    @pytest.mark.anyio
    async def test_get_entries_by_workspace(self, db_session) -> None:
        from src.repositories.libraries import AssumptionLibraryRepository

        repo = AssumptionLibraryRepository(db_session)
        ws = new_uuid7()
        await repo.create_entry(
            entry_id=new_uuid7(), workspace_id=ws,
            assumption_type="IMPORT_SHARE", sector_code="F",
            default_value=0.35, range_low=0.2, range_high=0.5,
            unit="fraction", confidence="ASSUMED",
        )
        rows = await repo.get_entries_by_workspace(ws)
        assert len(rows) == 1

    @pytest.mark.anyio
    async def test_get_entries_filter_by_type(self, db_session) -> None:
        from src.repositories.libraries import AssumptionLibraryRepository

        repo = AssumptionLibraryRepository(db_session)
        ws = new_uuid7()
        await repo.create_entry(
            entry_id=new_uuid7(), workspace_id=ws,
            assumption_type="IMPORT_SHARE", sector_code="F",
            default_value=0.35, range_low=0.2, range_high=0.5,
            unit="fraction", confidence="ASSUMED",
        )
        await repo.create_entry(
            entry_id=new_uuid7(), workspace_id=ws,
            assumption_type="PHASING", sector_code="F",
            default_value=0.5, range_low=0.3, range_high=0.7,
            unit="fraction", confidence="ESTIMATED",
        )
        rows = await repo.get_entries_by_workspace(
            ws, assumption_type="IMPORT_SHARE",
        )
        assert len(rows) == 1

    @pytest.mark.anyio
    async def test_get_entries_filter_by_sector(self, db_session) -> None:
        from src.repositories.libraries import AssumptionLibraryRepository

        repo = AssumptionLibraryRepository(db_session)
        ws = new_uuid7()
        await repo.create_entry(
            entry_id=new_uuid7(), workspace_id=ws,
            assumption_type="IMPORT_SHARE", sector_code="F",
            default_value=0.35, range_low=0.2, range_high=0.5,
            unit="fraction", confidence="ASSUMED",
        )
        rows = await repo.get_entries_by_workspace(ws, sector_code="C")
        assert len(rows) == 0

    @pytest.mark.anyio
    async def test_update_usage(self, db_session) -> None:
        from src.repositories.libraries import AssumptionLibraryRepository

        repo = AssumptionLibraryRepository(db_session)
        eid = new_uuid7()
        await repo.create_entry(
            entry_id=eid, workspace_id=new_uuid7(),
            assumption_type="IMPORT_SHARE", sector_code="F",
            default_value=0.35, range_low=0.2, range_high=0.5,
            unit="fraction", confidence="ASSUMED",
        )
        updated = await repo.update_usage(eid, usage_count=3, last_used_at=utc_now())
        assert updated is not None
        assert updated.usage_count == 3

    @pytest.mark.anyio
    async def test_create_version(self, db_session) -> None:
        from src.repositories.libraries import AssumptionLibraryRepository

        repo = AssumptionLibraryRepository(db_session)
        ws = new_uuid7()
        row = await repo.create_version(
            library_version_id=new_uuid7(), workspace_id=ws,
            version=1, entry_ids=[], entry_count=0,
        )
        assert row.version == 1

    @pytest.mark.anyio
    async def test_get_latest_version(self, db_session) -> None:
        from src.repositories.libraries import AssumptionLibraryRepository

        repo = AssumptionLibraryRepository(db_session)
        ws = new_uuid7()
        await repo.create_version(
            library_version_id=new_uuid7(), workspace_id=ws,
            version=1, entry_ids=[], entry_count=0,
        )
        await repo.create_version(
            library_version_id=new_uuid7(), workspace_id=ws,
            version=2, entry_ids=[], entry_count=0,
        )
        latest = await repo.get_latest_version(ws)
        assert latest is not None
        assert latest.version == 2


# ---------------------------------------------------------------------------
# ScenarioPatternRepository
# ---------------------------------------------------------------------------


class TestScenarioPatternRepository:
    @pytest.mark.anyio
    async def test_create_and_get(self, db_session) -> None:
        from src.repositories.libraries import ScenarioPatternRepository

        repo = ScenarioPatternRepository(db_session)
        pid = new_uuid7()
        row = await repo.create(
            pattern_id=pid,
            workspace_id=new_uuid7(),
            name="Mega construction",
            sector_focus=["F", "C"],
            typical_shock_types=["FINAL_DEMAND"],
        )
        assert row.pattern_id == pid

        fetched = await repo.get(pid)
        assert fetched is not None
        assert fetched.name == "Mega construction"

    @pytest.mark.anyio
    async def test_get_nonexistent(self, db_session) -> None:
        from src.repositories.libraries import ScenarioPatternRepository

        repo = ScenarioPatternRepository(db_session)
        assert await repo.get(uuid7()) is None

    @pytest.mark.anyio
    async def test_get_by_workspace(self, db_session) -> None:
        from src.repositories.libraries import ScenarioPatternRepository

        repo = ScenarioPatternRepository(db_session)
        ws = new_uuid7()
        await repo.create(
            pattern_id=new_uuid7(), workspace_id=ws,
            name="P1", sector_focus=["F"],
        )
        await repo.create(
            pattern_id=new_uuid7(), workspace_id=ws,
            name="P2", sector_focus=["C"],
        )
        rows = await repo.get_by_workspace(ws)
        assert len(rows) == 2

    @pytest.mark.anyio
    async def test_workspace_isolation(self, db_session) -> None:
        from src.repositories.libraries import ScenarioPatternRepository

        repo = ScenarioPatternRepository(db_session)
        ws1, ws2 = new_uuid7(), new_uuid7()
        await repo.create(
            pattern_id=new_uuid7(), workspace_id=ws1, name="P1",
        )
        assert await repo.get_by_workspace(ws2) == []

    @pytest.mark.anyio
    async def test_update_usage(self, db_session) -> None:
        from src.repositories.libraries import ScenarioPatternRepository

        repo = ScenarioPatternRepository(db_session)
        pid = new_uuid7()
        await repo.create(
            pattern_id=pid, workspace_id=new_uuid7(), name="P1",
        )
        updated = await repo.update_usage(pid, usage_count=7)
        assert updated is not None
        assert updated.usage_count == 7

    @pytest.mark.anyio
    async def test_update_usage_nonexistent(self, db_session) -> None:
        from src.repositories.libraries import ScenarioPatternRepository

        repo = ScenarioPatternRepository(db_session)
        result = await repo.update_usage(uuid7(), usage_count=1)
        assert result is None

    @pytest.mark.anyio
    async def test_flexjson_roundtrip(self, db_session) -> None:
        from src.repositories.libraries import ScenarioPatternRepository

        repo = ScenarioPatternRepository(db_session)
        pid = new_uuid7()
        await repo.create(
            pattern_id=pid,
            workspace_id=new_uuid7(),
            name="Test",
            sector_focus=["F", "C"],
            typical_shock_types=["FINAL_DEMAND"],
            tags=["infra", "PPP"],
        )
        row = await repo.get(pid)
        assert row is not None
        assert row.sector_focus == ["F", "C"]
        assert row.tags == ["infra", "PPP"]
