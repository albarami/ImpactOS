"""Tests for Pydantic workforce/saudization schemas — MVP-11.

Covers:
- NationalityTier and WorkforceConfidenceLevel enum values
- SectorEmploymentCoefficient construction and validation
- BridgeEntry share bounds and evidence_refs [Amend 8]
- TierAssignment construction
- SectorSaudizationTarget bounds
- EmploymentCoefficients versioning, output_unit [Amend 2], next_version
- SectorOccupationBridge share validator [Amend 4]
- SaudizationRules versioning (no model_version_id)
- SectorEmployment immutability
- NationalitySplit with unclassified bucket [Amend 5]
- SaudizationGap min/max range [Amend 6], training fields [Amend 7]
- SensitivityEnvelope ordering for positive and negative [Amend 3]
- WorkforceConfidenceSummary construction
- WorkforceResult with delta_x_source [Amend 1], unit fields [Amend 2]
"""

from uuid import uuid4

import pytest

from src.models.common import ConstraintConfidence
from src.models.workforce import (
    BridgeEntry,
    EmploymentCoefficients,
    NationalitySplit,
    NationalityTier,
    OccupationBreakdown,
    SaudizationGap,
    SaudizationRules,
    SectorEmployment,
    SectorEmploymentCoefficient,
    SectorOccupationBridge,
    SectorSaudizationTarget,
    SensitivityEnvelope,
    TierAssignment,
    WorkforceConfidenceLevel,
    WorkforceConfidenceSummary,
    WorkforceResult,
)


class TestNationalityTierEnum:
    def test_all_values_present(self):
        values = {e.value for e in NationalityTier}
        assert values == {"SAUDI_READY", "SAUDI_TRAINABLE", "EXPAT_RELIANT"}

    def test_is_str_enum(self):
        assert NationalityTier.SAUDI_READY == "SAUDI_READY"


class TestWorkforceConfidenceLevelEnum:
    def test_all_values_present(self):
        values = {e.value for e in WorkforceConfidenceLevel}
        assert values == {"HIGH", "MEDIUM", "LOW"}

    def test_is_str_enum(self):
        assert WorkforceConfidenceLevel.HIGH == "HIGH"


class TestSectorEmploymentCoefficient:
    def test_valid_construction(self):
        c = SectorEmploymentCoefficient(
            sector_code="SEC01",
            jobs_per_million_sar=12.5,
            confidence=ConstraintConfidence.HARD,
            source_description="GASTAT 2024",
        )
        assert c.sector_code == "SEC01"
        assert c.jobs_per_million_sar == 12.5
        assert c.confidence == ConstraintConfidence.HARD

    def test_jobs_per_million_sar_must_be_positive(self):
        with pytest.raises(ValueError):
            SectorEmploymentCoefficient(
                sector_code="SEC01",
                jobs_per_million_sar=-1.0,
                confidence=ConstraintConfidence.HARD,
            )

    def test_uses_constraint_confidence(self):
        c = SectorEmploymentCoefficient(
            sector_code="SEC01",
            jobs_per_million_sar=10.0,
            confidence=ConstraintConfidence.ESTIMATED,
        )
        assert isinstance(c.confidence, ConstraintConfidence)

    def test_evidence_refs_default_empty(self):
        c = SectorEmploymentCoefficient(
            sector_code="SEC01",
            jobs_per_million_sar=10.0,
            confidence=ConstraintConfidence.HARD,
        )
        assert c.evidence_refs == []

    def test_evidence_refs_populated(self):
        ref = uuid4()
        c = SectorEmploymentCoefficient(
            sector_code="SEC01",
            jobs_per_million_sar=10.0,
            confidence=ConstraintConfidence.HARD,
            evidence_refs=[ref],
        )
        assert len(c.evidence_refs) == 1


class TestBridgeEntry:
    def test_valid_construction(self):
        b = BridgeEntry(
            sector_code="SEC01",
            occupation_code="OCC01",
            share=0.3,
            confidence=ConstraintConfidence.ESTIMATED,
        )
        assert b.share == 0.3

    def test_share_bounds(self):
        with pytest.raises(ValueError):
            BridgeEntry(
                sector_code="SEC01",
                occupation_code="OCC01",
                share=1.5,
                confidence=ConstraintConfidence.HARD,
            )
        with pytest.raises(ValueError):
            BridgeEntry(
                sector_code="SEC01",
                occupation_code="OCC01",
                share=-0.1,
                confidence=ConstraintConfidence.HARD,
            )

    def test_evidence_refs(self):
        ref = uuid4()
        b = BridgeEntry(
            sector_code="SEC01",
            occupation_code="OCC01",
            share=0.5,
            confidence=ConstraintConfidence.HARD,
            evidence_refs=[ref],
        )
        assert len(b.evidence_refs) == 1


class TestTierAssignment:
    def test_valid_construction(self):
        t = TierAssignment(
            occupation_code="OCC01",
            nationality_tier=NationalityTier.SAUDI_READY,
            rationale="Established domestic training pipeline",
        )
        assert t.nationality_tier == NationalityTier.SAUDI_READY

    def test_evidence_refs(self):
        ref = uuid4()
        t = TierAssignment(
            occupation_code="OCC01",
            nationality_tier=NationalityTier.EXPAT_RELIANT,
            evidence_refs=[ref],
        )
        assert len(t.evidence_refs) == 1


class TestSectorSaudizationTarget:
    def test_valid_construction(self):
        t = SectorSaudizationTarget(
            sector_code="SEC01",
            target_saudi_pct=0.30,
            source="Nitaqat",
            effective_year=2025,
        )
        assert t.target_saudi_pct == 0.30

    def test_target_pct_bounds(self):
        with pytest.raises(ValueError):
            SectorSaudizationTarget(
                sector_code="SEC01",
                target_saudi_pct=1.5,
                source="Nitaqat",
                effective_year=2025,
            )

    def test_evidence_refs(self):
        ref = uuid4()
        t = SectorSaudizationTarget(
            sector_code="SEC01",
            target_saudi_pct=0.30,
            source="MHRSD",
            effective_year=2025,
            evidence_refs=[ref],
        )
        assert len(t.evidence_refs) == 1


class TestEmploymentCoefficients:
    def test_valid_construction(self):
        ec = EmploymentCoefficients(
            model_version_id=uuid4(),
            workspace_id=uuid4(),
            output_unit="MILLION_SAR",
            base_year=2024,
            coefficients=[
                SectorEmploymentCoefficient(
                    sector_code="SEC01",
                    jobs_per_million_sar=12.5,
                    confidence=ConstraintConfidence.HARD,
                ),
            ],
        )
        assert ec.version == 1
        assert ec.output_unit == "MILLION_SAR"
        assert ec.base_year == 2024
        assert len(ec.coefficients) == 1

    def test_default_version_is_1(self):
        ec = EmploymentCoefficients(
            model_version_id=uuid4(),
            workspace_id=uuid4(),
            output_unit="SAR",
            base_year=2024,
            coefficients=[],
        )
        assert ec.version == 1

    def test_next_version_increments(self):
        ec = EmploymentCoefficients(
            model_version_id=uuid4(),
            workspace_id=uuid4(),
            output_unit="SAR",
            base_year=2024,
            coefficients=[],
        )
        v2 = ec.next_version()
        assert v2.version == 2
        assert v2.employment_coefficients_id == ec.employment_coefficients_id
        assert v2.workspace_id == ec.workspace_id

    def test_output_unit_literal(self):
        """output_unit must be SAR or MILLION_SAR."""
        with pytest.raises(ValueError):
            EmploymentCoefficients(
                model_version_id=uuid4(),
                workspace_id=uuid4(),
                output_unit="INVALID",
                base_year=2024,
                coefficients=[],
            )


class TestSectorOccupationBridge:
    def test_valid_construction(self):
        bridge = SectorOccupationBridge(
            model_version_id=uuid4(),
            workspace_id=uuid4(),
            entries=[
                BridgeEntry(
                    sector_code="SEC01",
                    occupation_code="OCC01",
                    share=0.6,
                    confidence=ConstraintConfidence.HARD,
                ),
                BridgeEntry(
                    sector_code="SEC01",
                    occupation_code="OCC02",
                    share=0.3,
                    confidence=ConstraintConfidence.ESTIMATED,
                ),
            ],
        )
        assert bridge.version == 1
        assert len(bridge.entries) == 2

    def test_next_version(self):
        bridge = SectorOccupationBridge(
            model_version_id=uuid4(),
            workspace_id=uuid4(),
            entries=[],
        )
        v2 = bridge.next_version()
        assert v2.version == 2
        assert v2.bridge_id == bridge.bridge_id

    def test_shares_per_sector_valid_under_1(self):
        """Shares summing to < 1.0 is allowed (UNMAPPED residual)."""
        bridge = SectorOccupationBridge(
            model_version_id=uuid4(),
            workspace_id=uuid4(),
            entries=[
                BridgeEntry(
                    sector_code="SEC01",
                    occupation_code="OCC01",
                    share=0.7,
                    confidence=ConstraintConfidence.HARD,
                ),
            ],
        )
        assert len(bridge.entries) == 1

    def test_shares_exceed_1_raises(self):
        """Per-sector shares summing to > 1.0 + tolerance should raise."""
        with pytest.raises(ValueError, match="shares.*exceed"):
            SectorOccupationBridge(
                model_version_id=uuid4(),
                workspace_id=uuid4(),
                entries=[
                    BridgeEntry(
                        sector_code="SEC01",
                        occupation_code="OCC01",
                        share=0.6,
                        confidence=ConstraintConfidence.HARD,
                    ),
                    BridgeEntry(
                        sector_code="SEC01",
                        occupation_code="OCC02",
                        share=0.5,
                        confidence=ConstraintConfidence.HARD,
                    ),
                ],
            )


class TestSaudizationRules:
    def test_valid_construction(self):
        rules = SaudizationRules(
            workspace_id=uuid4(),
            tier_assignments=[
                TierAssignment(
                    occupation_code="OCC01",
                    nationality_tier=NationalityTier.SAUDI_READY,
                ),
            ],
            sector_targets=[
                SectorSaudizationTarget(
                    sector_code="SEC01",
                    target_saudi_pct=0.30,
                    source="Nitaqat",
                    effective_year=2025,
                ),
            ],
        )
        assert rules.version == 1
        assert len(rules.tier_assignments) == 1
        assert len(rules.sector_targets) == 1

    def test_next_version(self):
        rules = SaudizationRules(
            workspace_id=uuid4(),
            tier_assignments=[],
            sector_targets=[],
        )
        v2 = rules.next_version()
        assert v2.version == 2
        assert v2.rules_id == rules.rules_id


class TestSectorEmployment:
    def test_frozen_immutability(self):
        se = SectorEmployment(
            sector_code="SEC01",
            total_jobs=1250.0,
            direct_jobs=800.0,
            indirect_jobs=450.0,
            confidence=ConstraintConfidence.HARD,
        )
        with pytest.raises(Exception):
            se.total_jobs = 9999


class TestOccupationBreakdown:
    def test_valid_construction(self):
        ob = OccupationBreakdown(
            occupation_code="OCC01",
            jobs=375.0,
            share_of_sector=0.3,
            confidence=ConstraintConfidence.ESTIMATED,
        )
        assert ob.jobs == 375.0
        assert ob.share_of_sector == 0.3


class TestNationalitySplit:
    def test_valid_construction(self):
        ns = NationalitySplit(
            sector_code="SEC01",
            total_jobs=1000.0,
            saudi_ready=300.0,
            saudi_trainable=200.0,
            expat_reliant=400.0,
            unclassified=100.0,
        )
        assert ns.total_jobs == 1000.0

    def test_sum_mismatch_raises(self):
        """total must equal sum of four buckets (within tolerance)."""
        with pytest.raises(ValueError, match="total_jobs"):
            NationalitySplit(
                sector_code="SEC01",
                total_jobs=1000.0,
                saudi_ready=300.0,
                saudi_trainable=200.0,
                expat_reliant=400.0,
                unclassified=200.0,  # sum = 1100 != 1000
            )

    def test_sum_within_tolerance(self):
        """Small floating-point deviations should be accepted."""
        ns = NationalitySplit(
            sector_code="SEC01",
            total_jobs=1000.0,
            saudi_ready=300.0,
            saudi_trainable=200.0,
            expat_reliant=499.9999999,
            unclassified=0.0000001,
        )
        assert ns.total_jobs == 1000.0


class TestSaudizationGap:
    def test_valid_construction(self):
        sg = SaudizationGap(
            sector_code="SEC01",
            projected_saudi_pct_min=0.20,
            projected_saudi_pct_max=0.35,
            target_saudi_pct=0.30,
            gap_pct_min=-0.05,
            gap_pct_max=0.10,
            gap_jobs_min=-50,
            gap_jobs_max=100,
            achievability_assessment="ACHIEVABLE_WITH_TRAINING",
        )
        assert sg.projected_saudi_pct_min == 0.20
        assert sg.projected_saudi_pct_max == 0.35
        assert sg.achievability_assessment == "ACHIEVABLE_WITH_TRAINING"

    def test_training_fields_default_none(self):
        sg = SaudizationGap(
            sector_code="SEC01",
            projected_saudi_pct_min=0.20,
            projected_saudi_pct_max=0.35,
            target_saudi_pct=0.30,
            gap_pct_min=-0.05,
            gap_pct_max=0.10,
            gap_jobs_min=-50,
            gap_jobs_max=100,
            achievability_assessment="MODERATE_GAP",
        )
        assert sg.estimated_training_duration_months is None
        assert sg.training_capacity_note == ""

    def test_training_fields_populated(self):
        sg = SaudizationGap(
            sector_code="SEC01",
            projected_saudi_pct_min=0.10,
            projected_saudi_pct_max=0.20,
            target_saudi_pct=0.40,
            gap_pct_min=0.20,
            gap_pct_max=0.30,
            gap_jobs_min=200,
            gap_jobs_max=300,
            achievability_assessment="SIGNIFICANT_GAP",
            estimated_training_duration_months=24,
            training_capacity_note="Requires expansion of TVTC pipeline",
        )
        assert sg.estimated_training_duration_months == 24


class TestSensitivityEnvelope:
    def test_valid_construction(self):
        se = SensitivityEnvelope(
            sector_code="SEC01",
            base_jobs=1000.0,
            low_jobs=950.0,
            high_jobs=1050.0,
            confidence_band_pct=0.05,
        )
        assert se.low_jobs <= se.base_jobs <= se.high_jobs

    def test_ordering_violation_raises(self):
        """low must be <= base <= high."""
        with pytest.raises(ValueError, match="low_jobs"):
            SensitivityEnvelope(
                sector_code="SEC01",
                base_jobs=1000.0,
                low_jobs=1050.0,  # > base
                high_jobs=1100.0,
                confidence_band_pct=0.05,
            )


class TestWorkforceConfidenceSummary:
    def test_valid_construction(self):
        wcs = WorkforceConfidenceSummary(
            output_weighted_coefficient_confidence=0.75,
            bridge_coverage_pct=0.80,
            rule_coverage_pct=0.60,
            overall_confidence=WorkforceConfidenceLevel.MEDIUM,
            data_quality_notes=["Bridge missing for SEC03"],
        )
        assert wcs.overall_confidence == WorkforceConfidenceLevel.MEDIUM
        assert len(wcs.data_quality_notes) == 1


class TestWorkforceResult:
    def _make_result(self, **overrides):
        defaults = dict(
            run_id=uuid4(),
            workspace_id=uuid4(),
            sector_employment={},
            occupation_breakdowns={},
            nationality_splits={},
            saudization_gaps={},
            sensitivity_envelopes={},
            confidence_summary=WorkforceConfidenceSummary(
                output_weighted_coefficient_confidence=0.8,
                bridge_coverage_pct=1.0,
                rule_coverage_pct=0.9,
                overall_confidence=WorkforceConfidenceLevel.HIGH,
                data_quality_notes=[],
            ),
            employment_coefficients_id=uuid4(),
            employment_coefficients_version=1,
            bridge_id=None,
            bridge_version=None,
            rules_id=None,
            rules_version=None,
            satellite_coefficients_hash="abc123def456",
            data_quality_notes=[],
            delta_x_source="unconstrained",
            feasibility_result_id=None,
            delta_x_unit="SAR",
            coefficient_unit="MILLION_SAR",
        )
        defaults.update(overrides)
        return WorkforceResult(**defaults)

    def test_valid_construction(self):
        r = self._make_result()
        assert r.delta_x_source == "unconstrained"
        assert r.feasibility_result_id is None

    def test_immutable(self):
        r = self._make_result()
        with pytest.raises(Exception):
            r.delta_x_source = "feasible"

    def test_feasible_source(self):
        feas_id = uuid4()
        r = self._make_result(
            delta_x_source="feasible",
            feasibility_result_id=feas_id,
        )
        assert r.delta_x_source == "feasible"
        assert r.feasibility_result_id == feas_id

    def test_serialization_roundtrip(self):
        r = self._make_result()
        data = r.model_dump(mode="json")
        assert "workforce_result_id" in data
        assert data["delta_x_source"] == "unconstrained"
        assert data["coefficient_unit"] == "MILLION_SAR"
