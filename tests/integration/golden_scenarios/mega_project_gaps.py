"""Golden Scenario 2: Mega-Project with Data Gaps (20-sector).

Tests graceful degradation when data is incomplete:
- Model vintage 6+ years old -> vintage WARNING
- Some LOW confidence mappings -> mapping WARNING
- Missing occupation bridge for one ISIC section -> workforce null with caveats
- Constraints mostly ASSUMED -> constraint WARNING
- Expected quality grade: C or D

Uses 20-sector D-1 model (ISIC A-T) via load_real_saudi_io().
Demand shocks still target F, C, G primarily, but some mappings are LOW confidence.
"""

from dataclasses import dataclass, field

import numpy as np
from uuid_extensions import uuid7

from src.engine.constraints.schema import (
    Constraint,
    ConstraintBoundScope,
    ConstraintScope,
    ConstraintSet,
    ConstraintType,
    ConstraintUnit,
)
from src.models.common import ConstraintConfidence
from src.models.document import BoQLineItem
from src.models.mapping import DecisionType, MappingDecision

from .shared import ISIC_20_SECTIONS, make_decision, make_line_item


@dataclass(frozen=True)
class MegaProjectGapsScenario:
    """Scenario with intentional data gaps across 20-sector model."""

    workspace_id: object = field(default_factory=uuid7)
    scenario_name: str = "Mega-Project with Data Gaps"

    # Stale model: 6 years old (triggers vintage WARNING)
    base_year: int = 2018
    current_year: int = 2024

    # Demand shocks target ISIC sections (20-sector model)
    # F (Construction): 200M, C (Manufacturing): 100M, G (Wholesale): 50M, M: 50M
    primary_shocks: dict = field(default_factory=lambda: {
        "F": 200.0, "C": 100.0, "G": 50.0, "M": 50.0,
    })

    # Quality expectations
    expected_quality_grade_range: tuple = ("C", "D")

    # Mapping: some items will have LOW confidence (0.3)
    low_confidence_item_count: int = 5
    high_confidence_item_count: int = 10

    # Constraints: mostly ASSUMED (poor data quality)
    hard_constraints: int = 1
    estimated_constraints: int = 1
    assumed_constraints: int = 4

    # Workforce: section "N" (Administrative/Support) has no occupation bridge
    sections_without_bridge: list = field(default_factory=lambda: ["N"])


# ---------------------------------------------------------------------------
# BoQ line items: 15 total (10 HIGH confidence + 5 LOW confidence)
# ---------------------------------------------------------------------------

_DOC_ID = uuid7()
_JOB_ID = uuid7()


def build_boq_items() -> list[BoQLineItem]:
    """Build BoQ line items for the mega-project gaps scenario.

    Returns 15 items: 10 with high-confidence mappings and 5 with
    low-confidence mappings that trigger quality warnings.
    """
    # High-confidence items (confidence >= 0.85)
    high_items = [
        ("reinforced concrete foundation works", 25_000_000.0),
        ("structural steel erection and assembly", 20_000_000.0),
        ("site preparation grading leveling", 15_000_000.0),
        ("electrical infrastructure main distribution", 12_000_000.0),
        ("plumbing drainage and sanitary works", 10_000_000.0),
        ("prefabricated steel components delivery", 18_000_000.0),
        ("industrial equipment procurement install", 14_000_000.0),
        ("hvac system manufacturing and installation", 11_000_000.0),
        ("wholesale trade material supplies", 8_000_000.0),
        ("engineering design consultancy services", 6_000_000.0),
    ]

    # Low-confidence items (confidence = 0.3, ambiguous descriptions)
    low_items = [
        ("miscellaneous site support activities", 5_000_000.0),
        ("general administrative overhead costs", 4_000_000.0),
        ("unspecified equipment rental charges", 3_500_000.0),
        ("sundry procurement items batch lot", 3_000_000.0),
        ("other professional services various", 2_500_000.0),
    ]

    items: list[BoQLineItem] = []
    for text, value in high_items + low_items:
        items.append(make_line_item(text, value, doc_id=_DOC_ID, job_id=_JOB_ID))
    return items


# ---------------------------------------------------------------------------
# Mapping decisions: mixed confidence (HIGH + LOW)
# ---------------------------------------------------------------------------

# Ground-truth sector assignments for the items above
_HIGH_SECTORS = ["F", "F", "F", "F", "F", "C", "C", "C", "G", "M"]
_LOW_SECTORS = ["N", "N", "N", "C", "M"]  # Ambiguous -> mapped with LOW confidence


def build_mapping_decisions(
    boq_items: list[BoQLineItem],
) -> list[MappingDecision]:
    """Build mapping decisions for all BoQ items.

    First 10 items get high confidence (0.85-0.95).
    Last 5 items get low confidence (0.3) triggering quality warnings.
    """
    decisions: list[MappingDecision] = []
    analyst_id = uuid7()

    high_confidences = [0.95, 0.93, 0.90, 0.88, 0.87, 0.92, 0.90, 0.88, 0.91, 0.89]

    # High-confidence decisions
    for i, item in enumerate(boq_items[:10]):
        decisions.append(make_decision(
            line_item_id=item.line_item_id,
            suggested=_HIGH_SECTORS[i],
            final=_HIGH_SECTORS[i],
            confidence=high_confidences[i],
            decided_by=analyst_id,
        ))

    # Low-confidence decisions (0.3 confidence — triggers mapping WARNING)
    for i, item in enumerate(boq_items[10:]):
        decisions.append(make_decision(
            line_item_id=item.line_item_id,
            suggested=_LOW_SECTORS[i],
            final=_LOW_SECTORS[i],
            confidence=0.3,
            decided_by=analyst_id,
        ))

    return decisions


# ---------------------------------------------------------------------------
# Constraint set: mostly ASSUMED (poor data quality)
# ---------------------------------------------------------------------------


def build_constraint_set(workspace_id=None, model_version_id=None) -> ConstraintSet:
    """Build constraints with mostly ASSUMED confidence.

    1 HARD constraint (construction capacity cap) — well-documented.
    1 ESTIMATED constraint (labor cap on manufacturing) — survey-based.
    4 ASSUMED constraints — analyst guesses, no hard evidence.

    This distribution of confidence triggers constraint quality warnings.
    """
    ws_id = workspace_id or uuid7()
    mv_id = model_version_id or uuid7()

    constraints = [
        # 1 HARD: Construction sector capacity cap (well-documented)
        Constraint(
            constraint_type=ConstraintType.CAPACITY_CAP,
            scope=ConstraintScope(scope_type="sector", scope_values=["F"]),
            description="Construction sector max capacity (MOMRAH data)",
            upper_bound=500_000.0,
            unit=ConstraintUnit.SAR_MILLIONS,
            confidence=ConstraintConfidence.HARD,
            owner="client",
            notes="Based on MOMRAH construction permits database",
        ),
        # 1 ESTIMATED: Manufacturing labor cap (survey-based)
        Constraint(
            constraint_type=ConstraintType.LABOR,
            scope=ConstraintScope(scope_type="sector", scope_values=["C"]),
            description="Manufacturing labor ceiling (HRSD survey estimate)",
            upper_bound=150_000.0,
            unit=ConstraintUnit.JOBS,
            confidence=ConstraintConfidence.ESTIMATED,
            owner="steward",
            notes="Based on HRSD quarterly labor survey Q2 2023",
        ),
        # 4 ASSUMED: Analyst assumptions with no hard evidence
        Constraint(
            constraint_type=ConstraintType.RAMP,
            scope=ConstraintScope(scope_type="sector", scope_values=["F"]),
            description="Construction ramp rate assumption",
            max_growth_rate=0.15,
            unit=ConstraintUnit.GROWTH_RATE,
            confidence=ConstraintConfidence.ASSUMED,
            notes="Analyst assumption — no historical data available",
        ),
        Constraint(
            constraint_type=ConstraintType.RAMP,
            scope=ConstraintScope(scope_type="sector", scope_values=["C"]),
            description="Manufacturing ramp rate assumption",
            max_growth_rate=0.12,
            unit=ConstraintUnit.GROWTH_RATE,
            confidence=ConstraintConfidence.ASSUMED,
            notes="Analyst assumption — limited data for Saudi context",
        ),
        Constraint(
            constraint_type=ConstraintType.IMPORT,
            scope=ConstraintScope(scope_type="sector", scope_values=["G"]),
            description="Wholesale import growth assumption",
            upper_bound=0.25,
            unit=ConstraintUnit.GROWTH_RATE,
            confidence=ConstraintConfidence.ASSUMED,
            notes="Rough assumption pending customs data integration",
        ),
        Constraint(
            constraint_type=ConstraintType.CAPACITY_CAP,
            scope=ConstraintScope(scope_type="sector", scope_values=["M"]),
            description="Professional services capacity assumption",
            upper_bound=100_000.0,
            unit=ConstraintUnit.SAR_MILLIONS,
            confidence=ConstraintConfidence.ASSUMED,
            notes="Assumption — no firm capacity data for professional services",
        ),
    ]

    return ConstraintSet(
        workspace_id=ws_id,
        model_version_id=mv_id,
        name="Mega-Project Gaps Constraint Set",
        constraints=constraints,
        metadata={
            "hard_count": 1,
            "estimated_count": 1,
            "assumed_count": 4,
            "data_quality_note": "Majority ASSUMED — triggers constraint warnings",
        },
    )


# ---------------------------------------------------------------------------
# Demand shock vector for 20-sector model
# ---------------------------------------------------------------------------


def build_demand_shock_vector(sector_codes: list[str] | None = None) -> np.ndarray:
    """Build the 20-sector demand shock vector (delta_d).

    Shocks: F=200M, C=100M, G=50M, M=50M. All other sectors = 0.

    Args:
        sector_codes: Ordered sector codes. Defaults to ISIC_20_SECTIONS.

    Returns:
        numpy array of length 20 with demand shocks in SAR millions.
    """
    codes = sector_codes or ISIC_20_SECTIONS
    shocks = {"F": 200.0, "C": 100.0, "G": 50.0, "M": 50.0}
    return np.array([shocks.get(s, 0.0) for s in codes], dtype=np.float64)


# ---------------------------------------------------------------------------
# Convenience: instantiate default scenario
# ---------------------------------------------------------------------------

SCENARIO = MegaProjectGapsScenario()
