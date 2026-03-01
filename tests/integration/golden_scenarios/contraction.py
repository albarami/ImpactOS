"""Golden Scenario 3: Contraction Scenario -- Negative Demand Shocks (20-sector).

Tests that negative demand changes work correctly through the 20-sector model:
- Negative delta_d in sections F, C, G -> negative delta_x -> negative jobs
- Workforce nationality min/mid/max still in correct numeric order
- No binding capacity constraints (contraction doesn't hit caps)
- Quality assessment handles negative impacts correctly

Uses 20-sector D-1 model (ISIC A-T) via load_real_saudi_io().
"""

from dataclasses import dataclass, field

import numpy as np
from uuid_extensions import uuid7

from src.models.document import BoQLineItem
from src.models.mapping import DecisionType, MappingDecision

from .shared import ISIC_20_SECTIONS, make_decision, make_line_item


@dataclass(frozen=True)
class ContractionScenario:
    """Negative demand shock scenario across 20 ISIC sections."""

    workspace_id: object = field(default_factory=uuid7)
    scenario_name: str = "Sector Contraction"

    # NEGATIVE demand shocks in key ISIC sections
    primary_shocks: dict = field(default_factory=lambda: {
        "F": -100.0, "C": -50.0, "G": -30.0,
    })

    base_year: int = 2024

    # Quality expectations
    expected_quality_grade_range: tuple = ("A", "B", "C")

    # Contraction should NOT trigger capacity constraints
    expected_binding_constraints: int = 0


# ---------------------------------------------------------------------------
# BoQ line items: contraction items represent cancelled/reduced spend
# ---------------------------------------------------------------------------

_DOC_ID = uuid7()
_JOB_ID = uuid7()


def build_boq_items() -> list[BoQLineItem]:
    """Build BoQ line items representing cancelled or reduced project spend.

    Negative total_value is not valid in BoQ (values are always positive in
    the line items), so we use positive values here. The negative demand
    shocks are applied at the scenario level via the demand shock vector.

    Returns 9 items across the 3 contracting sectors (F, C, G).
    """
    items_data = [
        # Construction (F) reductions — largest contraction
        ("deferred foundation construction phase 2", 25_000_000.0),
        ("cancelled site expansion works", 40_000_000.0),
        ("reduced infrastructure maintenance scope", 35_000_000.0),
        # Manufacturing (C) reductions
        ("scaled back equipment procurement order", 20_000_000.0),
        ("reduced steel fabrication contract", 15_000_000.0),
        ("deferred hvac unit manufacturing", 15_000_000.0),
        # Wholesale/Retail (G) reductions
        ("reduced wholesale supply orders", 12_000_000.0),
        ("cancelled retail distribution contract", 10_000_000.0),
        ("deferred trade material procurement", 8_000_000.0),
    ]

    items: list[BoQLineItem] = []
    for text, value in items_data:
        items.append(make_line_item(text, value, doc_id=_DOC_ID, job_id=_JOB_ID))
    return items


# ---------------------------------------------------------------------------
# Mapping decisions: all HIGH confidence (clean data, just negative shocks)
# ---------------------------------------------------------------------------

_SECTOR_ASSIGNMENTS = ["F", "F", "F", "C", "C", "C", "G", "G", "G"]
_CONFIDENCES = [0.95, 0.93, 0.91, 0.92, 0.90, 0.88, 0.90, 0.88, 0.87]


def build_mapping_decisions(
    boq_items: list[BoQLineItem],
) -> list[MappingDecision]:
    """Build mapping decisions for contraction BoQ items.

    All items have HIGH confidence mappings (clean data scenario).
    The data quality issue here is the negative shocks, not bad mappings.
    """
    decisions: list[MappingDecision] = []
    analyst_id = uuid7()

    for i, item in enumerate(boq_items):
        decisions.append(make_decision(
            line_item_id=item.line_item_id,
            suggested=_SECTOR_ASSIGNMENTS[i],
            final=_SECTOR_ASSIGNMENTS[i],
            confidence=_CONFIDENCES[i],
            decided_by=analyst_id,
        ))

    return decisions


# ---------------------------------------------------------------------------
# Demand shock vector for 20-sector model (NEGATIVE values)
# ---------------------------------------------------------------------------


def build_demand_shock_vector(sector_codes: list[str] | None = None) -> np.ndarray:
    """Build the 20-sector NEGATIVE demand shock vector (delta_d).

    Shocks: F=-100M, C=-50M, G=-30M. All other sectors = 0.

    This tests that the engine correctly propagates negative demand through
    the Leontief inverse, producing:
    - Negative delta_x (output reductions)
    - Negative delta_jobs (job losses)
    - Negative delta_va (GDP contraction)

    The nationality breakdown (min/mid/max) must still maintain correct
    numeric ordering even with negative values:
    - For job losses: max <= mid <= min (all negative, max is most negative)
    - This ensures reporting logic handles contraction correctly

    Args:
        sector_codes: Ordered sector codes. Defaults to ISIC_20_SECTIONS.

    Returns:
        numpy array of length 20 with negative demand shocks in SAR millions.
    """
    codes = sector_codes or ISIC_20_SECTIONS
    shocks = {"F": -100.0, "C": -50.0, "G": -30.0}
    return np.array([shocks.get(s, 0.0) for s in codes], dtype=np.float64)


def verify_contraction_properties(
    delta_d: np.ndarray,
    delta_x: np.ndarray,
    delta_jobs: np.ndarray,
) -> list[str]:
    """Verify essential contraction properties hold after a run.

    Returns a list of violation descriptions. Empty list = all checks pass.

    Checks:
    1. Shocked sectors have negative delta_x (output falls).
    2. Total delta_x is negative (economy contracts).
    3. Total delta_jobs is negative (net job loss).
    4. Non-shocked sectors may have small positive or negative spillovers,
       but the dominant effect is contraction.
    """
    violations: list[str] = []

    # Sectors with negative demand shocks should have negative output change
    shocked_mask = delta_d < 0
    if not np.all(delta_x[shocked_mask] < 0):
        bad_idx = np.where(shocked_mask & (delta_x >= 0))[0]
        violations.append(
            f"Shocked sectors with non-negative delta_x: indices {bad_idx.tolist()}"
        )

    # Total economy should contract
    if np.sum(delta_x) >= 0:
        violations.append(
            f"Total delta_x is non-negative ({np.sum(delta_x):.2f}); "
            "expected net contraction"
        )

    # Total jobs should decline
    if np.sum(delta_jobs) >= 0:
        violations.append(
            f"Total delta_jobs is non-negative ({np.sum(delta_jobs):.2f}); "
            "expected net job losses"
        )

    return violations


def verify_nationality_ordering(
    nationality_min: np.ndarray,
    nationality_mid: np.ndarray,
    nationality_max: np.ndarray,
) -> list[str]:
    """Verify min <= mid <= max ordering for nationality workforce estimates.

    For contraction scenarios all values may be negative (job losses), but
    the ordering min <= mid <= max must still hold element-wise.

    Returns a list of violation descriptions. Empty list = all checks pass.
    """
    violations: list[str] = []

    # Element-wise: min <= mid
    bad_min_mid = np.where(nationality_min > nationality_mid + 1e-10)[0]
    if len(bad_min_mid) > 0:
        violations.append(
            f"min > mid at sector indices {bad_min_mid.tolist()}"
        )

    # Element-wise: mid <= max
    bad_mid_max = np.where(nationality_mid > nationality_max + 1e-10)[0]
    if len(bad_mid_max) > 0:
        violations.append(
            f"mid > max at sector indices {bad_mid_max.tolist()}"
        )

    return violations


# ---------------------------------------------------------------------------
# Convenience: instantiate default scenario
# ---------------------------------------------------------------------------

SCENARIO = ContractionScenario()
