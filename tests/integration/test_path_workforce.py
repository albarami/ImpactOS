"""Integration Path 3: Engine -> Workforce Satellite.

Tests:
- SatelliteResult (delta_jobs) -> WorkforceSatellite.analyze -> WorkforceResult
- Occupation decomposition sums to total sector employment
- Nationality splits have min <= mid <= max (numeric order)
- Negative jobs (contraction) preserve numeric ordering
- Missing occupation bridge -> graceful null with caveats
"""

import json

import numpy as np
import pytest
from pathlib import Path
from uuid_extensions import uuid7

from src.data.workforce.nationality_classification import (
    NationalityClassification,
    NationalityClassificationSet,
    NationalityTier,
)
from src.data.workforce.occupation_bridge import (
    OccupationBridge,
    OccupationBridgeEntry,
)
from src.data.workforce.unit_registry import QualityConfidence
from src.engine.satellites import SatelliteResult
from src.engine.workforce_satellite.satellite import WorkforceSatellite
from src.models.common import ConstraintConfidence

from tests.integration.golden_scenarios.shared import (
    EMPLOYMENT_ATOL,
    NUMERIC_RTOL,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "workforce"


def _load_bridge() -> OccupationBridge:
    """Load sample occupation bridge from fixtures.

    The JSON fixture has extra fields (_provenance, granularity, etc.)
    that are not part of the OccupationBridge dataclass, so we extract
    only the fields the constructor expects.
    """
    with open(FIXTURES_DIR / "sample_occupation_bridge.json") as f:
        data = json.load(f)

    entries = [
        OccupationBridgeEntry(
            sector_code=e["sector_code"],
            occupation_code=e["occupation_code"],
            share=e["share"],
            source=e["source"],
            source_confidence=ConstraintConfidence(e["source_confidence"]),
            quality_confidence=QualityConfidence(e["quality_confidence"]),
        )
        for e in data["entries"]
    ]
    return OccupationBridge(
        year=data["year"],
        entries=entries,
        metadata=data.get("metadata", {}),
    )


def _load_classifications() -> NationalityClassificationSet:
    """Load sample nationality classifications from fixtures.

    Adapts JSON structure to the frozen dataclass constructor.
    """
    with open(FIXTURES_DIR / "sample_nationality_classification.json") as f:
        data = json.load(f)

    classifications = [
        NationalityClassification(
            sector_code=c["sector_code"],
            occupation_code=c["occupation_code"],
            tier=NationalityTier(c["tier"]),
            current_saudi_pct=c["current_saudi_pct"],
            rationale=c["rationale"],
            source_confidence=ConstraintConfidence(c["source_confidence"]),
            quality_confidence=QualityConfidence(c["quality_confidence"]),
            sensitivity_range=(
                tuple(c["sensitivity_range"])
                if c.get("sensitivity_range") is not None
                else None
            ),
            source=c["source"],
        )
        for c in data["classifications"]
    ]
    return NationalityClassificationSet(
        year=data["year"],
        classifications=classifications,
        metadata=data.get("metadata", {}),
    )


def _make_satellite_result(delta_jobs: list[float]) -> SatelliteResult:
    """Create a SatelliteResult with given delta_jobs."""
    n = len(delta_jobs)
    return SatelliteResult(
        delta_jobs=np.array(delta_jobs),
        delta_imports=np.zeros(n),
        delta_domestic_output=np.zeros(n),
        delta_va=np.zeros(n),
        coefficients_version_id=uuid7(),
    )


@pytest.mark.integration
class TestWorkforceIntegration:
    """Engine -> Workforce Satellite integration."""

    def test_positive_jobs_produce_valid_workforce(self):
        """Positive delta_jobs -> WorkforceResult with sector summaries."""
        bridge = _load_bridge()
        classifications = _load_classifications()
        ws = WorkforceSatellite(
            occupation_bridge=bridge,
            nationality_classifications=classifications,
        )

        # Use sector codes from the bridge
        sector_codes = bridge.get_sectors()
        delta_jobs = [10.0] * len(sector_codes)
        sat_result = _make_satellite_result(delta_jobs)

        result = ws.analyze(
            satellite_result=sat_result,
            sector_codes=sector_codes,
        )

        assert result.total_jobs > 0
        assert len(result.sector_summaries) > 0

        # Each sector summary should have total_jobs matching input
        for summary in result.sector_summaries:
            assert summary.total_jobs == pytest.approx(10.0, abs=NUMERIC_RTOL)

        # Occupation decomposition: shares should sum to ~total_jobs per sector
        for summary in result.sector_summaries:
            occ_jobs_sum = sum(occ.jobs for occ in summary.occupation_impacts)
            assert occ_jobs_sum == pytest.approx(
                summary.total_jobs, rel=NUMERIC_RTOL,
            )

    def test_nationality_split_min_mid_max_order(self):
        """min_saudi <= mid_saudi <= max_saudi for positive jobs."""
        bridge = _load_bridge()
        classifications = _load_classifications()
        ws = WorkforceSatellite(
            occupation_bridge=bridge,
            nationality_classifications=classifications,
        )

        sector_codes = bridge.get_sectors()
        delta_jobs = [20.0] * len(sector_codes)
        sat_result = _make_satellite_result(delta_jobs)

        result = ws.analyze(
            satellite_result=sat_result,
            sector_codes=sector_codes,
        )

        for summary in result.sector_summaries:
            assert summary.projected_saudi_jobs_min <= summary.projected_saudi_jobs_mid
            assert summary.projected_saudi_jobs_mid <= summary.projected_saudi_jobs_max

    def test_contraction_nationality_ordering(self):
        """Negative jobs: min/mid/max still in correct numeric order."""
        bridge = _load_bridge()
        classifications = _load_classifications()
        ws = WorkforceSatellite(
            occupation_bridge=bridge,
            nationality_classifications=classifications,
        )

        sector_codes = bridge.get_sectors()
        delta_jobs = [-15.0] * len(sector_codes)
        sat_result = _make_satellite_result(delta_jobs)

        result = ws.analyze(
            satellite_result=sat_result,
            sector_codes=sector_codes,
        )

        for summary in result.sector_summaries:
            # Numeric order preserved even for negative
            assert summary.projected_saudi_jobs_min <= summary.projected_saudi_jobs_mid
            assert summary.projected_saudi_jobs_mid <= summary.projected_saudi_jobs_max

    def test_confidence_labels_present(self):
        """Every sector summary has a confidence label."""
        bridge = _load_bridge()
        classifications = _load_classifications()
        ws = WorkforceSatellite(
            occupation_bridge=bridge,
            nationality_classifications=classifications,
        )

        sector_codes = bridge.get_sectors()
        delta_jobs = [10.0] * len(sector_codes)
        sat_result = _make_satellite_result(delta_jobs)

        result = ws.analyze(
            satellite_result=sat_result,
            sector_codes=sector_codes,
        )

        valid_confidence_labels = {"HARD", "ESTIMATED", "ASSUMED", "HIGH", "MEDIUM", "LOW"}

        for summary in result.sector_summaries:
            assert summary.overall_confidence in valid_confidence_labels

        # Overall result also has confidence
        assert result.overall_confidence in valid_confidence_labels

    def test_missing_bridge_graceful_degradation(self):
        """Sectors not in bridge -> graceful fallback to ASSUMED elementary occupations."""
        bridge = _load_bridge()
        classifications = _load_classifications()
        ws = WorkforceSatellite(
            occupation_bridge=bridge,
            nationality_classifications=classifications,
        )

        # Use bridge sectors plus an extra sector not in the bridge
        bridge_sectors = bridge.get_sectors()
        extra_sector = "Z"  # Not a real ISIC section, not in bridge
        sector_codes = bridge_sectors + [extra_sector]
        delta_jobs = [10.0] * len(sector_codes)
        sat_result = _make_satellite_result(delta_jobs)

        result = ws.analyze(
            satellite_result=sat_result,
            sector_codes=sector_codes,
        )

        # Should still produce results for all sectors including the missing one
        assert len(result.sector_summaries) == len(sector_codes)

        # Find the summary for the extra sector
        extra_summary = next(
            s for s in result.sector_summaries if s.sector_code == extra_sector
        )

        # Should have occupation impacts (defaulted to elementary)
        assert len(extra_summary.occupation_impacts) > 0
        # The fallback occupation should be "9" (Elementary Occupations)
        assert extra_summary.occupation_impacts[0].occupation_code == "9"
        # Bridge confidence should be ASSUMED for the fallback
        assert extra_summary.occupation_impacts[0].bridge_confidence == "ASSUMED"
        # Overall confidence should reflect ASSUMED
        assert extra_summary.overall_confidence == "ASSUMED"
