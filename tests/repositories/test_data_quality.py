"""Tests for DataQualityRepository — MVP-13.

Covers: save_summary, get_by_run, get_by_workspace, get_failing_gate, delete_by_run.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_extensions import uuid7

from src.models.common import utc_now
from src.repositories.data_quality import DataQualityRepository


def _make_payload(
    *,
    run_id=None,
    workspace_id=None,
    overall_run_score=0.85,
    overall_run_grade="B",
    coverage_pct=0.9,
    mapping_coverage_pct=0.75,
    publication_gate_pass=True,
    publication_gate_mode="PASS",
    summary_version="1.0.0",
    summary_hash="abc123",
):
    """Build a minimal RunQualitySummary-like payload dict for testing."""
    return {
        "run_id": str(run_id or uuid7()),
        "workspace_id": str(workspace_id or uuid7()),
        "base_table_vintage": "GASTAT 2019 IO Table",
        "base_table_year": 2019,
        "years_since_base": 7,
        "input_scores": [],
        "overall_run_score": overall_run_score,
        "overall_run_grade": overall_run_grade,
        "freshness_report": {
            "checks": [],
            "stale_count": 0,
            "expired_count": 0,
            "overall_freshness": "CURRENT",
        },
        "coverage_pct": coverage_pct,
        "mapping_coverage_pct": mapping_coverage_pct,
        "key_gaps": [],
        "key_strengths": ["Good freshness"],
        "recommendation": "Publish with confidence.",
        "publication_gate_pass": publication_gate_pass,
        "publication_gate_mode": publication_gate_mode,
        "summary_version": summary_version,
        "summary_hash": summary_hash,
        "created_at": utc_now().isoformat(),
    }


class TestSaveSummary:
    @pytest.mark.anyio
    async def test_save_and_retrieve(self, db_session: AsyncSession) -> None:
        repo = DataQualityRepository(db_session)
        run_id = uuid7()
        ws_id = uuid7()
        payload = _make_payload(run_id=run_id, workspace_id=ws_id)

        row = await repo.save_summary(
            summary_id=uuid7(),
            run_id=run_id,
            workspace_id=ws_id,
            overall_run_score=0.85,
            overall_run_grade="B",
            coverage_pct=0.9,
            mapping_coverage_pct=0.75,
            publication_gate_pass=True,
            publication_gate_mode="PASS",
            summary_version="1.0.0",
            summary_hash="abc123",
            payload=payload,
        )
        assert row.run_id == run_id
        assert row.overall_run_score == 0.85
        assert row.publication_gate_pass is True

    @pytest.mark.anyio
    async def test_save_idempotent_same_run(self, db_session: AsyncSession) -> None:
        """Second save for same run_id should replace the first."""
        repo = DataQualityRepository(db_session)
        run_id = uuid7()
        ws_id = uuid7()

        payload1 = _make_payload(
            run_id=run_id, workspace_id=ws_id, overall_run_score=0.6,
        )
        await repo.save_summary(
            summary_id=uuid7(), run_id=run_id, workspace_id=ws_id,
            overall_run_score=0.6, overall_run_grade="C", coverage_pct=0.5,
            publication_gate_pass=False, publication_gate_mode="PASS_WITH_WARNINGS",
            summary_version="1.0.0", summary_hash="h1", payload=payload1,
        )

        # Save again — should delete old + insert new
        payload2 = _make_payload(
            run_id=run_id, workspace_id=ws_id, overall_run_score=0.9,
        )
        row = await repo.save_summary(
            summary_id=uuid7(), run_id=run_id, workspace_id=ws_id,
            overall_run_score=0.9, overall_run_grade="A", coverage_pct=0.95,
            publication_gate_pass=True, publication_gate_mode="PASS",
            summary_version="1.0.0", summary_hash="h2", payload=payload2,
        )
        assert row.overall_run_score == 0.9

        # Should only be 1 row for this run
        fetched = await repo.get_by_run(run_id)
        assert fetched is not None
        assert fetched.overall_run_score == 0.9

    @pytest.mark.anyio
    async def test_save_with_null_mapping_coverage(self, db_session: AsyncSession) -> None:
        repo = DataQualityRepository(db_session)
        run_id = uuid7()
        payload = _make_payload(run_id=run_id, mapping_coverage_pct=None)

        row = await repo.save_summary(
            summary_id=uuid7(), run_id=run_id, workspace_id=uuid7(),
            overall_run_score=0.8, overall_run_grade="B", coverage_pct=0.85,
            mapping_coverage_pct=None,
            publication_gate_pass=True, publication_gate_mode="PASS",
            summary_version="1.0.0", summary_hash="x", payload=payload,
        )
        assert row.mapping_coverage_pct is None


class TestGetByRun:
    @pytest.mark.anyio
    async def test_existing_run(self, db_session: AsyncSession) -> None:
        repo = DataQualityRepository(db_session)
        run_id = uuid7()
        payload = _make_payload(run_id=run_id)

        await repo.save_summary(
            summary_id=uuid7(), run_id=run_id, workspace_id=uuid7(),
            overall_run_score=0.75, overall_run_grade="B", coverage_pct=0.8,
            publication_gate_pass=True, publication_gate_mode="PASS",
            summary_version="1.0.0", summary_hash="y", payload=payload,
        )

        fetched = await repo.get_by_run(run_id)
        assert fetched is not None
        assert fetched.overall_run_grade == "B"

    @pytest.mark.anyio
    async def test_missing_run(self, db_session: AsyncSession) -> None:
        repo = DataQualityRepository(db_session)
        fetched = await repo.get_by_run(uuid7())
        assert fetched is None


class TestGetByWorkspace:
    @pytest.mark.anyio
    async def test_multiple_summaries(self, db_session: AsyncSession) -> None:
        repo = DataQualityRepository(db_session)
        ws_id = uuid7()

        for i in range(3):
            run_id = uuid7()
            payload = _make_payload(run_id=run_id, workspace_id=ws_id)
            await repo.save_summary(
                summary_id=uuid7(), run_id=run_id, workspace_id=ws_id,
                overall_run_score=0.7 + i * 0.05, overall_run_grade="B",
                coverage_pct=0.8, publication_gate_pass=True,
                publication_gate_mode="PASS", summary_version="1.0.0",
                summary_hash=f"h{i}", payload=payload,
            )

        rows = await repo.get_by_workspace(ws_id)
        assert len(rows) == 3

    @pytest.mark.anyio
    async def test_empty_workspace(self, db_session: AsyncSession) -> None:
        repo = DataQualityRepository(db_session)
        rows = await repo.get_by_workspace(uuid7())
        assert rows == []

    @pytest.mark.anyio
    async def test_workspace_isolation(self, db_session: AsyncSession) -> None:
        repo = DataQualityRepository(db_session)
        ws1 = uuid7()
        ws2 = uuid7()

        for ws in [ws1, ws1, ws2]:
            run_id = uuid7()
            payload = _make_payload(run_id=run_id, workspace_id=ws)
            await repo.save_summary(
                summary_id=uuid7(), run_id=run_id, workspace_id=ws,
                overall_run_score=0.8, overall_run_grade="B",
                coverage_pct=0.8, publication_gate_pass=True,
                publication_gate_mode="PASS", summary_version="1.0.0",
                summary_hash="h", payload=payload,
            )

        assert len(await repo.get_by_workspace(ws1)) == 2
        assert len(await repo.get_by_workspace(ws2)) == 1


class TestGetFailingGate:
    @pytest.mark.anyio
    async def test_returns_only_failing(self, db_session: AsyncSession) -> None:
        repo = DataQualityRepository(db_session)
        ws_id = uuid7()

        # Passing run
        r1 = uuid7()
        p1 = _make_payload(run_id=r1, workspace_id=ws_id, publication_gate_pass=True)
        await repo.save_summary(
            summary_id=uuid7(), run_id=r1, workspace_id=ws_id,
            overall_run_score=0.9, overall_run_grade="A", coverage_pct=0.95,
            publication_gate_pass=True, publication_gate_mode="PASS",
            summary_version="1.0.0", summary_hash="p1", payload=p1,
        )

        # Failing run
        r2 = uuid7()
        p2 = _make_payload(
            run_id=r2, workspace_id=ws_id, publication_gate_pass=False,
        )
        await repo.save_summary(
            summary_id=uuid7(), run_id=r2, workspace_id=ws_id,
            overall_run_score=0.3, overall_run_grade="F", coverage_pct=0.4,
            publication_gate_pass=False, publication_gate_mode="FAIL_REQUIRES_WAIVER",
            summary_version="1.0.0", summary_hash="p2", payload=p2,
        )

        failing = await repo.get_failing_gate(ws_id)
        assert len(failing) == 1
        assert failing[0].run_id == r2

    @pytest.mark.anyio
    async def test_no_failing(self, db_session: AsyncSession) -> None:
        repo = DataQualityRepository(db_session)
        ws_id = uuid7()

        run_id = uuid7()
        payload = _make_payload(run_id=run_id, workspace_id=ws_id)
        await repo.save_summary(
            summary_id=uuid7(), run_id=run_id, workspace_id=ws_id,
            overall_run_score=0.9, overall_run_grade="A", coverage_pct=0.95,
            publication_gate_pass=True, publication_gate_mode="PASS",
            summary_version="1.0.0", summary_hash="ok", payload=payload,
        )

        failing = await repo.get_failing_gate(ws_id)
        assert failing == []


class TestDeleteByRun:
    @pytest.mark.anyio
    async def test_delete_existing(self, db_session: AsyncSession) -> None:
        repo = DataQualityRepository(db_session)
        run_id = uuid7()
        payload = _make_payload(run_id=run_id)

        await repo.save_summary(
            summary_id=uuid7(), run_id=run_id, workspace_id=uuid7(),
            overall_run_score=0.8, overall_run_grade="B", coverage_pct=0.8,
            publication_gate_pass=True, publication_gate_mode="PASS",
            summary_version="1.0.0", summary_hash="d", payload=payload,
        )

        deleted = await repo.delete_by_run(run_id)
        assert deleted is True
        assert await repo.get_by_run(run_id) is None

    @pytest.mark.anyio
    async def test_delete_nonexistent(self, db_session: AsyncSession) -> None:
        repo = DataQualityRepository(db_session)
        deleted = await repo.delete_by_run(uuid7())
        assert deleted is False
