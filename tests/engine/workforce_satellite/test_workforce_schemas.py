"""Tests for workforce result schema validation."""

from src.data.workforce.nationality_classification import NationalityTier
from src.engine.workforce_satellite.schemas import (
    AppliedOverride,
    BaselineSectorWorkforce,
    NationalitySplit,
    OccupationImpact,
    SectorWorkforceSummary,
    TrainingGapEntry,
    WorkforceResult,
)


class TestOccupationImpact:
    def test_valid_construction(self) -> None:
        oi = OccupationImpact(
            sector_code="F",
            occupation_code="7",
            occupation_label="Craft Workers",
            jobs=500.0,
            share_of_sector=0.50,
            bridge_confidence="MEDIUM",
        )
        assert oi.sector_code == "F"
        assert oi.jobs == 500.0


class TestNationalitySplit:
    def test_range_fields_present(self) -> None:
        ns = NationalitySplit(
            sector_code="F", occupation_code="7",
            tier=NationalityTier.SAUDI_TRAINABLE,
            total_jobs=100.0,
            saudi_jobs_min=20.0, saudi_jobs_mid=40.0, saudi_jobs_max=60.0,
            classification_confidence="LOW",
        )
        assert ns.saudi_jobs_min <= ns.saudi_jobs_mid <= ns.saudi_jobs_max

    def test_negative_jobs_numeric_order(self) -> None:
        """Amendment 3: min <= mid <= max even for negative jobs."""
        ns = NationalitySplit(
            sector_code="F", occupation_code="7",
            tier=NationalityTier.SAUDI_TRAINABLE,
            total_jobs=-100.0,
            saudi_jobs_min=-60.0, saudi_jobs_mid=-40.0, saudi_jobs_max=-20.0,
            classification_confidence="ASSUMED",
        )
        assert ns.saudi_jobs_min <= ns.saudi_jobs_mid <= ns.saudi_jobs_max


class TestSectorWorkforceSummary:
    def test_compliance_status_values(self) -> None:
        for status in [
            "COMPLIANT", "AT_RISK", "NON_COMPLIANT",
            "NO_TARGET", "INSUFFICIENT_DATA",
        ]:
            s = SectorWorkforceSummary(
                sector_code="F",
                total_jobs=100.0,
                nitaqat_compliance_status=status,
            )
            assert s.nitaqat_compliance_status == status

    def test_nitaqat_target_range_preserved(self) -> None:
        """Amendment 2: ranges not collapsed to single number."""
        s = SectorWorkforceSummary(
            sector_code="F",
            total_jobs=100.0,
            nitaqat_target_effective=0.12,
            nitaqat_target_range=(0.08, 0.16),
        )
        assert s.nitaqat_target_range == (0.08, 0.16)

    def test_has_baseline_flag(self) -> None:
        s = SectorWorkforceSummary(
            sector_code="F", total_jobs=100.0, has_baseline=True,
        )
        assert s.has_baseline is True


class TestTrainingGapEntry:
    def test_typed_model(self) -> None:
        """Amendment 5: typed, not dict."""
        e = TrainingGapEntry(
            sector_code="F", occupation_code="7",
            tier=NationalityTier.SAUDI_TRAINABLE,
            total_jobs=500.0, gap_jobs=100.0,
            nitaqat_target=0.12,
        )
        assert e.gap_jobs == 100.0


class TestAppliedOverride:
    def test_typed_model(self) -> None:
        """Amendment 5: typed, not dict."""
        o = AppliedOverride(
            sector_code="F", occupation_code="7",
            original_tier=NationalityTier.EXPAT_RELIANT,
            override_tier=NationalityTier.SAUDI_TRAINABLE,
            overridden_by="analyst",
            engagement_id="eng-001",
            rationale="Training program available",
        )
        assert o.override_tier == NationalityTier.SAUDI_TRAINABLE


class TestWorkforceResult:
    def test_default_known_limitations(self) -> None:
        r = WorkforceResult(known_limitations=["test limitation"])
        assert len(r.known_limitations) == 1

    def test_result_granularity_default(self) -> None:
        """Amendment 8: default is section."""
        r = WorkforceResult()
        assert r.result_granularity == "section"

    def test_overall_confidence_default(self) -> None:
        r = WorkforceResult()
        assert r.overall_confidence == "ASSUMED"


class TestBaselineSectorWorkforce:
    def test_amendment_1_fields(self) -> None:
        bl = BaselineSectorWorkforce(
            sector_code="F",
            total_employment=5000.0,
            saudi_employment=400.0,
            saudi_share=0.08,
            source="GOSI",
            year=2023,
        )
        assert bl.saudi_share == 0.08
