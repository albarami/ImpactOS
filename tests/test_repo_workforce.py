"""Tests for workforce repositories — MVP-11.

Uses SAVEPOINT-isolated db_session from conftest.py.
"""

from uuid import uuid4

import pytest

from src.models.common import new_uuid7
from src.repositories.workforce import (
    EmploymentCoefficientsRepository,
    SaudizationRulesRepository,
    SectorOccupationBridgeRepository,
    WorkforceResultRepository,
)


# ---------------------------------------------------------------------------
# EmploymentCoefficientsRepository
# ---------------------------------------------------------------------------


class TestEmploymentCoefficientsRepository:
    @pytest.fixture
    def repo(self, db_session):
        return EmploymentCoefficientsRepository(db_session)

    async def test_create_and_get(self, repo):
        ec_id = new_uuid7()
        ws_id = uuid4()
        mv_id = uuid4()
        row = await repo.create(
            employment_coefficients_id=ec_id,
            version=1,
            model_version_id=mv_id,
            workspace_id=ws_id,
            output_unit="MILLION_SAR",
            base_year=2024,
            coefficients=[
                {
                    "sector_code": "SEC01",
                    "jobs_per_million_sar": 12.5,
                    "confidence": "HARD",
                    "source_description": "GASTAT 2024",
                },
            ],
        )
        assert row.employment_coefficients_id == ec_id
        assert row.version == 1
        assert row.output_unit == "MILLION_SAR"
        assert row.base_year == 2024

        fetched = await repo.get(ec_id, 1)
        assert fetched is not None
        assert fetched.employment_coefficients_id == ec_id

    async def test_get_nonexistent_returns_none(self, repo):
        result = await repo.get(uuid4(), 1)
        assert result is None

    async def test_get_latest(self, repo):
        ec_id = new_uuid7()
        ws_id = uuid4()
        mv_id = uuid4()
        await repo.create(
            employment_coefficients_id=ec_id, version=1,
            model_version_id=mv_id, workspace_id=ws_id,
            output_unit="SAR", base_year=2023, coefficients=[],
        )
        await repo.create(
            employment_coefficients_id=ec_id, version=2,
            model_version_id=mv_id, workspace_id=ws_id,
            output_unit="MILLION_SAR", base_year=2024,
            coefficients=[{"updated": True}],
        )
        latest = await repo.get_latest(ec_id)
        assert latest is not None
        assert latest.version == 2
        assert latest.output_unit == "MILLION_SAR"

    async def test_get_latest_nonexistent_returns_none(self, repo):
        result = await repo.get_latest(uuid4())
        assert result is None

    async def test_get_by_workspace(self, repo):
        ws_id = uuid4()
        mv_id = uuid4()
        await repo.create(
            employment_coefficients_id=new_uuid7(), version=1,
            model_version_id=mv_id, workspace_id=ws_id,
            output_unit="SAR", base_year=2024, coefficients=[],
        )
        await repo.create(
            employment_coefficients_id=new_uuid7(), version=1,
            model_version_id=mv_id, workspace_id=ws_id,
            output_unit="SAR", base_year=2024, coefficients=[],
        )
        # Different workspace
        await repo.create(
            employment_coefficients_id=new_uuid7(), version=1,
            model_version_id=mv_id, workspace_id=uuid4(),
            output_unit="SAR", base_year=2024, coefficients=[],
        )
        rows = await repo.get_by_workspace(ws_id)
        assert len(rows) == 2

    async def test_version_uniqueness(self, repo):
        ec_id = new_uuid7()
        ws_id = uuid4()
        mv_id = uuid4()
        await repo.create(
            employment_coefficients_id=ec_id, version=1,
            model_version_id=mv_id, workspace_id=ws_id,
            output_unit="SAR", base_year=2024, coefficients=[],
        )
        with pytest.raises(Exception):
            await repo.create(
                employment_coefficients_id=ec_id, version=1,
                model_version_id=mv_id, workspace_id=ws_id,
                output_unit="SAR", base_year=2024, coefficients=[],
            )

    async def test_flexjson_roundtrip(self, repo):
        ec_id = new_uuid7()
        coefficients = [
            {"sector_code": "SEC01", "jobs_per_million_sar": 12.5,
             "confidence": "HARD", "source_description": "Test"},
        ]
        await repo.create(
            employment_coefficients_id=ec_id, version=1,
            model_version_id=uuid4(), workspace_id=uuid4(),
            output_unit="MILLION_SAR", base_year=2024,
            coefficients=coefficients,
        )
        fetched = await repo.get(ec_id, 1)
        assert fetched.coefficients[0]["sector_code"] == "SEC01"
        assert fetched.coefficients[0]["jobs_per_million_sar"] == 12.5


# ---------------------------------------------------------------------------
# SectorOccupationBridgeRepository
# ---------------------------------------------------------------------------


class TestSectorOccupationBridgeRepository:
    @pytest.fixture
    def repo(self, db_session):
        return SectorOccupationBridgeRepository(db_session)

    async def test_create_and_get(self, repo):
        bridge_id = new_uuid7()
        ws_id = uuid4()
        mv_id = uuid4()
        row = await repo.create(
            bridge_id=bridge_id,
            version=1,
            model_version_id=mv_id,
            workspace_id=ws_id,
            entries=[
                {"sector_code": "SEC01", "occupation_code": "ENG",
                 "share": 0.6, "confidence": "HARD"},
            ],
        )
        assert row.bridge_id == bridge_id
        assert row.version == 1

        fetched = await repo.get(bridge_id, 1)
        assert fetched is not None

    async def test_get_nonexistent_returns_none(self, repo):
        result = await repo.get(uuid4(), 1)
        assert result is None

    async def test_get_latest(self, repo):
        bridge_id = new_uuid7()
        ws_id = uuid4()
        mv_id = uuid4()
        await repo.create(
            bridge_id=bridge_id, version=1,
            model_version_id=mv_id, workspace_id=ws_id,
            entries=[],
        )
        await repo.create(
            bridge_id=bridge_id, version=2,
            model_version_id=mv_id, workspace_id=ws_id,
            entries=[{"updated": True}],
        )
        latest = await repo.get_latest(bridge_id)
        assert latest.version == 2

    async def test_get_by_workspace(self, repo):
        ws_id = uuid4()
        mv_id = uuid4()
        await repo.create(
            bridge_id=new_uuid7(), version=1,
            model_version_id=mv_id, workspace_id=ws_id,
            entries=[],
        )
        await repo.create(
            bridge_id=new_uuid7(), version=1,
            model_version_id=mv_id, workspace_id=uuid4(),
            entries=[],
        )
        rows = await repo.get_by_workspace(ws_id)
        assert len(rows) == 1

    async def test_version_uniqueness(self, repo):
        bridge_id = new_uuid7()
        ws_id = uuid4()
        mv_id = uuid4()
        await repo.create(
            bridge_id=bridge_id, version=1,
            model_version_id=mv_id, workspace_id=ws_id,
            entries=[],
        )
        with pytest.raises(Exception):
            await repo.create(
                bridge_id=bridge_id, version=1,
                model_version_id=mv_id, workspace_id=ws_id,
                entries=[],
            )

    async def test_flexjson_roundtrip(self, repo):
        bridge_id = new_uuid7()
        entries = [
            {"sector_code": "SEC01", "occupation_code": "ENG",
             "share": 0.6, "confidence": "HARD"},
        ]
        await repo.create(
            bridge_id=bridge_id, version=1,
            model_version_id=uuid4(), workspace_id=uuid4(),
            entries=entries,
        )
        fetched = await repo.get(bridge_id, 1)
        assert fetched.entries[0]["occupation_code"] == "ENG"
        assert fetched.entries[0]["share"] == 0.6


# ---------------------------------------------------------------------------
# SaudizationRulesRepository
# ---------------------------------------------------------------------------


class TestSaudizationRulesRepository:
    @pytest.fixture
    def repo(self, db_session):
        return SaudizationRulesRepository(db_session)

    async def test_create_and_get(self, repo):
        rules_id = new_uuid7()
        ws_id = uuid4()
        row = await repo.create(
            rules_id=rules_id,
            version=1,
            workspace_id=ws_id,
            tier_assignments=[
                {"occupation_code": "ENG", "nationality_tier": "SAUDI_READY",
                 "rationale": "Test"},
            ],
            sector_targets=[
                {"sector_code": "SEC01", "target_saudi_pct": 0.30,
                 "source": "Nitaqat", "effective_year": 2025},
            ],
        )
        assert row.rules_id == rules_id
        assert row.version == 1

        fetched = await repo.get(rules_id, 1)
        assert fetched is not None

    async def test_get_latest(self, repo):
        rules_id = new_uuid7()
        ws_id = uuid4()
        await repo.create(
            rules_id=rules_id, version=1,
            workspace_id=ws_id,
            tier_assignments=[], sector_targets=[],
        )
        await repo.create(
            rules_id=rules_id, version=2,
            workspace_id=ws_id,
            tier_assignments=[{"updated": True}], sector_targets=[],
        )
        latest = await repo.get_latest(rules_id)
        assert latest.version == 2

    async def test_get_by_workspace(self, repo):
        ws_id = uuid4()
        await repo.create(
            rules_id=new_uuid7(), version=1,
            workspace_id=ws_id,
            tier_assignments=[], sector_targets=[],
        )
        # Different workspace
        await repo.create(
            rules_id=new_uuid7(), version=1,
            workspace_id=uuid4(),
            tier_assignments=[], sector_targets=[],
        )
        rows = await repo.get_by_workspace(ws_id)
        assert len(rows) == 1

    async def test_version_uniqueness(self, repo):
        rules_id = new_uuid7()
        ws_id = uuid4()
        await repo.create(
            rules_id=rules_id, version=1,
            workspace_id=ws_id,
            tier_assignments=[], sector_targets=[],
        )
        with pytest.raises(Exception):
            await repo.create(
                rules_id=rules_id, version=1,
                workspace_id=ws_id,
                tier_assignments=[], sector_targets=[],
            )

    async def test_flexjson_roundtrip(self, repo):
        rules_id = new_uuid7()
        await repo.create(
            rules_id=rules_id, version=1,
            workspace_id=uuid4(),
            tier_assignments=[
                {"occupation_code": "ENG", "nationality_tier": "SAUDI_READY"},
            ],
            sector_targets=[
                {"sector_code": "SEC01", "target_saudi_pct": 0.30,
                 "source": "Nitaqat", "effective_year": 2025},
            ],
        )
        fetched = await repo.get(rules_id, 1)
        assert fetched.tier_assignments[0]["nationality_tier"] == "SAUDI_READY"
        assert fetched.sector_targets[0]["target_saudi_pct"] == 0.30


# ---------------------------------------------------------------------------
# WorkforceResultRepository
# ---------------------------------------------------------------------------


class TestWorkforceResultRepository:
    @pytest.fixture
    def repo(self, db_session):
        return WorkforceResultRepository(db_session)

    def _make_result_kwargs(self, **overrides):
        defaults = {
            "workforce_result_id": new_uuid7(),
            "workspace_id": uuid4(),
            "run_id": uuid4(),
            "employment_coefficients_id": uuid4(),
            "employment_coefficients_version": 1,
            "bridge_id": None,
            "bridge_version": None,
            "rules_id": None,
            "rules_version": None,
            "results": {
                "sector_employment": {"SEC01": {"total_jobs": 100.0}},
            },
            "confidence_summary": {
                "output_weighted_coefficient_confidence": 0.8,
                "bridge_coverage_pct": 1.0,
                "rule_coverage_pct": 0.9,
                "overall_confidence": "HIGH",
                "data_quality_notes": [],
            },
            "data_quality_notes": [],
            "satellite_coefficients_hash": "abc123def456",
            "delta_x_source": "unconstrained",
            "feasibility_result_id": None,
        }
        defaults.update(overrides)
        return defaults

    async def test_create_and_get(self, repo):
        kwargs = self._make_result_kwargs()
        row = await repo.create(**kwargs)
        assert row.workforce_result_id == kwargs["workforce_result_id"]
        assert row.delta_x_source == "unconstrained"

        fetched = await repo.get(kwargs["workforce_result_id"])
        assert fetched is not None
        assert fetched.workforce_result_id == kwargs["workforce_result_id"]

    async def test_get_nonexistent_returns_none(self, repo):
        result = await repo.get(uuid4())
        assert result is None

    async def test_get_by_run(self, repo):
        run_id = uuid4()
        ws_id = uuid4()
        await repo.create(**self._make_result_kwargs(
            run_id=run_id, workspace_id=ws_id,
        ))
        await repo.create(**self._make_result_kwargs(
            run_id=run_id, workspace_id=ws_id,
            employment_coefficients_version=2,
        ))
        # Different run
        await repo.create(**self._make_result_kwargs())

        results = await repo.get_by_run(run_id)
        assert len(results) == 2

    async def test_get_by_workspace(self, repo):
        ws_id = uuid4()
        await repo.create(**self._make_result_kwargs(workspace_id=ws_id))
        await repo.create(**self._make_result_kwargs(workspace_id=ws_id))
        # Different workspace
        await repo.create(**self._make_result_kwargs())

        results = await repo.get_by_workspace(ws_id)
        assert len(results) == 2

    async def test_flexjson_roundtrip(self, repo):
        kwargs = self._make_result_kwargs()
        await repo.create(**kwargs)
        fetched = await repo.get(kwargs["workforce_result_id"])
        assert fetched.results["sector_employment"]["SEC01"]["total_jobs"] == 100.0
        assert fetched.confidence_summary["overall_confidence"] == "HIGH"

    async def test_nullable_bridge_rules(self, repo):
        kwargs = self._make_result_kwargs(
            bridge_id=None, bridge_version=None,
            rules_id=None, rules_version=None,
        )
        await repo.create(**kwargs)
        fetched = await repo.get(kwargs["workforce_result_id"])
        assert fetched.bridge_id is None
        assert fetched.rules_id is None

    async def test_feasible_source(self, repo):
        feas_id = uuid4()
        kwargs = self._make_result_kwargs(
            delta_x_source="feasible",
            feasibility_result_id=feas_id,
        )
        await repo.create(**kwargs)
        fetched = await repo.get(kwargs["workforce_result_id"])
        assert fetched.delta_x_source == "feasible"
        assert fetched.feasibility_result_id == feas_id

    async def test_get_existing(self, repo):
        """Amendment 9: Idempotency lookup."""
        run_id = uuid4()
        ec_id = uuid4()
        ws_id = uuid4()
        kwargs = self._make_result_kwargs(
            run_id=run_id,
            workspace_id=ws_id,
            employment_coefficients_id=ec_id,
            employment_coefficients_version=1,
            delta_x_source="unconstrained",
        )
        await repo.create(**kwargs)

        existing = await repo.get_existing(
            run_id=run_id,
            employment_coefficients_id=ec_id,
            employment_coefficients_version=1,
            delta_x_source="unconstrained",
        )
        assert existing is not None
        assert existing.workforce_result_id == kwargs["workforce_result_id"]

    async def test_get_existing_not_found(self, repo):
        result = await repo.get_existing(
            run_id=uuid4(),
            employment_coefficients_id=uuid4(),
            employment_coefficients_version=1,
            delta_x_source="unconstrained",
        )
        assert result is None
