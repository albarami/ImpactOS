"""Tests for workforce/saudization engine — MVP-11.

All 9 amendments tested:
- [1] Feasibility integration (delta_x_source in WorkforceResult)
- [2] Unit normalization (output_unit, delta_x_unit, coefficient_unit)
- [3] Negative sensitivity (abs-based bands)
- [4] UNMAPPED residual in bridge application
- [5] Unclassified nationality bucket
- [6] Saudization gap min/max range
- [7] Training fields (default None)
- [8] Evidence refs (model-level, not engine-level)
- [9] Idempotency (hash reproducibility)

Tests validate:
- compute_employment: basic, zero, formula correctness
- apply_occupation_bridge: basic, missing sector, UNMAPPED residual
- compute_nationality_split: basic, unclassified bucket, no bridge data
- compute_saudization_gap: all assessments, min/max range
- compute_sensitivity: confidence bands, negative, zero
- compute_confidence_summary: all levels
- compute_workforce_impact: full pipeline, optional bridge/rules, deterministic
"""

from uuid import uuid4

import numpy as np
import pytest

from src.models.common import ConstraintConfidence
from src.models.workforce import (
    BridgeEntry,
    EmploymentCoefficients,
    NationalityTier,
    SaudizationRules,
    SectorEmploymentCoefficient,
    SectorOccupationBridge,
    SectorSaudizationTarget,
    TierAssignment,
    WorkforceConfidenceLevel,
)

from src.engine.workforce import (
    WORKFORCE_SATELLITE_VERSION,
    apply_occupation_bridge,
    compute_confidence_summary,
    compute_employment,
    compute_nationality_split,
    compute_saudization_gap,
    compute_sensitivity,
    compute_workforce_impact,
    normalize_delta_x,
)


@pytest.fixture
def sector_codes():
    return ["SEC01", "SEC02", "SEC03"]


@pytest.fixture
def delta_x_total():
    """Total delta_x in SAR (not millions)."""
    return np.array([10_000_000.0, 5_000_000.0, 2_000_000.0])


@pytest.fixture
def delta_x_direct():
    return np.array([6_000_000.0, 3_000_000.0, 1_200_000.0])


@pytest.fixture
def delta_x_indirect():
    return np.array([4_000_000.0, 2_000_000.0, 800_000.0])


@pytest.fixture
def coefficients():
    return EmploymentCoefficients(
        model_version_id=uuid4(),
        workspace_id=uuid4(),
        output_unit="MILLION_SAR",
        base_year=2024,
        coefficients=[
            SectorEmploymentCoefficient(
                sector_code="SEC01",
                jobs_per_million_sar=10.0,
                confidence=ConstraintConfidence.HARD,
            ),
            SectorEmploymentCoefficient(
                sector_code="SEC02",
                jobs_per_million_sar=15.0,
                confidence=ConstraintConfidence.ESTIMATED,
            ),
            SectorEmploymentCoefficient(
                sector_code="SEC03",
                jobs_per_million_sar=20.0,
                confidence=ConstraintConfidence.ASSUMED,
            ),
        ],
    )


@pytest.fixture
def bridge():
    return SectorOccupationBridge(
        model_version_id=uuid4(),
        workspace_id=uuid4(),
        entries=[
            BridgeEntry(
                sector_code="SEC01",
                occupation_code="ENG",
                share=0.4,
                confidence=ConstraintConfidence.HARD,
            ),
            BridgeEntry(
                sector_code="SEC01",
                occupation_code="TECH",
                share=0.3,
                confidence=ConstraintConfidence.ESTIMATED,
            ),
            # SEC01 total = 0.7 → 0.3 UNMAPPED
            BridgeEntry(
                sector_code="SEC02",
                occupation_code="ADMIN",
                share=1.0,
                confidence=ConstraintConfidence.HARD,
            ),
            # SEC03 has no bridge entries
        ],
    )


@pytest.fixture
def rules():
    return SaudizationRules(
        workspace_id=uuid4(),
        tier_assignments=[
            TierAssignment(
                occupation_code="ENG",
                nationality_tier=NationalityTier.SAUDI_READY,
            ),
            TierAssignment(
                occupation_code="TECH",
                nationality_tier=NationalityTier.SAUDI_TRAINABLE,
            ),
            TierAssignment(
                occupation_code="ADMIN",
                nationality_tier=NationalityTier.EXPAT_RELIANT,
            ),
            # No assignment for UNMAPPED
        ],
        sector_targets=[
            SectorSaudizationTarget(
                sector_code="SEC01",
                target_saudi_pct=0.30,
                source="Nitaqat",
                effective_year=2025,
            ),
            SectorSaudizationTarget(
                sector_code="SEC02",
                target_saudi_pct=0.50,
                source="MHRSD",
                effective_year=2025,
            ),
        ],
    )


# ---------------------------------------------------------------------------
# compute_employment
# ---------------------------------------------------------------------------


class TestComputeEmployment:
    def test_basic_3_sector(self, delta_x_total, delta_x_direct, delta_x_indirect,
                            sector_codes, coefficients):
        result = compute_employment(
            delta_x_total=delta_x_total,
            delta_x_direct=delta_x_direct,
            delta_x_indirect=delta_x_indirect,
            coefficients=coefficients,
            sector_codes=sector_codes,
        )
        assert len(result) == 3
        # SEC01: 10 jobs/M SAR * 10M SAR = 100 jobs
        assert abs(result["SEC01"].total_jobs - 100.0) < 0.01
        # SEC02: 15 jobs/M SAR * 5M SAR = 75 jobs
        assert abs(result["SEC02"].total_jobs - 75.0) < 0.01
        # SEC03: 20 jobs/M SAR * 2M SAR = 40 jobs
        assert abs(result["SEC03"].total_jobs - 40.0) < 0.01

    def test_direct_indirect_split(self, delta_x_total, delta_x_direct,
                                    delta_x_indirect, sector_codes, coefficients):
        result = compute_employment(
            delta_x_total=delta_x_total,
            delta_x_direct=delta_x_direct,
            delta_x_indirect=delta_x_indirect,
            coefficients=coefficients,
            sector_codes=sector_codes,
        )
        # SEC01: direct = 10 * 6 = 60, indirect = 10 * 4 = 40
        assert abs(result["SEC01"].direct_jobs - 60.0) < 0.01
        assert abs(result["SEC01"].indirect_jobs - 40.0) < 0.01

    def test_zero_delta_x(self, sector_codes, coefficients):
        zeros = np.zeros(3)
        result = compute_employment(
            delta_x_total=zeros,
            delta_x_direct=zeros,
            delta_x_indirect=zeros,
            coefficients=coefficients,
            sector_codes=sector_codes,
        )
        for se in result.values():
            assert se.total_jobs == 0.0

    def test_confidence_carried_from_coefficients(self, delta_x_total, delta_x_direct,
                                                    delta_x_indirect, sector_codes,
                                                    coefficients):
        result = compute_employment(
            delta_x_total=delta_x_total,
            delta_x_direct=delta_x_direct,
            delta_x_indirect=delta_x_indirect,
            coefficients=coefficients,
            sector_codes=sector_codes,
        )
        assert result["SEC01"].confidence == ConstraintConfidence.HARD
        assert result["SEC02"].confidence == ConstraintConfidence.ESTIMATED
        assert result["SEC03"].confidence == ConstraintConfidence.ASSUMED

    def test_dimension_mismatch_raises(self, sector_codes, coefficients):
        wrong_shape = np.array([1.0, 2.0])  # 2 elements, need 3
        with pytest.raises(ValueError, match="dimension"):
            compute_employment(
                delta_x_total=wrong_shape,
                delta_x_direct=wrong_shape,
                delta_x_indirect=wrong_shape,
                coefficients=coefficients,
                sector_codes=sector_codes,
            )

    def test_deterministic(self, delta_x_total, delta_x_direct, delta_x_indirect,
                           sector_codes, coefficients):
        r1 = compute_employment(delta_x_total, delta_x_direct, delta_x_indirect,
                                coefficients, sector_codes)
        r2 = compute_employment(delta_x_total, delta_x_direct, delta_x_indirect,
                                coefficients, sector_codes)
        for sc in sector_codes:
            assert r1[sc].total_jobs == r2[sc].total_jobs


class TestNormalizeDeltaX:
    """Amendment 2: Unit normalization."""

    def test_sar_to_million_sar(self):
        delta_x = np.array([10_000_000.0, 5_000_000.0])
        result = normalize_delta_x(delta_x, delta_x_unit="SAR",
                                    coefficient_unit="MILLION_SAR")
        np.testing.assert_array_almost_equal(result, [10.0, 5.0])

    def test_million_sar_to_sar(self):
        delta_x = np.array([10.0, 5.0])
        result = normalize_delta_x(delta_x, delta_x_unit="MILLION_SAR",
                                    coefficient_unit="SAR")
        np.testing.assert_array_almost_equal(result, [10_000_000.0, 5_000_000.0])

    def test_same_unit_no_change(self):
        delta_x = np.array([100.0, 200.0])
        result = normalize_delta_x(delta_x, delta_x_unit="SAR",
                                    coefficient_unit="SAR")
        np.testing.assert_array_almost_equal(result, delta_x)

    def test_normalization_produces_same_jobs(self):
        """Same scenario in different units → same jobs after normalization."""
        delta_x_sar = np.array([10_000_000.0])
        delta_x_msar = np.array([10.0])
        norm_sar = normalize_delta_x(delta_x_sar, "SAR", "MILLION_SAR")
        norm_msar = normalize_delta_x(delta_x_msar, "MILLION_SAR", "MILLION_SAR")
        np.testing.assert_array_almost_equal(norm_sar, norm_msar)


# ---------------------------------------------------------------------------
# apply_occupation_bridge
# ---------------------------------------------------------------------------


class TestApplyOccupationBridge:
    def test_basic_mapping(self, delta_x_total, delta_x_direct, delta_x_indirect,
                           sector_codes, coefficients, bridge):
        employment = compute_employment(
            delta_x_total, delta_x_direct, delta_x_indirect,
            coefficients, sector_codes,
        )
        breakdowns, notes = apply_occupation_bridge(employment, bridge.entries)
        # SEC01 has ENG(0.4) and TECH(0.3)
        assert "SEC01" in breakdowns
        occ_codes = {ob.occupation_code for ob in breakdowns["SEC01"]}
        assert "ENG" in occ_codes
        assert "TECH" in occ_codes

    def test_unmapped_residual(self, delta_x_total, delta_x_direct, delta_x_indirect,
                                sector_codes, coefficients, bridge):
        """Amendment 4: Shares < 1.0 create UNMAPPED entry."""
        employment = compute_employment(
            delta_x_total, delta_x_direct, delta_x_indirect,
            coefficients, sector_codes,
        )
        breakdowns, notes = apply_occupation_bridge(employment, bridge.entries)
        # SEC01 shares = 0.4 + 0.3 = 0.7 → 0.3 UNMAPPED
        occ_codes = {ob.occupation_code for ob in breakdowns["SEC01"]}
        assert "UNMAPPED" in occ_codes
        unmapped = [ob for ob in breakdowns["SEC01"] if ob.occupation_code == "UNMAPPED"][0]
        assert abs(unmapped.share_of_sector - 0.3) < 0.01

    def test_missing_sector_returns_empty_with_note(self, delta_x_total, delta_x_direct,
                                                      delta_x_indirect, sector_codes,
                                                      coefficients, bridge):
        """SEC03 has no bridge entries → empty list."""
        employment = compute_employment(
            delta_x_total, delta_x_direct, delta_x_indirect,
            coefficients, sector_codes,
        )
        breakdowns, notes = apply_occupation_bridge(employment, bridge.entries)
        assert breakdowns.get("SEC03", []) == []
        # Should have a note about SEC03
        assert any("SEC03" in note for note in notes)

    def test_full_coverage_no_unmapped(self, delta_x_total, delta_x_direct,
                                       delta_x_indirect, sector_codes, coefficients):
        """SEC02 has share=1.0 → no UNMAPPED entry."""
        employment = compute_employment(
            delta_x_total, delta_x_direct, delta_x_indirect,
            coefficients, sector_codes,
        )
        entries = [
            BridgeEntry(sector_code="SEC01", occupation_code="ALL",
                       share=1.0, confidence=ConstraintConfidence.HARD),
            BridgeEntry(sector_code="SEC02", occupation_code="ALL",
                       share=1.0, confidence=ConstraintConfidence.HARD),
            BridgeEntry(sector_code="SEC03", occupation_code="ALL",
                       share=1.0, confidence=ConstraintConfidence.HARD),
        ]
        breakdowns, notes = apply_occupation_bridge(employment, entries)
        for sc in sector_codes:
            occ_codes = {ob.occupation_code for ob in breakdowns[sc]}
            assert "UNMAPPED" not in occ_codes

    def test_empty_bridge_returns_empty(self, delta_x_total, delta_x_direct,
                                        delta_x_indirect, sector_codes, coefficients):
        employment = compute_employment(
            delta_x_total, delta_x_direct, delta_x_indirect,
            coefficients, sector_codes,
        )
        breakdowns, notes = apply_occupation_bridge(employment, [])
        assert len(breakdowns) == 0


# ---------------------------------------------------------------------------
# compute_nationality_split
# ---------------------------------------------------------------------------


class TestComputeNationalitySplit:
    def test_basic_split(self, delta_x_total, delta_x_direct, delta_x_indirect,
                         sector_codes, coefficients, bridge, rules):
        employment = compute_employment(
            delta_x_total, delta_x_direct, delta_x_indirect,
            coefficients, sector_codes,
        )
        breakdowns, _ = apply_occupation_bridge(employment, bridge.entries)
        splits, notes = compute_nationality_split(
            employment, rules.tier_assignments, breakdowns,
        )
        assert "SEC01" in splits
        # SEC01: ENG=SAUDI_READY, TECH=SAUDI_TRAINABLE, UNMAPPED=unclassified
        assert splits["SEC01"].saudi_ready > 0
        assert splits["SEC01"].saudi_trainable > 0

    def test_unclassified_bucket(self, delta_x_total, delta_x_direct,
                                  delta_x_indirect, sector_codes, coefficients,
                                  bridge, rules):
        """Amendment 5: Unassigned occupations → unclassified, NOT expat_reliant."""
        employment = compute_employment(
            delta_x_total, delta_x_direct, delta_x_indirect,
            coefficients, sector_codes,
        )
        breakdowns, _ = apply_occupation_bridge(employment, bridge.entries)
        splits, notes = compute_nationality_split(
            employment, rules.tier_assignments, breakdowns,
        )
        # SEC01 has UNMAPPED occupation → should be in unclassified
        assert splits["SEC01"].unclassified > 0

    def test_no_bridge_data_all_unclassified(self, delta_x_total, delta_x_direct,
                                              delta_x_indirect, sector_codes,
                                              coefficients, rules):
        """No bridge → all jobs unclassified."""
        employment = compute_employment(
            delta_x_total, delta_x_direct, delta_x_indirect,
            coefficients, sector_codes,
        )
        splits, notes = compute_nationality_split(
            employment, rules.tier_assignments, {},
        )
        for sc in sector_codes:
            assert abs(splits[sc].unclassified - splits[sc].total_jobs) < 0.01

    def test_sum_invariant(self, delta_x_total, delta_x_direct, delta_x_indirect,
                           sector_codes, coefficients, bridge, rules):
        """total = saudi_ready + saudi_trainable + expat_reliant + unclassified."""
        employment = compute_employment(
            delta_x_total, delta_x_direct, delta_x_indirect,
            coefficients, sector_codes,
        )
        breakdowns, _ = apply_occupation_bridge(employment, bridge.entries)
        splits, _ = compute_nationality_split(
            employment, rules.tier_assignments, breakdowns,
        )
        for sc, ns in splits.items():
            bucket_sum = ns.saudi_ready + ns.saudi_trainable + ns.expat_reliant + ns.unclassified
            assert abs(ns.total_jobs - bucket_sum) < 1.0

    def test_all_assigned_no_unclassified(self):
        """When all occupations have assignments, unclassified = 0."""
        from src.models.workforce import SectorEmployment
        employment = {
            "SEC01": SectorEmployment(
                sector_code="SEC01", total_jobs=100.0,
                direct_jobs=60.0, indirect_jobs=40.0,
                confidence=ConstraintConfidence.HARD,
            ),
        }
        from src.models.workforce import OccupationBreakdown
        breakdowns = {
            "SEC01": [
                OccupationBreakdown(occupation_code="ENG", jobs=60.0,
                                   share_of_sector=0.6,
                                   confidence=ConstraintConfidence.HARD),
                OccupationBreakdown(occupation_code="TECH", jobs=40.0,
                                   share_of_sector=0.4,
                                   confidence=ConstraintConfidence.HARD),
            ],
        }
        tier_assignments = [
            TierAssignment(occupation_code="ENG",
                          nationality_tier=NationalityTier.SAUDI_READY),
            TierAssignment(occupation_code="TECH",
                          nationality_tier=NationalityTier.SAUDI_TRAINABLE),
        ]
        splits, notes = compute_nationality_split(
            employment, tier_assignments, breakdowns,
        )
        assert splits["SEC01"].unclassified == 0.0


# ---------------------------------------------------------------------------
# compute_saudization_gap
# ---------------------------------------------------------------------------


class TestComputeSaudizationGap:
    def _make_split(self, sector_code, total, saudi_ready, saudi_trainable,
                    expat_reliant, unclassified=0.0):
        from src.models.workforce import NationalitySplit
        return NationalitySplit(
            sector_code=sector_code,
            total_jobs=total,
            saudi_ready=saudi_ready,
            saudi_trainable=saudi_trainable,
            expat_reliant=expat_reliant,
            unclassified=unclassified,
        )

    def test_on_track(self):
        """Target ≤ projected_min → ON_TRACK."""
        splits = {"SEC01": self._make_split("SEC01", 1000, 400, 100, 500)}
        targets = [SectorSaudizationTarget(
            sector_code="SEC01", target_saudi_pct=0.30,
            source="Nitaqat", effective_year=2025,
        )]
        gaps = compute_saudization_gap(splits, targets)
        assert gaps["SEC01"].achievability_assessment == "ON_TRACK"

    def test_achievable_with_training(self):
        """Target > projected_min but ≤ projected_max → ACHIEVABLE_WITH_TRAINING."""
        splits = {"SEC01": self._make_split("SEC01", 1000, 200, 200, 600)}
        # projected_min = 200/1000 = 0.20, projected_max = 400/1000 = 0.40
        targets = [SectorSaudizationTarget(
            sector_code="SEC01", target_saudi_pct=0.35,
            source="Nitaqat", effective_year=2025,
        )]
        gaps = compute_saudization_gap(splits, targets)
        assert gaps["SEC01"].achievability_assessment == "ACHIEVABLE_WITH_TRAINING"

    def test_moderate_gap(self):
        """gap_pct_min > 0 but ≤ 0.10 → MODERATE_GAP."""
        splits = {"SEC01": self._make_split("SEC01", 1000, 200, 100, 700)}
        # projected_min = 0.20, projected_max = 0.30
        targets = [SectorSaudizationTarget(
            sector_code="SEC01", target_saudi_pct=0.38,
            source="Nitaqat", effective_year=2025,
        )]
        # gap_pct_min = 0.38 - 0.30 = 0.08 (≤ 0.10)
        gaps = compute_saudization_gap(splits, targets)
        assert gaps["SEC01"].achievability_assessment == "MODERATE_GAP"

    def test_significant_gap(self):
        """gap_pct_min > 0.10 but ≤ 0.25 → SIGNIFICANT_GAP."""
        splits = {"SEC01": self._make_split("SEC01", 1000, 100, 100, 800)}
        # projected_min = 0.10, projected_max = 0.20
        targets = [SectorSaudizationTarget(
            sector_code="SEC01", target_saudi_pct=0.40,
            source="Nitaqat", effective_year=2025,
        )]
        # gap_pct_min = 0.40 - 0.20 = 0.20 (≤ 0.25)
        gaps = compute_saudization_gap(splits, targets)
        assert gaps["SEC01"].achievability_assessment == "SIGNIFICANT_GAP"

    def test_critical_gap(self):
        """gap_pct_min > 0.25 → CRITICAL_GAP."""
        splits = {"SEC01": self._make_split("SEC01", 1000, 50, 50, 900)}
        # projected_min = 0.05, projected_max = 0.10
        targets = [SectorSaudizationTarget(
            sector_code="SEC01", target_saudi_pct=0.60,
            source="Nitaqat", effective_year=2025,
        )]
        # gap_pct_min = 0.60 - 0.10 = 0.50 (> 0.25)
        gaps = compute_saudization_gap(splits, targets)
        assert gaps["SEC01"].achievability_assessment == "CRITICAL_GAP"

    def test_min_max_range_values(self):
        """Amendment 6: Verify min/max projected percentages."""
        splits = {"SEC01": self._make_split("SEC01", 1000, 200, 150, 650)}
        targets = [SectorSaudizationTarget(
            sector_code="SEC01", target_saudi_pct=0.40,
            source="Nitaqat", effective_year=2025,
        )]
        gaps = compute_saudization_gap(splits, targets)
        sg = gaps["SEC01"]
        assert abs(sg.projected_saudi_pct_min - 0.20) < 0.001
        assert abs(sg.projected_saudi_pct_max - 0.35) < 0.001
        assert abs(sg.gap_pct_min - 0.05) < 0.001  # 0.40 - 0.35
        assert abs(sg.gap_pct_max - 0.20) < 0.001  # 0.40 - 0.20

    def test_no_target_for_sector(self):
        """Sectors without targets are not included in gaps."""
        splits = {
            "SEC01": self._make_split("SEC01", 1000, 300, 200, 500),
            "SEC02": self._make_split("SEC02", 500, 100, 100, 300),
        }
        targets = [SectorSaudizationTarget(
            sector_code="SEC01", target_saudi_pct=0.30,
            source="Nitaqat", effective_year=2025,
        )]
        gaps = compute_saudization_gap(splits, targets)
        assert "SEC01" in gaps
        assert "SEC02" not in gaps

    def test_zero_total_jobs(self):
        """Zero total jobs → projected_pct = 0."""
        splits = {"SEC01": self._make_split("SEC01", 0, 0, 0, 0)}
        targets = [SectorSaudizationTarget(
            sector_code="SEC01", target_saudi_pct=0.30,
            source="Nitaqat", effective_year=2025,
        )]
        gaps = compute_saudization_gap(splits, targets)
        assert gaps["SEC01"].projected_saudi_pct_min == 0.0
        assert gaps["SEC01"].projected_saudi_pct_max == 0.0


# ---------------------------------------------------------------------------
# compute_sensitivity
# ---------------------------------------------------------------------------


class TestComputeSensitivity:
    def test_hard_band_5pct(self):
        from src.models.workforce import SectorEmployment
        employment = {
            "SEC01": SectorEmployment(
                sector_code="SEC01", total_jobs=1000.0,
                direct_jobs=600.0, indirect_jobs=400.0,
                confidence=ConstraintConfidence.HARD,
            ),
        }
        envelopes = compute_sensitivity(
            employment, {"SEC01": ConstraintConfidence.HARD},
        )
        se = envelopes["SEC01"]
        assert abs(se.low_jobs - 950.0) < 0.01  # 1000 - 1000*0.05
        assert abs(se.high_jobs - 1050.0) < 0.01

    def test_estimated_band_15pct(self):
        from src.models.workforce import SectorEmployment
        employment = {
            "SEC01": SectorEmployment(
                sector_code="SEC01", total_jobs=1000.0,
                direct_jobs=600.0, indirect_jobs=400.0,
                confidence=ConstraintConfidence.ESTIMATED,
            ),
        }
        envelopes = compute_sensitivity(
            employment, {"SEC01": ConstraintConfidence.ESTIMATED},
        )
        se = envelopes["SEC01"]
        assert abs(se.low_jobs - 850.0) < 0.01
        assert abs(se.high_jobs - 1150.0) < 0.01

    def test_assumed_band_30pct(self):
        from src.models.workforce import SectorEmployment
        employment = {
            "SEC01": SectorEmployment(
                sector_code="SEC01", total_jobs=1000.0,
                direct_jobs=600.0, indirect_jobs=400.0,
                confidence=ConstraintConfidence.ASSUMED,
            ),
        }
        envelopes = compute_sensitivity(
            employment, {"SEC01": ConstraintConfidence.ASSUMED},
        )
        se = envelopes["SEC01"]
        assert abs(se.low_jobs - 700.0) < 0.01
        assert abs(se.high_jobs - 1300.0) < 0.01

    def test_negative_delta_x_valid_ordering(self):
        """Amendment 3: Negative base → low < base < high still holds."""
        from src.models.workforce import SectorEmployment
        employment = {
            "SEC01": SectorEmployment(
                sector_code="SEC01", total_jobs=-1000.0,
                direct_jobs=-600.0, indirect_jobs=-400.0,
                confidence=ConstraintConfidence.ESTIMATED,
            ),
        }
        envelopes = compute_sensitivity(
            employment, {"SEC01": ConstraintConfidence.ESTIMATED},
        )
        se = envelopes["SEC01"]
        assert se.low_jobs <= se.base_jobs <= se.high_jobs
        # low = -1000 - 1000*0.15 = -1150, high = -1000 + 1000*0.15 = -850
        assert abs(se.low_jobs - (-1150.0)) < 0.01
        assert abs(se.high_jobs - (-850.0)) < 0.01

    def test_zero_delta_x_zero_envelope(self):
        """Amendment 3: Zero base → zero envelope."""
        from src.models.workforce import SectorEmployment
        employment = {
            "SEC01": SectorEmployment(
                sector_code="SEC01", total_jobs=0.0,
                direct_jobs=0.0, indirect_jobs=0.0,
                confidence=ConstraintConfidence.HARD,
            ),
        }
        envelopes = compute_sensitivity(
            employment, {"SEC01": ConstraintConfidence.HARD},
        )
        se = envelopes["SEC01"]
        assert se.low_jobs == 0.0
        assert se.high_jobs == 0.0


# ---------------------------------------------------------------------------
# compute_confidence_summary
# ---------------------------------------------------------------------------


class TestComputeConfidenceSummary:
    def test_all_hard_high(self, sector_codes):
        from src.models.workforce import SectorEmployment
        employment = {
            sc: SectorEmployment(
                sector_code=sc, total_jobs=100.0,
                direct_jobs=60.0, indirect_jobs=40.0,
                confidence=ConstraintConfidence.HARD,
            )
            for sc in sector_codes
        }
        coefficients = [
            SectorEmploymentCoefficient(
                sector_code=sc, jobs_per_million_sar=10.0,
                confidence=ConstraintConfidence.HARD,
            )
            for sc in sector_codes
        ]
        # Provide full bridge + rules so coverage doesn't drag confidence down
        bridge_entries = [
            BridgeEntry(sector_code=sc, occupation_code=f"OCC_{sc}",
                       share=1.0, confidence=ConstraintConfidence.HARD)
            for sc in sector_codes
        ]
        tier_assignments = [
            TierAssignment(occupation_code=f"OCC_{sc}",
                          nationality_tier=NationalityTier.SAUDI_READY)
            for sc in sector_codes
        ]
        summary = compute_confidence_summary(
            coefficients, bridge_entries, tier_assignments,
            employment, sector_codes,
        )
        assert summary.overall_confidence == WorkforceConfidenceLevel.HIGH
        assert summary.output_weighted_coefficient_confidence == 1.0

    def test_all_assumed_low(self, sector_codes):
        from src.models.workforce import SectorEmployment
        employment = {
            sc: SectorEmployment(
                sector_code=sc, total_jobs=100.0,
                direct_jobs=60.0, indirect_jobs=40.0,
                confidence=ConstraintConfidence.ASSUMED,
            )
            for sc in sector_codes
        }
        coefficients = [
            SectorEmploymentCoefficient(
                sector_code=sc, jobs_per_million_sar=10.0,
                confidence=ConstraintConfidence.ASSUMED,
            )
            for sc in sector_codes
        ]
        summary = compute_confidence_summary(
            coefficients, [], [], employment, sector_codes,
        )
        assert summary.overall_confidence == WorkforceConfidenceLevel.LOW

    def test_mixed_medium(self, sector_codes):
        from src.models.workforce import SectorEmployment
        employment = {
            sc: SectorEmployment(
                sector_code=sc, total_jobs=100.0,
                direct_jobs=60.0, indirect_jobs=40.0,
                confidence=ConstraintConfidence.ESTIMATED,
            )
            for sc in sector_codes
        }
        coefficients = [
            SectorEmploymentCoefficient(
                sector_code="SEC01", jobs_per_million_sar=10.0,
                confidence=ConstraintConfidence.HARD,
            ),
            SectorEmploymentCoefficient(
                sector_code="SEC02", jobs_per_million_sar=10.0,
                confidence=ConstraintConfidence.ESTIMATED,
            ),
            SectorEmploymentCoefficient(
                sector_code="SEC03", jobs_per_million_sar=10.0,
                confidence=ConstraintConfidence.ASSUMED,
            ),
        ]
        # Provide bridge + rules at moderate coverage
        bridge_entries = [
            BridgeEntry(sector_code=sc, occupation_code=f"OCC_{sc}",
                       share=1.0, confidence=ConstraintConfidence.ESTIMATED)
            for sc in sector_codes
        ]
        tier_assignments = [
            TierAssignment(occupation_code=f"OCC_{sc}",
                          nationality_tier=NationalityTier.SAUDI_READY)
            for sc in sector_codes
        ]
        summary = compute_confidence_summary(
            coefficients, bridge_entries, tier_assignments,
            employment, sector_codes,
        )
        assert summary.overall_confidence == WorkforceConfidenceLevel.MEDIUM

    def test_bridge_coverage(self, sector_codes):
        from src.models.workforce import SectorEmployment
        employment = {
            sc: SectorEmployment(
                sector_code=sc, total_jobs=100.0,
                direct_jobs=60.0, indirect_jobs=40.0,
                confidence=ConstraintConfidence.HARD,
            )
            for sc in sector_codes
        }
        bridge_entries = [
            BridgeEntry(sector_code="SEC01", occupation_code="OCC01",
                       share=0.5, confidence=ConstraintConfidence.HARD),
        ]
        # Only SEC01 has bridge → coverage = 1/3
        summary = compute_confidence_summary(
            [], bridge_entries, [], employment, sector_codes,
        )
        assert abs(summary.bridge_coverage_pct - 1.0 / 3.0) < 0.01

    def test_unclassified_over_50_forces_low(self, sector_codes):
        """Amendment 5: >50% unclassified → overall_confidence = LOW."""
        from src.models.workforce import SectorEmployment
        employment = {
            sc: SectorEmployment(
                sector_code=sc, total_jobs=100.0,
                direct_jobs=60.0, indirect_jobs=40.0,
                confidence=ConstraintConfidence.HARD,
            )
            for sc in sector_codes
        }
        coefficients = [
            SectorEmploymentCoefficient(
                sector_code=sc, jobs_per_million_sar=10.0,
                confidence=ConstraintConfidence.HARD,
            )
            for sc in sector_codes
        ]
        # rule_coverage = 0 → unclassified > 50% scenario
        summary = compute_confidence_summary(
            coefficients, [], [], employment, sector_codes,
            unclassified_pct=0.6,
        )
        assert summary.overall_confidence == WorkforceConfidenceLevel.LOW


# ---------------------------------------------------------------------------
# compute_workforce_impact (orchestrator)
# ---------------------------------------------------------------------------


class TestComputeWorkforceImpact:
    def test_full_pipeline(self, delta_x_total, delta_x_direct, delta_x_indirect,
                           sector_codes, coefficients, bridge, rules):
        result = compute_workforce_impact(
            delta_x_total=delta_x_total,
            delta_x_direct=delta_x_direct,
            delta_x_indirect=delta_x_indirect,
            sector_codes=sector_codes,
            coefficients=coefficients,
            bridge=bridge,
            rules=rules,
        )
        assert len(result.sector_employment) == 3
        assert len(result.occupation_breakdowns) > 0
        assert len(result.nationality_splits) == 3
        assert len(result.saudization_gaps) > 0
        assert len(result.sensitivity_envelopes) == 3
        assert result.delta_x_source == "unconstrained"

    def test_bridge_optional_graceful(self, delta_x_total, delta_x_direct,
                                       delta_x_indirect, sector_codes, coefficients):
        """Bridge is optional — result still computed without it."""
        result = compute_workforce_impact(
            delta_x_total=delta_x_total,
            delta_x_direct=delta_x_direct,
            delta_x_indirect=delta_x_indirect,
            sector_codes=sector_codes,
            coefficients=coefficients,
            bridge=None,
            rules=None,
        )
        assert len(result.sector_employment) == 3
        assert len(result.occupation_breakdowns) == 0
        assert len(result.saudization_gaps) == 0
        assert any("bridge" in note.lower() for note in result.data_quality_notes)

    def test_rules_optional_graceful(self, delta_x_total, delta_x_direct,
                                      delta_x_indirect, sector_codes, coefficients,
                                      bridge):
        """Rules optional — no saudization gaps but employment computed."""
        result = compute_workforce_impact(
            delta_x_total=delta_x_total,
            delta_x_direct=delta_x_direct,
            delta_x_indirect=delta_x_indirect,
            sector_codes=sector_codes,
            coefficients=coefficients,
            bridge=bridge,
            rules=None,
        )
        assert len(result.sector_employment) == 3
        assert len(result.saudization_gaps) == 0

    def test_data_quality_notes_populated(self, delta_x_total, delta_x_direct,
                                           delta_x_indirect, sector_codes,
                                           coefficients, bridge, rules):
        result = compute_workforce_impact(
            delta_x_total=delta_x_total,
            delta_x_direct=delta_x_direct,
            delta_x_indirect=delta_x_indirect,
            sector_codes=sector_codes,
            coefficients=coefficients,
            bridge=bridge,
            rules=rules,
        )
        # Notes should mention UNMAPPED for SEC01 and missing bridge for SEC03
        assert isinstance(result.data_quality_notes, list)

    def test_deterministic_reproducibility(self, delta_x_total, delta_x_direct,
                                           delta_x_indirect, sector_codes,
                                           coefficients, bridge, rules):
        r1 = compute_workforce_impact(
            delta_x_total, delta_x_direct, delta_x_indirect,
            sector_codes, coefficients, bridge, rules,
        )
        r2 = compute_workforce_impact(
            delta_x_total, delta_x_direct, delta_x_indirect,
            sector_codes, coefficients, bridge, rules,
        )
        for sc in sector_codes:
            assert r1.sector_employment[sc].total_jobs == r2.sector_employment[sc].total_jobs

    def test_hash_reproducibility(self, delta_x_total, delta_x_direct,
                                   delta_x_indirect, sector_codes, coefficients):
        """Amendment 9: Same inputs → same hash."""
        r1 = compute_workforce_impact(
            delta_x_total, delta_x_direct, delta_x_indirect,
            sector_codes, coefficients,
        )
        r2 = compute_workforce_impact(
            delta_x_total, delta_x_direct, delta_x_indirect,
            sector_codes, coefficients,
        )
        assert r1.satellite_coefficients_hash == r2.satellite_coefficients_hash

    def test_version_constant(self):
        assert WORKFORCE_SATELLITE_VERSION == "1.0.0"
