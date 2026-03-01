"""Golden Scenario 1: Industrial Zone CAPEX — Full Happy Path (20-sector).

A typical SG engagement: construction of an industrial zone.
Exercises the complete pipeline with all modules present.

Uses the D-1 20-sector IO model (ISIC A-T) via load_real_saudi_io().
Demand shocks concentrated in F (Construction), C (Manufacturing),
G (Wholesale/Retail), with smaller amounts in M (Professional Services)
and other sections.

Expected path: D-1 IO model -> Compiler -> Leontief -> Satellite ->
Constraints -> Workforce -> Quality -> RunSnapshot
"""

from dataclasses import dataclass, field
from uuid import UUID

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
from src.models.common import ConstraintConfidence, new_uuid7
from src.models.document import BoQLineItem
from src.models.mapping import DecisionType, MappingDecision
from src.models.scenario import TimeHorizon

from .shared import make_decision, make_line_item


@dataclass(frozen=True)
class IndustrialZoneScenario:
    """Complete test data for industrial zone impact assessment (20-sector).

    Uses ISIC sections A-T. Primary demand shocks target:
    - F (Construction): ~300M SAR
    - C (Manufacturing): ~150M SAR
    - G (Wholesale/Retail): ~30M SAR
    - M (Professional Services): ~50M SAR
    """

    # Identity
    workspace_id: UUID = field(default_factory=uuid7)
    scenario_name: str = "Industrial Zone Phase 1"
    base_year: int = 2024

    # Phasing: 3-year schedule (40%/35%/25%)
    phasing: dict = field(default_factory=lambda: {2024: 0.40, 2025: 0.35, 2026: 0.25})

    # Tolerances
    output_rtol: float = 0.01       # 1% relative tolerance
    employment_atol: int = 10       # +/- 10 jobs
    gdp_rtol: float = 0.01         # 1% relative tolerance

    # Expected quality grade
    expected_quality_grade_range: tuple = ("A", "B")


# ---------------------------------------------------------------------------
# Total spend breakdown (SAR):
#   Construction (F):            300,000,000
#   Manufacturing (C):           150,000,000
#   Professional Services (M):    50,000,000
#   Wholesale/Retail (G):          8,000,000
#   Transport (H):                 6,000,000
#   ICT (J):                       4,000,000
#   Accommodation/Food (I):        2,000,000
#   -------------------------------------------
#   Grand total:                 520,000,000
# ---------------------------------------------------------------------------


def build_industrial_zone_scenario() -> IndustrialZoneScenario:
    """Construct the complete industrial zone golden scenario."""
    return IndustrialZoneScenario()


def build_industrial_zone_boq(
    doc_id: UUID | None = None,
    job_id: UUID | None = None,
) -> list[BoQLineItem]:
    """Build 20 BoQ line items spanning multiple ISIC sections.

    Primary sectors: F (Construction), C (Manufacturing), M (Professional Services).
    Secondary sectors: G (Wholesale), H (Transport), J (ICT), I (Accommodation/Food).

    Returns exactly 20 items with a grand total of 520M SAR.
    """
    doc_id = doc_id or uuid7()
    job_id = job_id or uuid7()

    items = []

    # Construction items (F) -- 6 items, 300M total
    for text, value in [
        ("Reinforced concrete foundation works", 80_000_000),
        ("Structural steel erection", 70_000_000),
        ("Site preparation and grading", 50_000_000),
        ("Electrical infrastructure installation", 40_000_000),
        ("Plumbing and drainage systems", 30_000_000),
        ("Concrete batch plant operations", 30_000_000),
    ]:
        items.append(make_line_item(text, value, doc_id, job_id))

    # Manufacturing items (C) -- 5 items, 150M total
    for text, value in [
        ("Pre-fabricated steel components", 40_000_000),
        ("Industrial equipment procurement", 35_000_000),
        ("HVAC system manufacturing", 30_000_000),
        ("Control panel fabrication", 25_000_000),
        ("Piping and valve assemblies", 20_000_000),
    ]:
        items.append(make_line_item(text, value, doc_id, job_id))

    # Professional services items (M) -- 5 items, 50M total
    for text, value in [
        ("Engineering design consultancy", 15_000_000),
        ("Project management services", 12_000_000),
        ("Environmental impact assessment", 8_000_000),
        ("Quality assurance and testing", 8_000_000),
        ("Legal and regulatory compliance", 7_000_000),
    ]:
        items.append(make_line_item(text, value, doc_id, job_id))

    # Secondary sector items -- 4 items, 20M total
    for text, value in [
        ("Wholesale trade supplies", 8_000_000),         # G
        ("Transportation and logistics", 6_000_000),     # H
        ("Information technology systems", 4_000_000),   # J
        ("Catering and food services", 2_000_000),       # I
    ]:
        items.append(make_line_item(text, value, doc_id, job_id))

    assert len(items) == 20, f"Expected 20 BoQ items, got {len(items)}"
    _total = sum(item.total_value for item in items)
    assert _total == 520_000_000, f"Expected 520M SAR total, got {_total}"

    return items


def build_industrial_zone_decisions(
    line_items: list[BoQLineItem],
    decided_by: UUID | None = None,
) -> list[MappingDecision]:
    """Build HIGH-confidence mapping decisions for all 20 items.

    Sector assignment: first 6 -> F, next 5 -> C, next 5 -> M,
    then G, H, J, I for the remaining 4.
    """
    decided_by = decided_by or uuid7()

    sector_map = (
        ["F"] * 6 + ["C"] * 5 + ["M"] * 5
        + ["G", "H", "J", "I"]
    )
    assert len(sector_map) == len(line_items), (
        f"sector_map length ({len(sector_map)}) != "
        f"line_items length ({len(line_items)})"
    )

    decisions = []
    for item, sector in zip(line_items, sector_map):
        decisions.append(
            make_decision(
                line_item_id=item.line_item_id,
                suggested=sector,
                final=sector,
                confidence=0.90,
                decided_by=decided_by,
            )
        )
    return decisions


def build_industrial_zone_constraints(
    workspace_id: UUID | None = None,
    model_version_id: UUID | None = None,
) -> ConstraintSet:
    """Build constraint set with one binding labor constraint on Construction (F).

    The constraint caps Construction (F) delta output at 200M SAR,
    which is expected to bind given the ~300M SAR direct demand shock
    on sector F.
    """
    workspace_id = workspace_id or uuid7()
    model_version_id = model_version_id or uuid7()

    constraints = [
        Constraint(
            constraint_id=new_uuid7(),
            constraint_type=ConstraintType.LABOR,
            scope=ConstraintScope(
                scope_type="sector",
                scope_values=["F"],
            ),
            upper_bound=200.0,
            bound_scope=ConstraintBoundScope.DELTA_ONLY,
            unit=ConstraintUnit.SAR_MILLIONS,
            confidence=ConstraintConfidence.HARD,
            description="Construction labor capacity constraint",
        ),
    ]
    return ConstraintSet(
        constraint_set_id=new_uuid7(),
        workspace_id=workspace_id,
        model_version_id=model_version_id,
        name="Industrial Zone Constraints v1",
        constraints=constraints,
    )


# ---------------------------------------------------------------------------
# Phasing helper
# ---------------------------------------------------------------------------

PHASING_WEIGHTS: dict[int, float] = {2024: 0.40, 2025: 0.35, 2026: 0.25}
"""3-year phasing schedule: 40% / 35% / 25%."""


def get_phased_demand(sector_total_sar: float) -> dict[int, float]:
    """Split a sector total into phased annual demands using PHASING_WEIGHTS."""
    return {year: sector_total_sar * weight for year, weight in PHASING_WEIGHTS.items()}


# ---------------------------------------------------------------------------
# Sector-level demand aggregation (for building ScenarioSpec shock items)
# ---------------------------------------------------------------------------

SECTOR_TOTALS_SAR: dict[str, float] = {
    "F": 300_000_000.0,
    "C": 150_000_000.0,
    "M":  50_000_000.0,
    "G":   8_000_000.0,
    "H":   6_000_000.0,
    "J":   4_000_000.0,
    "I":   2_000_000.0,
}
"""Sector-level total spend from the 20 BoQ items."""


# ---------------------------------------------------------------------------
# Expected tolerances (for assertions in integration tests)
# ---------------------------------------------------------------------------

EXPECTED_TOLERANCES = {
    "output_rtol": 0.01,        # 1% relative tolerance on total output
    "employment_atol": 10,      # +/- 10 jobs absolute tolerance
    "gdp_rtol": 0.01,           # 1% relative tolerance on GDP impact
    "quality_grades": ("A", "B"),  # Acceptable quality gate grades
}


# ---------------------------------------------------------------------------
# Convenience: build all scenario components at once
# ---------------------------------------------------------------------------

def build_all(
    workspace_id: UUID | None = None,
    model_version_id: UUID | None = None,
) -> dict:
    """Build all scenario components and return as a dict.

    Returns:
        dict with keys: scenario, boq_items, decisions, constraints,
        phasing, sector_totals, tolerances.
    """
    workspace_id = workspace_id or uuid7()
    model_version_id = model_version_id or uuid7()

    scenario = build_industrial_zone_scenario()
    boq_items = build_industrial_zone_boq()
    decisions = build_industrial_zone_decisions(boq_items)
    constraints = build_industrial_zone_constraints(
        workspace_id=workspace_id,
        model_version_id=model_version_id,
    )

    return {
        "scenario": scenario,
        "boq_items": boq_items,
        "decisions": decisions,
        "constraints": constraints,
        "phasing": PHASING_WEIGHTS,
        "sector_totals": SECTOR_TOTALS_SAR,
        "tolerances": EXPECTED_TOLERANCES,
    }
