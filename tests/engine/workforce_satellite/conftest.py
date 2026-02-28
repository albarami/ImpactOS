"""Shared fixtures for workforce satellite tests."""

from __future__ import annotations

from uuid import uuid4

import numpy as np
import pytest

from src.data.workforce.nationality_classification import (
    NationalityClassification,
    NationalityClassificationSet,
    NationalityTier,
)
from src.data.workforce.nitaqat_macro_targets import (
    MacroSaudizationTargets,
    SectorSaudizationTarget,
)
from src.data.workforce.occupation_bridge import (
    OccupationBridge,
    OccupationBridgeEntry,
)
from src.data.workforce.satellite_coeff_loader import CoefficientProvenance
from src.data.workforce.unit_registry import QualityConfidence
from src.engine.satellites import SatelliteResult
from src.engine.workforce_satellite.schemas import BaselineSectorWorkforce
from src.models.common import ConstraintConfidence


@pytest.fixture()
def two_sector_bridge() -> OccupationBridge:
    """Bridge for sectors A (agriculture) and F (construction).

    A: 60% elementary(9), 30% agricultural(6), 10% managers(1)
    F: 50% craft(7), 30% operators(8), 20% elementary(9)
    """
    return OccupationBridge(
        year=2024,
        entries=[
            OccupationBridgeEntry(
                sector_code="A", occupation_code="9",
                share=0.60, source="expert",
                source_confidence=ConstraintConfidence.ASSUMED,
                quality_confidence=QualityConfidence.MEDIUM,
            ),
            OccupationBridgeEntry(
                sector_code="A", occupation_code="6",
                share=0.30, source="expert",
                source_confidence=ConstraintConfidence.ASSUMED,
                quality_confidence=QualityConfidence.MEDIUM,
            ),
            OccupationBridgeEntry(
                sector_code="A", occupation_code="1",
                share=0.10, source="expert",
                source_confidence=ConstraintConfidence.ASSUMED,
                quality_confidence=QualityConfidence.MEDIUM,
            ),
            OccupationBridgeEntry(
                sector_code="F", occupation_code="7",
                share=0.50, source="expert",
                source_confidence=ConstraintConfidence.ASSUMED,
                quality_confidence=QualityConfidence.LOW,
            ),
            OccupationBridgeEntry(
                sector_code="F", occupation_code="8",
                share=0.30, source="expert",
                source_confidence=ConstraintConfidence.ASSUMED,
                quality_confidence=QualityConfidence.LOW,
            ),
            OccupationBridgeEntry(
                sector_code="F", occupation_code="9",
                share=0.20, source="expert",
                source_confidence=ConstraintConfidence.ASSUMED,
                quality_confidence=QualityConfidence.LOW,
            ),
        ],
        metadata={"source": "test"},
    )


@pytest.fixture()
def two_sector_classifications() -> NationalityClassificationSet:
    """Classifications for A and F sectors.

    A/9: expat_reliant (elementary agriculture)
    A/6: saudi_trainable (agricultural workers)
    A/1: saudi_ready (managers)
    F/7: saudi_trainable (craft)
    F/8: expat_reliant (operators)
    F/9: expat_reliant (elementary construction)
    """
    return NationalityClassificationSet(
        year=2024,
        classifications=[
            NationalityClassification(
                sector_code="A", occupation_code="9",
                tier=NationalityTier.EXPAT_RELIANT,
                current_saudi_pct=0.05,
                rationale="Elementary agriculture mostly expat",
                source_confidence=ConstraintConfidence.ASSUMED,
                quality_confidence=QualityConfidence.LOW,
                sensitivity_range=None, source="expert",
            ),
            NationalityClassification(
                sector_code="A", occupation_code="6",
                tier=NationalityTier.SAUDI_TRAINABLE,
                current_saudi_pct=None,
                rationale="Agricultural workers trainable",
                source_confidence=ConstraintConfidence.ASSUMED,
                quality_confidence=QualityConfidence.LOW,
                sensitivity_range=None, source="expert",
            ),
            NationalityClassification(
                sector_code="A", occupation_code="1",
                tier=NationalityTier.SAUDI_READY,
                current_saudi_pct=0.80,
                rationale="Managers mostly Saudi",
                source_confidence=ConstraintConfidence.ESTIMATED,
                quality_confidence=QualityConfidence.HIGH,
                sensitivity_range=None, source="GOSI",
            ),
            NationalityClassification(
                sector_code="F", occupation_code="7",
                tier=NationalityTier.SAUDI_TRAINABLE,
                current_saudi_pct=None,
                rationale="Construction craft workers trainable",
                source_confidence=ConstraintConfidence.ASSUMED,
                quality_confidence=QualityConfidence.LOW,
                sensitivity_range=None, source="expert",
            ),
            NationalityClassification(
                sector_code="F", occupation_code="8",
                tier=NationalityTier.EXPAT_RELIANT,
                current_saudi_pct=0.02,
                rationale="Machine operators mostly expat",
                source_confidence=ConstraintConfidence.ASSUMED,
                quality_confidence=QualityConfidence.LOW,
                sensitivity_range=None, source="expert",
            ),
            NationalityClassification(
                sector_code="F", occupation_code="9",
                tier=NationalityTier.EXPAT_RELIANT,
                current_saudi_pct=0.01,
                rationale="Elementary construction mostly expat",
                source_confidence=ConstraintConfidence.ASSUMED,
                quality_confidence=QualityConfidence.LOW,
                sensitivity_range=None, source="expert",
            ),
        ],
    )


@pytest.fixture()
def two_sector_nitaqat() -> MacroSaudizationTargets:
    """Nitaqat targets for A and F sectors."""
    return MacroSaudizationTargets(
        targets={
            "A": SectorSaudizationTarget(
                sector_code="A",
                effective_target_pct=0.10,
                target_range_low=0.05,
                target_range_high=0.15,
                derivation="macro simplified",
                applicable_rules=["rule1"],
                source_confidence=ConstraintConfidence.ESTIMATED,
                quality_confidence=QualityConfidence.MEDIUM,
            ),
            "F": SectorSaudizationTarget(
                sector_code="F",
                effective_target_pct=0.12,
                target_range_low=0.08,
                target_range_high=0.16,
                derivation="macro simplified",
                applicable_rules=["rule2"],
                source_confidence=ConstraintConfidence.ESTIMATED,
                quality_confidence=QualityConfidence.MEDIUM,
            ),
        },
        effective_as_of="2024-01-01",
    )


@pytest.fixture()
def two_sector_satellite_result() -> SatelliteResult:
    """SatelliteResult for 2-sector model: A=50 jobs, F=100 jobs."""
    return SatelliteResult(
        delta_jobs=np.array([50.0, 100.0]),
        delta_imports=np.array([10.0, 30.0]),
        delta_domestic_output=np.array([40.0, 70.0]),
        delta_va=np.array([30.0, 40.0]),
        coefficients_version_id=uuid4(),
    )


@pytest.fixture()
def two_sector_baseline() -> list[BaselineSectorWorkforce]:
    """Baseline workforce for A and F."""
    return [
        BaselineSectorWorkforce(
            sector_code="A",
            total_employment=1000.0,
            saudi_employment=100.0,
            saudi_share=0.10,
            source="GOSI",
            year=2023,
        ),
        BaselineSectorWorkforce(
            sector_code="F",
            total_employment=5000.0,
            saudi_employment=400.0,
            saudi_share=0.08,
            source="GOSI",
            year=2023,
        ),
    ]


@pytest.fixture()
def coefficient_provenance() -> CoefficientProvenance:
    return CoefficientProvenance(
        employment_coeff_year=2024,
        io_base_year=2022,
        import_ratio_year=2022,
        va_ratio_year=2022,
        fallback_flags=[],
        synchronized=False,
    )
