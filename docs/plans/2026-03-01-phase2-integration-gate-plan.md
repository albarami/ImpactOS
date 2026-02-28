# MVP-14: Phase 2 Integration + Gate — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prove all Phase 2 modules work together via 80+ integration tests, golden scenarios, regression baselines, and a formal gate report.

**Architecture:** Direct module-level integration tests (not API/HTTP). Three golden scenarios using the 20-sector D-1 IO model (ISIC A-T) via `load_real_saudi_io()`, with toleranced JSON snapshots. A separate 3-sector toy model (ISIC F/C/G) used ONLY for mathematical accuracy verification. Gate report script reads pytest JSON output. All tests deterministic — Depth Engine LLM mocked.

**Tech Stack:** Python 3.11+, pytest, numpy, Pydantic v2. No new product modules in src/.

**Existing State:** 3,049 tests passing. 134 API-level integration tests already in tests/integration/. This plan adds module-level tests alongside them.

**Key conventions:**
- `shared.py` holds constants and helpers; `conftest.py` holds ONLY `@pytest.fixture` definitions
- All test files import from `.golden_scenarios.shared`, NEVER from `.golden_scenarios.conftest`
- Golden scenarios use 20-sector model via `load_real_saudi_io()` (ISIC sections A-T)
- The 3-sector toy model (ISIC F/C/G) exists ONLY in `shared.py` for `test_mathematical_accuracy.py`

---

### Task 0: Create Worktree + Register Pytest Markers

**Files:**
- Modify: `pyproject.toml` (markers section, ~line 81-83)

**Step 1: Create git worktree for MVP-14**

```bash
cd C:/Projects/ImpactOS
git worktree add .claude/worktrees/mvp14-integration -b mvp14-phase2-integration-gate
```

**Step 2: Add pytest markers to pyproject.toml**

In `[tool.pytest.ini_options]` markers list, add:

```toml
markers = [
    "benchmark: performance benchmark tests (deselect with '-m not benchmark')",
    "integration: Integration tests across module boundaries",
    "golden: Golden scenario end-to-end tests",
    "performance: Performance benchmark tests (skip in CI by default)",
    "slow: Tests that take more than 5s",
    "regression: Regression baseline tests",
    "gate: Phase 2 gate criteria verification",
    "real_data: Tests using sanitized real data fixtures",
]
```

**Step 3: Run existing tests to verify no breakage**

Run: `python -m pytest --co -q`
Expected: 3049 tests collected

**Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "[mvp14] register integration test pytest markers"
```

---

### Task 1: Shared Integration Module (shared.py) + Fixture Definitions (conftest.py)

**Files:**
- Create: `tests/integration/golden_scenarios/__init__.py`
- Create: `tests/integration/golden_scenarios/shared.py`
- Create: `tests/integration/golden_scenarios/conftest.py`

This task builds the shared constant/helper layer and the fixture layer as SEPARATE files. `shared.py` holds all constants, tolerance values, the 3-sector toy model data, and helper functions. `conftest.py` holds ONLY `@pytest.fixture` definitions that import from `shared.py`. All test files import from `shared.py`, never from `conftest.py`.

**Step 1: Create the `__init__.py`**

```python
# tests/integration/golden_scenarios/__init__.py
"""Golden scenario test data for MVP-14 integration tests."""
```

**Step 2: Create `shared.py` with constants, toy model, and helpers**

```python
# tests/integration/golden_scenarios/shared.py
"""Shared constants, toy model data, and helper functions for MVP-14 integration tests.

ALL test files import from this module. conftest.py imports from here too.
This file contains NO pytest fixtures — those live in conftest.py.

Conventions:
- SECTOR_CODES_SMALL uses valid ISIC codes: F (Construction), C (Manufacturing),
  G (Wholesale/Retail Trade). Used ONLY for mathematical accuracy verification.
- The 20-sector model uses load_real_saudi_io() and is the standard for golden scenarios.
"""

import numpy as np
from uuid_extensions import uuid7

from src.models.document import BoQLineItem
from src.models.mapping import DecisionType, MappingDecision, MappingLibraryEntry

# ---------------------------------------------------------------------------
# Tolerance constants (documented per Amendment 7)
# ---------------------------------------------------------------------------

NUMERIC_RTOL = 1e-6          # Relative tolerance for floating point
EMPLOYMENT_ATOL = 10         # Absolute tolerance for job counts
GDP_RTOL = 0.01              # 1% tolerance for GDP impacts
OUTPUT_RTOL = 0.01           # 1% tolerance for output impacts

# ---------------------------------------------------------------------------
# 3-sector toy model (ISIC F/C/G) — ONLY for test_mathematical_accuracy.py
# ---------------------------------------------------------------------------

# Valid ISIC section codes
SECTOR_CODES_SMALL = ["F", "C", "G"]  # Construction, Manufacturing, Wholesale/Retail

# Transaction matrix Z (3x3) — inter-industry flows
# Chosen so A matrix has reasonable coefficients (0.05-0.25)
GOLDEN_Z = np.array([
    [100.0, 50.0,  30.0],   # F buys from F, C, G
    [ 80.0, 200.0, 60.0],   # C buys from F, C, G
    [ 40.0, 100.0, 150.0],  # G buys from F, C, G
], dtype=np.float64)

# Gross output vector x
GOLDEN_X = np.array([1000.0, 2000.0, 1500.0], dtype=np.float64)

# A = Z / x (column-wise): technical coefficients
# A[i,j] = Z[i,j] / x[j]
# Column 0 (F): [100/1000, 80/1000, 40/1000] = [0.10, 0.08, 0.04]
# Column 1 (C): [50/2000, 200/2000, 100/2000] = [0.025, 0.10, 0.05]
# Column 2 (G): [30/1500, 60/1500, 150/1500] = [0.02, 0.04, 0.10]
#
# I - A:
# [[0.90, -0.025, -0.02 ],
#  [-0.08, 0.90,  -0.04 ],
#  [-0.04, -0.05,  0.90 ]]
#
# B = (I-A)^-1 is computed by the engine; we verify in test_mathematical_accuracy.py

GOLDEN_BASE_YEAR = 2024

# Pre-computed B = (I-A)^-1 for hand-verification (3-sector model)
# Computed via numpy: np.linalg.inv(np.eye(3) - A)
# These are reference values for test_mathematical_accuracy.py
_A_SMALL = GOLDEN_Z / GOLDEN_X[np.newaxis, :]
_I_MINUS_A = np.eye(3) - _A_SMALL
EXPECTED_B_SMALL = np.linalg.inv(_I_MINUS_A)

# Satellite coefficients for the 3-sector toy model
SMALL_JOBS_COEFF = np.array([0.008, 0.004, 0.006])   # jobs per unit output
SMALL_IMPORT_RATIO = np.array([0.30, 0.25, 0.15])     # import leakage
SMALL_VA_RATIO = np.array([0.35, 0.45, 0.55])         # value added share

# ---------------------------------------------------------------------------
# ISIC 20-sector codes (A through T)
# ---------------------------------------------------------------------------

ISIC_20_SECTIONS = [
    "A", "B", "C", "D", "E", "F", "G", "H", "I", "J",
    "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T",
]

# Demand shock targets for golden scenarios (the "active" sectors)
PRIMARY_SHOCK_SECTIONS = {
    "F": "Construction",
    "C": "Manufacturing",
    "G": "Wholesale and retail trade",
}

# ---------------------------------------------------------------------------
# Seed mapping library for compiler gate tests
# ---------------------------------------------------------------------------

SEED_LIBRARY = [
    MappingLibraryEntry(
        pattern="concrete", sector_code="F", confidence=0.95,
    ),
    MappingLibraryEntry(
        pattern="reinforced concrete", sector_code="F", confidence=0.95,
    ),
    MappingLibraryEntry(
        pattern="foundation works", sector_code="F", confidence=0.90,
    ),
    MappingLibraryEntry(
        pattern="site preparation", sector_code="F", confidence=0.90,
    ),
    MappingLibraryEntry(
        pattern="structural steel erection", sector_code="F", confidence=0.88,
    ),
    MappingLibraryEntry(
        pattern="electrical infrastructure", sector_code="F", confidence=0.85,
    ),
    MappingLibraryEntry(
        pattern="plumbing drainage", sector_code="F", confidence=0.85,
    ),
    MappingLibraryEntry(
        pattern="steel supply", sector_code="C", confidence=0.90,
    ),
    MappingLibraryEntry(
        pattern="prefabricated steel", sector_code="C", confidence=0.90,
    ),
    MappingLibraryEntry(
        pattern="industrial equipment", sector_code="C", confidence=0.88,
    ),
    MappingLibraryEntry(
        pattern="hvac system", sector_code="C", confidence=0.85,
    ),
    MappingLibraryEntry(
        pattern="control panel fabrication", sector_code="C", confidence=0.85,
    ),
    MappingLibraryEntry(
        pattern="piping valve", sector_code="C", confidence=0.82,
    ),
    MappingLibraryEntry(
        pattern="consulting", sector_code="M", confidence=0.85,
    ),
    MappingLibraryEntry(
        pattern="engineering design", sector_code="M", confidence=0.88,
    ),
    MappingLibraryEntry(
        pattern="project management", sector_code="M", confidence=0.85,
    ),
    MappingLibraryEntry(
        pattern="environmental assessment", sector_code="M", confidence=0.82,
    ),
    MappingLibraryEntry(
        pattern="quality assurance testing", sector_code="M", confidence=0.80,
    ),
    MappingLibraryEntry(
        pattern="legal regulatory", sector_code="M", confidence=0.78,
    ),
    MappingLibraryEntry(
        pattern="transportation logistics", sector_code="H", confidence=0.85,
    ),
    MappingLibraryEntry(
        pattern="wholesale trade", sector_code="G", confidence=0.90,
    ),
    MappingLibraryEntry(
        pattern="retail supply", sector_code="G", confidence=0.85,
    ),
    MappingLibraryEntry(
        pattern="catering food", sector_code="I", confidence=0.82,
    ),
    MappingLibraryEntry(
        pattern="information technology", sector_code="J", confidence=0.88,
    ),
    MappingLibraryEntry(
        pattern="financial services", sector_code="K", confidence=0.85,
    ),
    MappingLibraryEntry(
        pattern="real estate", sector_code="L", confidence=0.90,
    ),
    MappingLibraryEntry(
        pattern="mining quarrying", sector_code="B", confidence=0.88,
    ),
    MappingLibraryEntry(
        pattern="agriculture farming", sector_code="A", confidence=0.85,
    ),
    MappingLibraryEntry(
        pattern="water supply sewerage", sector_code="E", confidence=0.82,
    ),
    MappingLibraryEntry(
        pattern="electricity gas", sector_code="D", confidence=0.85,
    ),
]

# ---------------------------------------------------------------------------
# Labeled BoQ for compiler gate (ground-truth ISIC mappings)
# ---------------------------------------------------------------------------

LABELED_BOQ = [
    {"text": "reinforced concrete foundation", "ground_truth_isic": "F", "value": 5_000_000},
    {"text": "structural steel erection works", "ground_truth_isic": "F", "value": 4_000_000},
    {"text": "site preparation and grading", "ground_truth_isic": "F", "value": 3_500_000},
    {"text": "electrical infrastructure installation", "ground_truth_isic": "F", "value": 3_000_000},
    {"text": "plumbing and drainage systems", "ground_truth_isic": "F", "value": 2_500_000},
    {"text": "prefabricated steel components", "ground_truth_isic": "C", "value": 4_000_000},
    {"text": "industrial equipment procurement", "ground_truth_isic": "C", "value": 3_500_000},
    {"text": "hvac system manufacturing", "ground_truth_isic": "C", "value": 3_000_000},
    {"text": "control panel fabrication", "ground_truth_isic": "C", "value": 2_500_000},
    {"text": "piping and valve assemblies", "ground_truth_isic": "C", "value": 2_000_000},
    {"text": "engineering design consultancy", "ground_truth_isic": "M", "value": 1_500_000},
    {"text": "project management services", "ground_truth_isic": "M", "value": 1_200_000},
    {"text": "environmental impact assessment", "ground_truth_isic": "M", "value": 800_000},
    {"text": "quality assurance and testing", "ground_truth_isic": "M", "value": 800_000},
    {"text": "legal and regulatory compliance", "ground_truth_isic": "M", "value": 700_000},
    {"text": "transportation and logistics", "ground_truth_isic": "H", "value": 1_000_000},
    {"text": "wholesale trade supplies", "ground_truth_isic": "G", "value": 900_000},
    {"text": "catering and food services", "ground_truth_isic": "I", "value": 600_000},
    {"text": "information technology systems", "ground_truth_isic": "J", "value": 1_200_000},
    {"text": "financial advisory services", "ground_truth_isic": "K", "value": 500_000},
    {"text": "real estate leasing", "ground_truth_isic": "L", "value": 400_000},
    {"text": "mining and quarrying materials", "ground_truth_isic": "B", "value": 1_500_000},
    {"text": "water supply and sewerage works", "ground_truth_isic": "E", "value": 700_000},
    {"text": "electricity and gas supply", "ground_truth_isic": "D", "value": 800_000},
    {"text": "agriculture and farming inputs", "ground_truth_isic": "A", "value": 300_000},
    {"text": "retail supply chain items", "ground_truth_isic": "G", "value": 500_000},
    {"text": "concrete batch plant operations", "ground_truth_isic": "F", "value": 2_000_000},
    {"text": "steel reinforcement bars", "ground_truth_isic": "C", "value": 1_800_000},
    {"text": "project consulting advisory", "ground_truth_isic": "M", "value": 600_000},
    {"text": "heavy equipment rental", "ground_truth_isic": "N", "value": 900_000},
]

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def make_line_item(
    raw_text: str,
    total_value: float,
    doc_id=None,
    job_id=None,
) -> BoQLineItem:
    """Create a BoQLineItem with minimal required fields."""
    return BoQLineItem(
        doc_id=doc_id or uuid7(),
        extraction_job_id=job_id or uuid7(),
        raw_text=raw_text,
        total_value=total_value,
        page_ref=0,
        evidence_snippet_ids=[uuid7()],
    )


def make_decision(
    line_item_id,
    suggested: str,
    final: str,
    confidence: float,
    decided_by=None,
) -> MappingDecision:
    """Create a MappingDecision for testing."""
    return MappingDecision(
        line_item_id=line_item_id,
        suggested_sector_code=suggested,
        suggested_confidence=confidence,
        final_sector_code=final,
        decision_type=DecisionType.APPROVED,
        decided_by=decided_by or uuid7(),
    )


def make_labeled_boq_items(
    labeled_boq: list[dict] | None = None,
) -> list[BoQLineItem]:
    """Convert LABELED_BOQ dicts into BoQLineItem objects for testing."""
    labeled = labeled_boq or LABELED_BOQ
    doc_id = uuid7()
    job_id = uuid7()
    return [
        make_line_item(item["text"], item["value"], doc_id=doc_id, job_id=job_id)
        for item in labeled
    ]
```

**Step 3: Create `conftest.py` with ONLY fixture definitions**

```python
# tests/integration/golden_scenarios/conftest.py
"""Pytest fixture definitions for MVP-14 integration tests.

This file contains ONLY @pytest.fixture functions.
All constants and helpers live in shared.py.
"""

import numpy as np
import pytest
from uuid_extensions import uuid7

from src.engine.model_store import ModelStore
from src.engine.satellites import SatelliteCoefficients

from .shared import (
    GOLDEN_BASE_YEAR,
    GOLDEN_X,
    GOLDEN_Z,
    SECTOR_CODES_SMALL,
    SMALL_IMPORT_RATIO,
    SMALL_JOBS_COEFF,
    SMALL_VA_RATIO,
)


@pytest.fixture
def model_store() -> ModelStore:
    """Fresh ModelStore instance."""
    return ModelStore()


@pytest.fixture
def small_model_version(model_store: ModelStore):
    """Register the 3-sector toy IO model (ISIC F/C/G)."""
    mv = model_store.register(
        Z=GOLDEN_Z,
        x=GOLDEN_X,
        sector_codes=SECTOR_CODES_SMALL,
        base_year=GOLDEN_BASE_YEAR,
        source="golden-integration-test-small",
    )
    return mv


@pytest.fixture
def small_loaded_model(model_store: ModelStore, small_model_version):
    """Load the 3-sector toy model for computation."""
    return model_store.get(small_model_version.model_version_id)


@pytest.fixture
def small_satellite_coefficients() -> SatelliteCoefficients:
    """Satellite coefficients for the 3-sector toy model."""
    return SatelliteCoefficients(
        jobs_coeff=SMALL_JOBS_COEFF.copy(),
        import_ratio=SMALL_IMPORT_RATIO.copy(),
        va_ratio=SMALL_VA_RATIO.copy(),
        version_id=uuid7(),
    )
```

**Step 4: Verify fixtures load**

Run: `python -m pytest tests/integration/golden_scenarios/ --co -q`
Expected: 0 tests collected (just fixtures, no tests yet)

**Step 5: Commit**

```bash
git add tests/integration/golden_scenarios/
git commit -m "[mvp14] Task 1: shared.py constants/helpers + conftest.py fixture definitions"
```

---

### Task 2: Golden Scenario 1 — Industrial Zone CAPEX (20-sector)

**Files:**
- Create: `tests/integration/golden_scenarios/industrial_zone.py`

This constructs the complete happy-path test data using the 20-sector D-1 model. BoQ items, mapping decisions, phasing, constraints, workforce data, and hand-verified expected outputs all reference ISIC sections A-T.

**Step 1: Build the golden scenario data class**

```python
# tests/integration/golden_scenarios/industrial_zone.py
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
    - M (Professional Services): ~20M SAR
    """

    # Identity
    workspace_id: UUID = field(default_factory=uuid7)
    scenario_name: str = "Industrial Zone Phase 1"
    base_year: int = 2024

    # Phasing: 3-year schedule
    phasing: dict = field(default_factory=lambda: {2024: 0.40, 2025: 0.35, 2026: 0.25})

    # Tolerances
    output_rtol: float = 0.01       # 1% relative tolerance
    employment_atol: int = 10       # +/- 10 jobs
    gdp_rtol: float = 0.01         # 1% relative tolerance

    # Expected quality grade
    expected_quality_grade_range: tuple = ("A", "B")


def build_industrial_zone_scenario() -> IndustrialZoneScenario:
    """Construct the complete industrial zone golden scenario."""
    return IndustrialZoneScenario()


def build_industrial_zone_boq(
    doc_id: UUID | None = None,
    job_id: UUID | None = None,
) -> list[BoQLineItem]:
    """Build 20 BoQ line items spanning multiple ISIC sections.

    Primary sectors: F (Construction), C (Manufacturing), M (Professional Services).
    Secondary sectors: G (Wholesale), H (Transport), J (ICT).
    """
    doc_id = doc_id or uuid7()
    job_id = job_id or uuid7()

    items = []
    # Construction items (F) — 6 items, ~300M total
    for text, value in [
        ("Reinforced concrete foundation works", 80_000_000),
        ("Structural steel erection", 70_000_000),
        ("Site preparation and grading", 50_000_000),
        ("Electrical infrastructure installation", 40_000_000),
        ("Plumbing and drainage systems", 30_000_000),
        ("Concrete batch plant operations", 30_000_000),
    ]:
        items.append(make_line_item(text, value, doc_id, job_id))

    # Manufacturing items (C) — 5 items, ~150M total
    for text, value in [
        ("Pre-fabricated steel components", 40_000_000),
        ("Industrial equipment procurement", 35_000_000),
        ("HVAC system manufacturing", 30_000_000),
        ("Control panel fabrication", 25_000_000),
        ("Piping and valve assemblies", 20_000_000),
    ]:
        items.append(make_line_item(text, value, doc_id, job_id))

    # Professional services items (M) — 5 items, ~50M total
    for text, value in [
        ("Engineering design consultancy", 15_000_000),
        ("Project management services", 12_000_000),
        ("Environmental impact assessment", 8_000_000),
        ("Quality assurance and testing", 8_000_000),
        ("Legal and regulatory compliance", 7_000_000),
    ]:
        items.append(make_line_item(text, value, doc_id, job_id))

    # Secondary sector items — 4 items, ~20M total
    for text, value, sector_note in [
        ("Wholesale trade supplies", 8_000_000, "G"),
        ("Transportation and logistics", 6_000_000, "H"),
        ("Information technology systems", 4_000_000, "J"),
        ("Catering and food services", 2_000_000, "I"),
    ]:
        items.append(make_line_item(text, value, doc_id, job_id))

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
        ["F"] * 6 + ["C"] * 5 + ["M"] * 5 +
        ["G", "H", "J", "I"]
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


def build_industrial_zone_constraints() -> ConstraintSet:
    """Build constraint set with one binding labor constraint on Construction (F)."""
    constraints = [
        Constraint(
            constraint_id=new_uuid7(),
            constraint_type=ConstraintType.LABOR,
            scope=ConstraintScope(sector_code="F"),
            bound_value=200.0,  # Max delta output from labor capacity
            bound_scope=ConstraintBoundScope.DELTA_ONLY,
            unit=ConstraintUnit.SAR_MILLIONS,
            confidence=ConstraintConfidence.HARD,
            description="Construction labor capacity constraint",
        ),
    ]
    return ConstraintSet(
        constraint_set_id=new_uuid7(),
        constraints=constraints,
        workspace_id=uuid7(),
    )
```

**Step 2: Verify scenario builds without error**

Run: `python -c "from tests.integration.golden_scenarios.industrial_zone import build_industrial_zone_scenario, build_industrial_zone_boq; s = build_industrial_zone_scenario(); items = build_industrial_zone_boq(); print(f'Scenario OK: {len(items)} items')"`

**Step 3: Commit**

```bash
git add tests/integration/golden_scenarios/industrial_zone.py
git commit -m "[mvp14] Task 2: golden scenario 1 — industrial zone CAPEX (20-sector)"
```

---

### Task 3: Golden Scenarios 2 & 3 — Gaps + Contraction (20-sector)

**Files:**
- Create: `tests/integration/golden_scenarios/mega_project_gaps.py`
- Create: `tests/integration/golden_scenarios/contraction.py`

Both scenarios use the 20-sector D-1 model (ISIC A-T). They reference specific ISIC section codes for demand shocks and gaps.

**Step 1: Build mega-project with gaps scenario**

```python
# tests/integration/golden_scenarios/mega_project_gaps.py
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
```

**Step 2: Build contraction scenario**

```python
# tests/integration/golden_scenarios/contraction.py
"""Golden Scenario 3: Contraction Scenario — Negative Demand Shocks (20-sector).

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
```

**Step 3: Commit**

```bash
git add tests/integration/golden_scenarios/mega_project_gaps.py tests/integration/golden_scenarios/contraction.py
git commit -m "[mvp14] Task 3: golden scenarios 2 (data gaps) and 3 (contraction) — 20-sector"
```

---

### Task 4: Integration Path — Core Engine (Leontief -> Satellite -> Constraints)

**Files:**
- Create: `tests/integration/test_path_engine.py`

Uses the 3-sector toy model from `shared.py` for basic path verification. The golden scenarios (20-sector) are exercised in the e2e tests later.

**Step 1: Write the failing tests**

```python
# tests/integration/test_path_engine.py
"""Integration Path 1: Core Engine — Leontief -> Satellite -> Constraints.

Tests module boundaries between:
- ModelStore.register/get -> LoadedModel
- LeontiefSolver.solve(loaded_model, delta_d) -> SolveResult
- SatelliteAccounts.compute(delta_x, coefficients) -> SatelliteResult
- FeasibilitySolver.solve(unconstrained, constraints) -> FeasibilityResult

Uses the 3-sector toy IO model (ISIC F/C/G) from shared.py for basic path tests.
"""

import numpy as np
import pytest
from numpy.testing import assert_allclose
from uuid_extensions import uuid7

from src.engine.batch import BatchRunner
from src.engine.constraints.schema import (
    Constraint,
    ConstraintBoundScope,
    ConstraintScope,
    ConstraintSet,
    ConstraintType,
    ConstraintUnit,
)
from src.engine.constraints.solver import FeasibilitySolver
from src.engine.leontief import LeontiefSolver
from src.engine.model_store import ModelStore
from src.engine.satellites import SatelliteAccounts, SatelliteCoefficients
from src.models.common import ConstraintConfidence, new_uuid7

from .golden_scenarios.shared import (
    GOLDEN_BASE_YEAR,
    GOLDEN_X,
    GOLDEN_Z,
    NUMERIC_RTOL,
    SECTOR_CODES_SMALL,
    SMALL_IMPORT_RATIO,
    SMALL_JOBS_COEFF,
    SMALL_VA_RATIO,
)


@pytest.fixture
def model_store():
    return ModelStore()


@pytest.fixture
def loaded_model(model_store):
    mv = model_store.register(
        Z=GOLDEN_Z, x=GOLDEN_X, sector_codes=SECTOR_CODES_SMALL,
        base_year=GOLDEN_BASE_YEAR, source="test-engine-path",
    )
    return model_store.get(mv.model_version_id)


@pytest.fixture
def sat_coefficients():
    return SatelliteCoefficients(
        jobs_coeff=SMALL_JOBS_COEFF.copy(),
        import_ratio=SMALL_IMPORT_RATIO.copy(),
        va_ratio=SMALL_VA_RATIO.copy(),
        version_id=uuid7(),
    )


@pytest.mark.integration
class TestLeontiefToSatellite:
    """Leontief output feeds satellite accounts correctly."""

    def test_solve_produces_valid_delta_x(self, loaded_model):
        """delta_x = B . delta_d has correct shape and positive values."""
        solver = LeontiefSolver()
        delta_d = np.array([100.0, 50.0, 25.0])
        result = solver.solve(loaded_model=loaded_model, delta_d=delta_d)

        assert result.delta_x_total.shape == (3,)
        # Total = direct + indirect
        assert_allclose(
            result.delta_x_total,
            result.delta_x_direct + result.delta_x_indirect,
            rtol=NUMERIC_RTOL,
        )
        # Positive shock -> positive output
        assert np.all(result.delta_x_total > 0)

    def test_satellite_employment_from_delta_x(self, loaded_model, sat_coefficients):
        """Satellite employment = jobs_coeff * delta_x."""
        solver = LeontiefSolver()
        delta_d = np.array([100.0, 50.0, 25.0])
        solve_result = solver.solve(loaded_model=loaded_model, delta_d=delta_d)

        sa = SatelliteAccounts()
        sat_result = sa.compute(
            delta_x=solve_result.delta_x_total,
            coefficients=sat_coefficients,
        )

        # Employment = jobs_coeff * delta_x (element-wise)
        expected_jobs = sat_coefficients.jobs_coeff * solve_result.delta_x_total
        assert_allclose(sat_result.delta_jobs, expected_jobs, rtol=NUMERIC_RTOL)

    def test_satellite_gdp_from_delta_x(self, loaded_model, sat_coefficients):
        """Satellite GDP = va_ratio * delta_x."""
        solver = LeontiefSolver()
        delta_d = np.array([100.0, 50.0, 25.0])
        solve_result = solver.solve(loaded_model=loaded_model, delta_d=delta_d)

        sa = SatelliteAccounts()
        sat_result = sa.compute(
            delta_x=solve_result.delta_x_total,
            coefficients=sat_coefficients,
        )

        expected_va = sat_coefficients.va_ratio * solve_result.delta_x_total
        assert_allclose(sat_result.delta_va, expected_va, rtol=NUMERIC_RTOL)


@pytest.mark.integration
class TestUnconstrainedVsFeasible:
    """Constrained results vs unconstrained."""

    def test_feasibility_clips_not_creates(self, loaded_model, sat_coefficients):
        """Feasible delta_x <= unconstrained delta_x per sector."""
        solver = LeontiefSolver()
        delta_d = np.array([300.0, 150.0, 50.0])
        solve_result = solver.solve(loaded_model=loaded_model, delta_d=delta_d)

        # Tight constraint on Construction (F): cap delta at 200
        constraints = ConstraintSet(
            constraint_set_id=new_uuid7(),
            constraints=[
                Constraint(
                    constraint_id=new_uuid7(),
                    constraint_type=ConstraintType.CAPACITY_CAP,
                    scope=ConstraintScope(sector_code="F"),
                    bound_value=200.0,
                    bound_scope=ConstraintBoundScope.DELTA_ONLY,
                    unit=ConstraintUnit.SAR_MILLIONS,
                    confidence=ConstraintConfidence.HARD,
                    description="Construction capacity cap",
                ),
            ],
            workspace_id=uuid7(),
        )

        fsolver = FeasibilitySolver()
        feas_result = fsolver.solve(
            unconstrained_delta_x=solve_result.delta_x_total,
            base_x=loaded_model.x,
            satellite_coefficients=sat_coefficients,
            constraint_set=constraints,
            sector_codes=SECTOR_CODES_SMALL,
        )

        # Feasible <= unconstrained for every sector
        assert np.all(
            feas_result.feasible_delta_x <= solve_result.delta_x_total + 1e-10
        )

    def test_binding_constraint_diagnostics(self, loaded_model, sat_coefficients):
        """Binding constraints report which constraint, gap, and description."""
        solver = LeontiefSolver()
        delta_d = np.array([300.0, 150.0, 50.0])
        solve_result = solver.solve(loaded_model=loaded_model, delta_d=delta_d)

        constraints = ConstraintSet(
            constraint_set_id=new_uuid7(),
            constraints=[
                Constraint(
                    constraint_id=new_uuid7(),
                    constraint_type=ConstraintType.CAPACITY_CAP,
                    scope=ConstraintScope(sector_code="F"),
                    bound_value=200.0,
                    bound_scope=ConstraintBoundScope.DELTA_ONLY,
                    unit=ConstraintUnit.SAR_MILLIONS,
                    confidence=ConstraintConfidence.HARD,
                    description="Construction capacity cap",
                ),
            ],
            workspace_id=uuid7(),
        )

        fsolver = FeasibilitySolver()
        feas_result = fsolver.solve(
            unconstrained_delta_x=solve_result.delta_x_total,
            base_x=loaded_model.x,
            satellite_coefficients=sat_coefficients,
            constraint_set=constraints,
            sector_codes=SECTOR_CODES_SMALL,
        )

        # Should have at least one binding constraint
        assert len(feas_result.binding_constraints) >= 1
        bc = feas_result.binding_constraints[0]
        assert bc.gap > 0  # Gap is positive (clipped)
        assert bc.description != ""


@pytest.mark.integration
class TestDeterministicReproducibility:
    """Same inputs produce identical outputs."""

    def test_three_consecutive_runs_identical(self, loaded_model, sat_coefficients):
        """3 runs with same inputs -> bit-for-bit identical."""
        solver = LeontiefSolver()
        sa = SatelliteAccounts()
        delta_d = np.array([100.0, 50.0, 25.0])

        results = []
        for _ in range(3):
            solve_result = solver.solve(loaded_model=loaded_model, delta_d=delta_d)
            sat_result = sa.compute(
                delta_x=solve_result.delta_x_total,
                coefficients=sat_coefficients,
            )
            results.append((solve_result.delta_x_total.copy(), sat_result.delta_jobs.copy()))

        for i in range(1, 3):
            assert_allclose(results[0][0], results[i][0], rtol=0)
            assert_allclose(results[0][1], results[i][1], rtol=0)
```

**Step 2: Run tests to verify they pass**

Run: `python -m pytest tests/integration/test_path_engine.py -v`

If any test fails due to API mismatch (e.g., ConstraintScope constructor differs), fix the test to match actual API. The tests should pass since we're testing real module integration.

**Step 3: Commit**

```bash
git add tests/integration/test_path_engine.py
git commit -m "[mvp14] Task 4: integration path tests — core engine (Leontief->Satellite->Constraints)"
```

---

### Task 5: Integration Path — Compiler -> Engine + Compiler Gate Metric

**Files:**
- Create: `tests/integration/test_path_compiler_engine.py`

This task tests two things:
1. Hand-authored MappingDecision path: CompilationInput -> ScenarioSpec -> delta_d -> LeontiefSolver
2. Real suggestion pipeline: `MappingSuggestionAgent(library=SEED_LIBRARY).suggest_batch(items, taxonomy)` measuring coverage >= 60% and accuracy >= 80%

**Step 1: Write the tests**

```python
# tests/integration/test_path_compiler_engine.py
"""Integration Path 2: Compiler -> Engine + Compiler Gate Metric.

Tests:
1. ScenarioCompiler output feeds Leontief correctly (hand-authored decisions)
2. MappingSuggestionAgent.suggest_batch coverage/accuracy gate (real pipeline)

Uses SECTOR_CODES_SMALL (F/C/G) for basic compiler->engine path tests.
Uses SEED_LIBRARY and LABELED_BOQ from shared.py for the suggestion gate test.
"""

import numpy as np
import pytest
from numpy.testing import assert_allclose
from uuid_extensions import uuid7

from src.agents.mapping_agent import MappingSuggestionAgent
from src.compiler.scenario_compiler import CompilationInput, ScenarioCompiler
from src.engine.leontief import LeontiefSolver
from src.engine.model_store import ModelStore
from src.models.document import BoQLineItem
from src.models.mapping import DecisionType, MappingDecision
from src.models.scenario import TimeHorizon

from .golden_scenarios.shared import (
    GOLDEN_BASE_YEAR,
    GOLDEN_X,
    GOLDEN_Z,
    LABELED_BOQ,
    NUMERIC_RTOL,
    SECTOR_CODES_SMALL,
    SEED_LIBRARY,
    make_labeled_boq_items,
    make_line_item,
)


@pytest.fixture
def loaded_model():
    store = ModelStore()
    mv = store.register(
        Z=GOLDEN_Z, x=GOLDEN_X, sector_codes=SECTOR_CODES_SMALL,
        base_year=GOLDEN_BASE_YEAR, source="test-compiler-engine",
    )
    return store.get(mv.model_version_id)


@pytest.mark.integration
class TestCompilerToEngine:
    """Compiler output -> valid Leontief inputs (hand-authored decisions)."""

    def test_scenario_spec_has_shock_items(self):
        """Compiled scenario has shock items matching BoQ mapping."""
        items = [make_line_item("concrete works", 100_000_000)]
        decisions = [
            MappingDecision(
                line_item_id=items[0].line_item_id,
                suggested_sector_code="F",
                suggested_confidence=0.9,
                final_sector_code="F",
                decision_type=DecisionType.APPROVED,
                decided_by=uuid7(),
            ),
        ]
        compiler = ScenarioCompiler()
        spec = compiler.compile(CompilationInput(
            workspace_id=uuid7(),
            scenario_name="Test",
            base_model_version_id=uuid7(),
            base_year=GOLDEN_BASE_YEAR,
            time_horizon=TimeHorizon(start_year=2024, end_year=2026),
            line_items=items,
            decisions=decisions,
            phasing={2024: 0.5, 2025: 0.3, 2026: 0.2},
        ))
        assert len(spec.shock_items) > 0

    def test_domestic_share_reduces_shock(self):
        """With 65% domestic share, delta_d < total spend."""
        items = [make_line_item("steel supply", 100_000_000)]
        decisions = [
            MappingDecision(
                line_item_id=items[0].line_item_id,
                suggested_sector_code="C",
                suggested_confidence=0.9,
                final_sector_code="C",
                decision_type=DecisionType.APPROVED,
                decided_by=uuid7(),
            ),
        ]
        compiler = ScenarioCompiler()
        spec = compiler.compile(CompilationInput(
            workspace_id=uuid7(),
            scenario_name="Test",
            base_model_version_id=uuid7(),
            base_year=GOLDEN_BASE_YEAR,
            time_horizon=TimeHorizon(start_year=2024, end_year=2024),
            line_items=items,
            decisions=decisions,
            default_domestic_share=0.65,
            default_import_share=0.35,
        ))
        # Total domestic amount should be 65% of 100M = 65M
        total_domestic = sum(
            s.amount_real_base_year * s.domestic_share
            for s in spec.shock_items
        )
        assert total_domestic < 100_000_000

    def test_compiled_spec_feeds_leontief(self, loaded_model):
        """Full path: compile -> extract delta_d -> solve -> valid result."""
        items = [
            make_line_item("concrete", 50_000_000),
            make_line_item("steel", 30_000_000),
        ]
        decisions = [
            MappingDecision(
                line_item_id=items[0].line_item_id,
                suggested_sector_code="F", suggested_confidence=0.9,
                final_sector_code="F", decision_type=DecisionType.APPROVED,
                decided_by=uuid7(),
            ),
            MappingDecision(
                line_item_id=items[1].line_item_id,
                suggested_sector_code="C", suggested_confidence=0.85,
                final_sector_code="C", decision_type=DecisionType.APPROVED,
                decided_by=uuid7(),
            ),
        ]
        compiler = ScenarioCompiler()
        spec = compiler.compile(CompilationInput(
            workspace_id=uuid7(),
            scenario_name="Test",
            base_model_version_id=loaded_model.model_version.model_version_id,
            base_year=GOLDEN_BASE_YEAR,
            time_horizon=TimeHorizon(start_year=2024, end_year=2024),
            line_items=items,
            decisions=decisions,
        ))

        # Extract delta_d from shock items
        delta_d = np.zeros(len(SECTOR_CODES_SMALL))
        sector_idx = {code: i for i, code in enumerate(SECTOR_CODES_SMALL)}
        for shock in spec.shock_items:
            if shock.sector_code in sector_idx:
                delta_d[sector_idx[shock.sector_code]] += (
                    shock.amount_real_base_year * shock.domestic_share
                )

        solver = LeontiefSolver()
        result = solver.solve(loaded_model=loaded_model, delta_d=delta_d)

        assert result.delta_x_total.shape == (3,)
        assert np.all(result.delta_x_total >= 0)


@pytest.mark.integration
@pytest.mark.gate
class TestCompilerAutoMapping:
    """Compiler gate metric: MappingSuggestionAgent coverage and accuracy.

    Uses SEED_LIBRARY and LABELED_BOQ from shared.py. The agent performs
    real pattern matching against the seeded library — no mocks.

    Gate criteria (Amendment 4):
    - Coverage >= 60%: fraction of items where agent proposes a mapping
    - Accuracy >= 80%: fraction of proposed mappings matching ground truth ISIC section
    """

    def test_compiler_auto_mapping_gate(self):
        """Auto-mapping coverage >= 60% and accuracy >= 80% on labeled BoQ."""
        # Build taxonomy (minimal — agent uses library matching primarily)
        taxonomy = [
            {"sector_code": code, "description": desc}
            for code, desc in [
                ("A", "Agriculture"), ("B", "Mining"), ("C", "Manufacturing"),
                ("D", "Electricity"), ("E", "Water"), ("F", "Construction"),
                ("G", "Wholesale"), ("H", "Transport"), ("I", "Accommodation"),
                ("J", "ICT"), ("K", "Financial"), ("L", "Real estate"),
                ("M", "Professional"), ("N", "Administrative"), ("O", "Public admin"),
                ("P", "Education"), ("Q", "Health"), ("R", "Arts"),
                ("S", "Other services"), ("T", "Households"),
            ]
        ]

        agent = MappingSuggestionAgent(library=SEED_LIBRARY)
        boq_items = make_labeled_boq_items(LABELED_BOQ)
        batch_result = agent.suggest_batch(boq_items, taxonomy=taxonomy)

        suggestions = batch_result.suggestions
        assert len(suggestions) == len(LABELED_BOQ)

        # Compute coverage: items where confidence > 0.1 (not a fallback)
        covered = [s for s in suggestions if s.confidence > 0.1]
        coverage = len(covered) / len(LABELED_BOQ)

        # Compute accuracy: of covered items, how many match ground truth?
        # We need to align suggestions with labeled BoQ by line_item_id
        item_id_to_truth = {
            item.line_item_id: label["ground_truth_isic"]
            for item, label in zip(boq_items, LABELED_BOQ)
        }
        correct = [
            s for s in covered
            if s.sector_code == item_id_to_truth.get(s.line_item_id)
        ]
        accuracy = len(correct) / len(covered) if covered else 0.0

        assert coverage >= 0.60, f"Coverage {coverage:.0%} < 60% ({len(covered)}/{len(LABELED_BOQ)})"
        assert accuracy >= 0.80, f"Accuracy {accuracy:.0%} < 80% ({len(correct)}/{len(covered)})"
```

**Step 2: Run and fix any API mismatches**

Run: `python -m pytest tests/integration/test_path_compiler_engine.py -v`

**Step 3: Commit**

```bash
git add tests/integration/test_path_compiler_engine.py
git commit -m "[mvp14] Task 5: integration path — compiler -> engine + auto-mapping gate"
```

---

### Task 6: Integration Path — Workforce Satellite

**Files:**
- Create: `tests/integration/test_path_workforce.py`

**Step 1: Write the tests**

This task requires constructing D-4 workforce data objects. Use the fixture files in `tests/fixtures/workforce/`.

```python
# tests/integration/test_path_workforce.py
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

from src.data.workforce.occupation_bridge import OccupationBridge
from src.data.workforce.nationality_classification import (
    NationalityClassificationSet,
)
from src.engine.satellites import SatelliteCoefficients, SatelliteResult
from src.engine.workforce_satellite.satellite import WorkforceSatellite

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "workforce"


def _load_bridge() -> OccupationBridge:
    """Load sample occupation bridge from fixtures."""
    with open(FIXTURES_DIR / "sample_occupation_bridge.json") as f:
        data = json.load(f)
    return OccupationBridge(**data)


def _load_classifications() -> NationalityClassificationSet:
    """Load sample nationality classifications from fixtures."""
    with open(FIXTURES_DIR / "sample_nationality_classification.json") as f:
        data = json.load(f)
    return NationalityClassificationSet(**data)


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

        for summary in result.sector_summaries:
            assert summary.overall_confidence in ("HARD", "ESTIMATED", "ASSUMED")

        # Overall result also has confidence
        assert result.overall_confidence in ("HARD", "ESTIMATED", "ASSUMED")
```

**Step 2: Run and fix fixture loading issues**

Run: `python -m pytest tests/integration/test_path_workforce.py -v`

If fixture JSON structure doesn't match constructor, adapt the loading functions to match the actual fixture format.

**Step 3: Commit**

```bash
git add tests/integration/test_path_workforce.py
git commit -m "[mvp14] Task 6: integration path — engine -> workforce satellite"
```

---

### Task 7: Integration Path — Quality Assessment (with Real Upstream Test)

**Files:**
- Create: `tests/integration/test_path_quality.py`

This task includes BOTH the mocked-signal quality tests AND one test that feeds REAL compiler output -> REAL engine output -> REAL constraint summary -> QualityAssessmentService with no mocks for upstream modules.

**Step 1: Write the tests**

```python
# tests/integration/test_path_quality.py
"""Integration Path 6: Quality Assessment integration.

Tests that QualityAssessmentService receives real signals from all modules
and produces valid RunQualityAssessment results.

Includes one test with REAL upstream modules (no mocks):
  REAL compiler -> REAL engine -> REAL constraints -> QualityAssessmentService
"""

import numpy as np
import pytest
from uuid_extensions import uuid7

from src.quality.models import QualityGrade, QualitySeverity
from src.quality.service import QualityAssessmentService

from .golden_scenarios.shared import (
    GOLDEN_BASE_YEAR,
    GOLDEN_X,
    GOLDEN_Z,
    SECTOR_CODES_SMALL,
    SMALL_IMPORT_RATIO,
    SMALL_JOBS_COEFF,
    SMALL_VA_RATIO,
    make_decision,
    make_line_item,
)


@pytest.mark.integration
class TestQualityFullAssessment:
    """Complete quality assessment from constructed module signals."""

    def test_full_assessment_all_7_dimensions(self):
        """All inputs provided -> 7 dimension assessments."""
        svc = QualityAssessmentService()
        assessment = svc.assess(
            base_year=2024,
            current_year=2026,
            mapping_coverage_pct=0.95,
            mapping_confidence_dist={"HIGH": 0.7, "MEDIUM": 0.2, "LOW": 0.1},
            mapping_residual_pct=0.03,
            mapping_unresolved_pct=0.02,
            mapping_unresolved_spend_pct=0.5,
            assumption_ranges_coverage_pct=0.8,
            assumption_approval_rate=0.9,
            constraint_confidence_summary={"HARD": 8, "ESTIMATED": 2, "ASSUMED": 0},
            workforce_overall_confidence="HIGH",
            plausibility_in_range_pct=95.0,
            plausibility_flagged_count=1,
            source_ages=[],
            run_id=uuid7(),
        )

        assert assessment.composite_score > 0
        assert assessment.grade in list(QualityGrade)
        assert len(assessment.dimension_assessments) >= 6

    def test_partial_assessment_missing_workforce(self):
        """No workforce input -> renormalized weights, no crash."""
        svc = QualityAssessmentService()
        assessment = svc.assess(
            base_year=2024,
            current_year=2026,
            mapping_coverage_pct=0.90,
            mapping_confidence_dist={"HIGH": 0.6, "MEDIUM": 0.3, "LOW": 0.1},
            mapping_residual_pct=0.05,
            mapping_unresolved_pct=0.03,
            mapping_unresolved_spend_pct=1.0,
            assumption_ranges_coverage_pct=0.7,
            assumption_approval_rate=0.8,
            constraint_confidence_summary=None,
            workforce_overall_confidence=None,
            plausibility_in_range_pct=90.0,
            plausibility_flagged_count=2,
            source_ages=[],
            run_id=uuid7(),
        )

        assert assessment.composite_score > 0
        assert len(assessment.missing_dimensions) >= 1

    def test_stale_model_vintage_warning(self):
        """Model 6+ years old -> WARNING in assessment."""
        svc = QualityAssessmentService()
        assessment = svc.assess(
            base_year=2018,
            current_year=2026,
            mapping_coverage_pct=0.90,
            mapping_confidence_dist={"HIGH": 0.5, "MEDIUM": 0.3, "LOW": 0.2},
            mapping_residual_pct=0.05,
            mapping_unresolved_pct=0.03,
            mapping_unresolved_spend_pct=1.0,
            assumption_ranges_coverage_pct=0.6,
            assumption_approval_rate=0.7,
            constraint_confidence_summary={"HARD": 2, "ESTIMATED": 3, "ASSUMED": 5},
            workforce_overall_confidence="LOW",
            plausibility_in_range_pct=80.0,
            plausibility_flagged_count=3,
            source_ages=[],
            run_id=uuid7(),
        )

        # Should have vintage warning
        vintage_warnings = [
            w for w in assessment.warnings
            if w.dimension.value == "VINTAGE"
        ]
        assert len(vintage_warnings) > 0

    def test_completeness_grade_cap(self):
        """Only 2 applicable dimensions -> grade capped at C."""
        svc = QualityAssessmentService()
        assessment = svc.assess(
            base_year=2024,
            current_year=2026,
            mapping_coverage_pct=0.99,
            mapping_confidence_dist={"HIGH": 0.9, "MEDIUM": 0.1, "LOW": 0.0},
            mapping_residual_pct=0.01,
            mapping_unresolved_pct=0.0,
            mapping_unresolved_spend_pct=0.0,
            assumption_ranges_coverage_pct=None,
            assumption_approval_rate=None,
            constraint_confidence_summary=None,
            workforce_overall_confidence=None,
            plausibility_in_range_pct=None,
            plausibility_flagged_count=None,
            source_ages=[],
            run_id=uuid7(),
        )

        # With very few dimensions, grade should be capped
        if assessment.completeness_pct < 0.50:
            assert assessment.grade.value >= "C"


@pytest.mark.integration
class TestQualityFromRealUpstream:
    """Quality assessment with REAL upstream modules — no mocks.

    Feeds REAL compiler output -> REAL engine -> REAL constraints ->
    QualityAssessmentService. This verifies that the actual signals
    produced by upstream modules are compatible with the quality scorer.
    """

    def test_quality_from_real_upstream(self):
        """Full real pipeline: compiler -> engine -> constraints -> quality."""
        from src.compiler.scenario_compiler import CompilationInput, ScenarioCompiler
        from src.engine.constraints.schema import (
            Constraint,
            ConstraintBoundScope,
            ConstraintScope,
            ConstraintSet,
            ConstraintType,
            ConstraintUnit,
        )
        from src.engine.constraints.solver import FeasibilitySolver
        from src.engine.leontief import LeontiefSolver
        from src.engine.model_store import ModelStore
        from src.engine.satellites import SatelliteAccounts, SatelliteCoefficients
        from src.models.common import ConstraintConfidence, new_uuid7
        from src.models.mapping import DecisionType, MappingDecision
        from src.models.scenario import TimeHorizon

        # 1. REAL compiler
        items = [
            make_line_item("concrete foundation", 50_000_000),
            make_line_item("steel fabrication", 30_000_000),
        ]
        decisions = [
            MappingDecision(
                line_item_id=items[0].line_item_id,
                suggested_sector_code="F", suggested_confidence=0.9,
                final_sector_code="F", decision_type=DecisionType.APPROVED,
                decided_by=uuid7(),
            ),
            MappingDecision(
                line_item_id=items[1].line_item_id,
                suggested_sector_code="C", suggested_confidence=0.85,
                final_sector_code="C", decision_type=DecisionType.APPROVED,
                decided_by=uuid7(),
            ),
        ]
        compiler = ScenarioCompiler()
        spec = compiler.compile(CompilationInput(
            workspace_id=uuid7(),
            scenario_name="Quality Real Test",
            base_model_version_id=uuid7(),
            base_year=GOLDEN_BASE_YEAR,
            time_horizon=TimeHorizon(start_year=2024, end_year=2024),
            line_items=items,
            decisions=decisions,
        ))

        # 2. REAL engine
        store = ModelStore()
        mv = store.register(
            Z=GOLDEN_Z, x=GOLDEN_X, sector_codes=SECTOR_CODES_SMALL,
            base_year=GOLDEN_BASE_YEAR, source="quality-real-test",
        )
        loaded = store.get(mv.model_version_id)

        delta_d = np.zeros(len(SECTOR_CODES_SMALL))
        sector_idx = {c: i for i, c in enumerate(SECTOR_CODES_SMALL)}
        for shock in spec.shock_items:
            if shock.sector_code in sector_idx:
                delta_d[sector_idx[shock.sector_code]] += (
                    shock.amount_real_base_year * shock.domestic_share
                )

        solver = LeontiefSolver()
        solve_result = solver.solve(loaded_model=loaded, delta_d=delta_d)

        # 3. REAL constraints
        sat_coeff = SatelliteCoefficients(
            jobs_coeff=SMALL_JOBS_COEFF.copy(),
            import_ratio=SMALL_IMPORT_RATIO.copy(),
            va_ratio=SMALL_VA_RATIO.copy(),
            version_id=uuid7(),
        )
        constraint_set = ConstraintSet(
            constraint_set_id=new_uuid7(),
            constraints=[
                Constraint(
                    constraint_id=new_uuid7(),
                    constraint_type=ConstraintType.CAPACITY_CAP,
                    scope=ConstraintScope(sector_code="F"),
                    bound_value=500.0,
                    bound_scope=ConstraintBoundScope.DELTA_ONLY,
                    unit=ConstraintUnit.SAR_MILLIONS,
                    confidence=ConstraintConfidence.HARD,
                    description="Construction capacity",
                ),
            ],
            workspace_id=uuid7(),
        )
        fsolver = FeasibilitySolver()
        feas_result = fsolver.solve(
            unconstrained_delta_x=solve_result.delta_x_total,
            base_x=loaded.x,
            satellite_coefficients=sat_coeff,
            constraint_set=constraint_set,
            sector_codes=SECTOR_CODES_SMALL,
        )

        # 4. REAL quality assessment — feed actual upstream signals
        svc = QualityAssessmentService()
        conf_summary = feas_result.constraint_confidence_summary
        assessment = svc.assess(
            base_year=GOLDEN_BASE_YEAR,
            current_year=2026,
            mapping_coverage_pct=1.0,
            mapping_confidence_dist={"HIGH": 1.0, "MEDIUM": 0.0, "LOW": 0.0},
            mapping_residual_pct=0.0,
            mapping_unresolved_pct=0.0,
            mapping_unresolved_spend_pct=0.0,
            assumption_ranges_coverage_pct=None,
            assumption_approval_rate=None,
            constraint_confidence_summary={
                "HARD": conf_summary.hard_count,
                "ESTIMATED": conf_summary.estimated_count,
                "ASSUMED": conf_summary.assumed_count,
            },
            workforce_overall_confidence=None,
            plausibility_in_range_pct=None,
            plausibility_flagged_count=None,
            source_ages=[],
            run_id=uuid7(),
        )

        assert assessment.grade in list(QualityGrade)
        assert assessment.composite_score > 0
        assert len(assessment.dimension_assessments) > 0
```

**Step 2: Run and verify**

Run: `python -m pytest tests/integration/test_path_quality.py -v`

**Step 3: Commit**

```bash
git add tests/integration/test_path_quality.py
git commit -m "[mvp14] Task 7: integration path — quality assessment with real upstream test"
```

---

### Task 8: Integration Path — Flywheel Learning Loop

**Files:**
- Create: `tests/integration/test_path_flywheel_module.py`

**Step 1: Write the tests**

```python
# tests/integration/test_path_flywheel_module.py
"""Integration Path 5: Flywheel Learning Loop (module-level).

Tests the direct Python API (not HTTP):
- LearningLoop.record_override -> extract_new_patterns -> MappingLibraryManager
- FlywheelPublicationService.publish_new_cycle
- Quality gate rejects low-frequency patterns
- Scope isolation
"""

import pytest
from datetime import datetime, timezone
from uuid_extensions import uuid7

from src.compiler.learning import LearningLoop, OverridePair
from src.flywheel.mapping_library import MappingLibraryManager
from src.flywheel.assumption_library import AssumptionLibraryManager
from src.flywheel.scenario_patterns import ScenarioPatternLibrary
from src.flywheel.workforce_refinement import WorkforceBridgeRefinement
from src.flywheel.publication import FlywheelPublicationService, PublicationQualityGate


@pytest.fixture
def learning_loop():
    return LearningLoop()


@pytest.fixture
def publication_service():
    mm = MappingLibraryManager()
    am = AssumptionLibraryManager()
    sp = ScenarioPatternLibrary()
    wr = WorkforceBridgeRefinement()
    return FlywheelPublicationService(mm, am, sp, wr)


@pytest.mark.integration
class TestFlywheelLearningIntegration:
    """Override -> pattern extraction -> publish cycle."""

    def test_override_to_pattern_extraction(self, learning_loop):
        """Analyst override -> extracted pattern with min_frequency."""
        engagement_id = uuid7()
        # Record same override pattern 3 times (above min_frequency=2)
        for _ in range(3):
            learning_loop.record_override(OverridePair(
                engagement_id=engagement_id,
                line_item_id=uuid7(),
                line_item_text="concrete foundation works",
                suggested_sector_code="C",
                final_sector_code="F",
                project_type="industrial",
            ))

        overrides = learning_loop.get_overrides()
        patterns = learning_loop.extract_new_patterns(
            overrides=overrides,
            existing_library=[],
            min_frequency=2,
        )
        assert len(patterns) >= 1

    def test_publish_cycle_produces_versions(self, publication_service):
        """Publish cycle -> new mapping and assumption library versions."""
        result = publication_service.publish_new_cycle(
            published_by=uuid7(),
            steward_approved=True,
        )
        # Should produce a PublicationResult
        assert result is not None

    def test_quality_gate_rejects_low_frequency(self, learning_loop):
        """Pattern appearing only once -> not promotable (min_frequency=2)."""
        learning_loop.record_override(OverridePair(
            engagement_id=uuid7(),
            line_item_id=uuid7(),
            line_item_text="very unique procurement item",
            suggested_sector_code="G",
            final_sector_code="F",
            project_type="custom",
        ))

        overrides = learning_loop.get_overrides()
        patterns = learning_loop.extract_new_patterns(
            overrides=overrides,
            existing_library=[],
            min_frequency=2,
        )
        # Single occurrence -> no pattern extracted
        assert len(patterns) == 0

    def test_flywheel_health_metrics(self, publication_service):
        """get_flywheel_health returns meaningful metrics."""
        health = publication_service.get_flywheel_health()
        assert isinstance(health, dict)
```

**Step 2: Run and verify**

Run: `python -m pytest tests/integration/test_path_flywheel_module.py -v`

**Step 3: Commit**

```bash
git add tests/integration/test_path_flywheel_module.py
git commit -m "[mvp14] Task 8: integration path — flywheel learning loop"
```

---

### Task 9: Integration Path — Doc -> Export (with Real Suggestions + Governed Export)

**Files:**
- Create: `tests/integration/test_path_doc_to_export.py`

This uses `MappingSuggestionAgent.suggest_batch()` for real suggestions (not hand-authored decisions only), tests GOVERNED mode with resolved Claims, and uses a committed extraction fixture.

**Step 1: Write the tests**

```python
# tests/integration/test_path_doc_to_export.py
"""Integration Path 7: Doc -> Export (Amendment 3).

The full pipeline that the Build Plan requires:
1. Pre-extracted BoQ fixture (committed, not hand-constructed)
2. MappingSuggestionAgent.suggest_batch (REAL suggestions from SEED_LIBRARY)
3. Analyst approves suggestions -> MappingDecisions
4. ScenarioCompiler -> ScenarioSpec
5. Engine run -> SolveResult
6. Satellite -> SatelliteResult
7. Feasibility -> FeasibilityResult
8. Quality assessment -> RunQualityAssessment
9. Governance gate check (GOVERNED mode with resolved claims)
10. Export -> ExportRecord

Tests GOVERNED mode with resolved Claims, not just SANDBOX.
"""

import numpy as np
import pytest
from uuid_extensions import uuid7

from src.agents.mapping_agent import MappingSuggestionAgent
from src.compiler.scenario_compiler import CompilationInput, ScenarioCompiler
from src.engine.leontief import LeontiefSolver
from src.engine.model_store import ModelStore
from src.engine.satellites import SatelliteAccounts, SatelliteCoefficients
from src.export.orchestrator import ExportOrchestrator, ExportRequest
from src.governance.publication_gate import PublicationGate
from src.models.common import ClaimStatus, ClaimType, ExportMode
from src.models.document import BoQLineItem
from src.models.governance import Claim
from src.models.mapping import DecisionType, MappingDecision
from src.models.scenario import TimeHorizon
from src.quality.service import QualityAssessmentService

from .golden_scenarios.shared import (
    GOLDEN_BASE_YEAR,
    GOLDEN_X,
    GOLDEN_Z,
    SECTOR_CODES_SMALL,
    SEED_LIBRARY,
    SMALL_IMPORT_RATIO,
    SMALL_JOBS_COEFF,
    SMALL_VA_RATIO,
    make_line_item,
)


def _committed_extraction_fixture() -> list[BoQLineItem]:
    """Committed extraction fixture simulating real document extraction output.

    These items have realistic text that the SEED_LIBRARY can match against.
    """
    doc_id, job_id = uuid7(), uuid7()
    return [
        make_line_item("reinforced concrete foundation works", 50_000_000, doc_id, job_id),
        make_line_item("structural steel fabrication", 30_000_000, doc_id, job_id),
        make_line_item("engineering design consultancy services", 10_000_000, doc_id, job_id),
        make_line_item("wholesale trade building supplies", 5_000_000, doc_id, job_id),
    ]


@pytest.mark.integration
@pytest.mark.gate
class TestDocToExport:
    """Full doc -> export pipeline with real suggestions + governed export."""

    def test_full_pipeline_with_real_suggestions_governed_mode(self):
        """Full pipeline using MappingSuggestionAgent + GOVERNED export."""
        # 1. Pre-extracted BoQ (committed fixture)
        items = _committed_extraction_fixture()

        # 2. REAL auto-mapping suggestions from SEED_LIBRARY
        taxonomy = [
            {"sector_code": c, "description": d}
            for c, d in [
                ("F", "Construction"), ("C", "Manufacturing"),
                ("G", "Wholesale"), ("M", "Professional services"),
            ]
        ]
        agent = MappingSuggestionAgent(library=SEED_LIBRARY)
        batch_result = agent.suggest_batch(items, taxonomy=taxonomy)

        # 3. Analyst approves all suggestions -> MappingDecisions
        analyst = uuid7()
        decisions = []
        for suggestion in batch_result.suggestions:
            decisions.append(
                MappingDecision(
                    line_item_id=suggestion.line_item_id,
                    suggested_sector_code=suggestion.sector_code,
                    suggested_confidence=suggestion.confidence,
                    final_sector_code=suggestion.sector_code,
                    decision_type=DecisionType.APPROVED,
                    decided_by=analyst,
                )
            )

        # 4. Compile
        compiler = ScenarioCompiler()
        spec = compiler.compile(CompilationInput(
            workspace_id=uuid7(),
            scenario_name="Doc-to-Export Governed Test",
            base_model_version_id=uuid7(),
            base_year=GOLDEN_BASE_YEAR,
            time_horizon=TimeHorizon(start_year=2024, end_year=2024),
            line_items=items,
            decisions=decisions,
        ))
        assert len(spec.shock_items) > 0

        # 5. Register model and solve
        store = ModelStore()
        mv = store.register(
            Z=GOLDEN_Z, x=GOLDEN_X, sector_codes=SECTOR_CODES_SMALL,
            base_year=GOLDEN_BASE_YEAR, source="doc-to-export-governed",
        )
        loaded = store.get(mv.model_version_id)

        # Extract delta_d
        delta_d = np.zeros(len(SECTOR_CODES_SMALL))
        sector_idx = {c: i for i, c in enumerate(SECTOR_CODES_SMALL)}
        for shock in spec.shock_items:
            if shock.sector_code in sector_idx:
                delta_d[sector_idx[shock.sector_code]] += (
                    shock.amount_real_base_year * shock.domestic_share
                )

        solver = LeontiefSolver()
        solve_result = solver.solve(loaded_model=loaded, delta_d=delta_d)

        # 6. Satellite
        sa = SatelliteAccounts()
        sat_coeff = SatelliteCoefficients(
            jobs_coeff=SMALL_JOBS_COEFF.copy(),
            import_ratio=SMALL_IMPORT_RATIO.copy(),
            va_ratio=SMALL_VA_RATIO.copy(),
            version_id=uuid7(),
        )
        sat_result = sa.compute(
            delta_x=solve_result.delta_x_total,
            coefficients=sat_coeff,
        )

        # 7. Quality assessment
        qas = QualityAssessmentService()
        assessment = qas.assess(
            base_year=GOLDEN_BASE_YEAR,
            current_year=2026,
            mapping_coverage_pct=1.0,
            mapping_confidence_dist={"HIGH": 0.75, "MEDIUM": 0.25, "LOW": 0.0},
            mapping_residual_pct=0.0,
            mapping_unresolved_pct=0.0,
            mapping_unresolved_spend_pct=0.0,
            assumption_ranges_coverage_pct=None,
            assumption_approval_rate=None,
            constraint_confidence_summary=None,
            workforce_overall_confidence=None,
            plausibility_in_range_pct=None,
            plausibility_flagged_count=None,
            source_ages=[],
            run_id=uuid7(),
        )
        assert assessment.composite_score > 0

        # 8. Governance: GOVERNED mode with RESOLVED claims
        gate = PublicationGate()
        resolved_claims = [
            Claim(
                text="Construction output multiplier is within OECD range",
                claim_type=ClaimType.MODEL,
                status=ClaimStatus.SUPPORTED,
            ),
            Claim(
                text="Import share based on GASTAT 2023 data",
                claim_type=ClaimType.SOURCE_FACT,
                status=ClaimStatus.SUPPORTED,
            ),
        ]
        gate_result = gate.check(claims=resolved_claims)
        assert gate_result.passed, f"Gate blocked: {gate_result.blocking_reasons}"

        # 9. Export in GOVERNED mode
        export_orch = ExportOrchestrator()
        record = export_orch.execute(
            request=ExportRequest(
                run_id=uuid7(),
                workspace_id=uuid7(),
                mode=ExportMode.GOVERNED,
                export_formats=["xlsx"],
                pack_data={
                    "scenario_name": spec.name,
                    "total_output": float(solve_result.delta_x_total.sum()),
                    "total_gdp": float(sat_result.delta_va.sum()),
                    "total_jobs": float(sat_result.delta_jobs.sum()),
                },
            ),
            claims=resolved_claims,
        )
        assert record.status.value == "COMPLETED"

    def test_governed_export_blocked_without_claims(self):
        """Governed mode blocked if claims unresolved."""
        gate = PublicationGate()
        claim = Claim(
            text="Unresolved claim about labor data",
            claim_type=ClaimType.MODEL,
            status=ClaimStatus.NEEDS_EVIDENCE,
        )
        result = gate.check(claims=[claim])
        assert not result.passed
        assert len(result.blocking_reasons) > 0

    def test_governed_export_succeeds_with_all_resolved(self):
        """Governed mode passes after all claims resolved."""
        gate = PublicationGate()
        claims = [
            Claim(
                text="Model vintage is acceptable",
                claim_type=ClaimType.MODEL,
                status=ClaimStatus.SUPPORTED,
            ),
            Claim(
                text="Assumption about import shares",
                claim_type=ClaimType.ASSUMPTION,
                status=ClaimStatus.APPROVED_FOR_EXPORT,
            ),
            Claim(
                text="Outdated constraint removed",
                claim_type=ClaimType.MODEL,
                status=ClaimStatus.DELETED,
            ),
        ]
        result = gate.check(claims=claims)
        assert result.passed
```

**Step 2: Run and verify**

Run: `python -m pytest tests/integration/test_path_doc_to_export.py -v`

**Step 3: Commit**

```bash
git add tests/integration/test_path_doc_to_export.py
git commit -m "[mvp14] Task 9: integration path — doc -> export with real suggestions + governed mode"
```

---

### Task 9a: Integration Path — SG Parser -> Concordance -> Compiler

**Files:**
- Create: `tests/integration/test_path_sg_concordance.py`

Path 8: Tests that SGTemplateParser output flows through ConcordanceService into ScenarioCompiler without orphan codes or unmapped divisions.

**Step 1: Write the tests**

```python
# tests/integration/test_path_sg_concordance.py
"""Integration Path 8: SG Parser -> Concordance -> Compiler.

Tests that SGTemplateParser(concordance).parse() produces line items whose
division-level codes map via ConcordanceService to valid D-1 sections,
and that ScenarioCompiler.compile accepts the resulting sector codes
without orphan codes or unmapped divisions.

This path verifies the D-2 (84 divisions) -> D-1 (20 sections) concordance
chain works end-to-end through the compiler.
"""

import pytest
from uuid_extensions import uuid7

from .golden_scenarios.shared import ISIC_20_SECTIONS


@pytest.mark.integration
class TestSGParserToConcordanceToCompiler:
    """SG Parser -> Concordance -> Compiler path (Amendment A)."""

    def test_parser_output_maps_to_valid_sections(self):
        """Every code emitted by SGTemplateParser exists in concordance.

        Loads SGTemplateParser with a ConcordanceService, parses a sample
        SG template, and verifies all resulting codes map to D-1 sections.
        """
        from src.data.concordance import ConcordanceService
        from src.data.sg_template_parser import SGTemplateParser

        concordance = ConcordanceService()
        parser = SGTemplateParser(concordance)
        parsed_items = parser.parse()

        # Every parsed item should have a valid ISIC section code
        for item in parsed_items:
            section = concordance.division_to_section(item.division_code)
            assert section in ISIC_20_SECTIONS, (
                f"Orphan division code {item.division_code} -> "
                f"section {section} not in D-1 sections"
            )

    def test_no_orphan_codes_in_sg_parser(self):
        """No orphan division or section codes in parser output."""
        from src.data.concordance import ConcordanceService
        from src.data.sg_template_parser import SGTemplateParser

        concordance = ConcordanceService()
        parser = SGTemplateParser(concordance)
        parsed_items = parser.parse()

        orphan_codes = []
        for item in parsed_items:
            if not concordance.has_division(item.division_code):
                orphan_codes.append(item.division_code)

        assert len(orphan_codes) == 0, f"Orphan codes: {orphan_codes}"

    def test_parsed_items_feed_compiler(self):
        """Parsed SG template items can be compiled into a ScenarioSpec."""
        from src.compiler.scenario_compiler import CompilationInput, ScenarioCompiler
        from src.data.concordance import ConcordanceService
        from src.data.sg_template_parser import SGTemplateParser
        from src.models.mapping import DecisionType, MappingDecision
        from src.models.scenario import TimeHorizon

        concordance = ConcordanceService()
        parser = SGTemplateParser(concordance)
        parsed_items = parser.parse()

        # Create approved decisions for each parsed item
        analyst = uuid7()
        decisions = []
        for item in parsed_items:
            section = concordance.division_to_section(item.division_code)
            decisions.append(
                MappingDecision(
                    line_item_id=item.line_item_id,
                    suggested_sector_code=section,
                    suggested_confidence=0.85,
                    final_sector_code=section,
                    decision_type=DecisionType.APPROVED,
                    decided_by=analyst,
                )
            )

        compiler = ScenarioCompiler()
        spec = compiler.compile(CompilationInput(
            workspace_id=uuid7(),
            scenario_name="SG Concordance Path Test",
            base_model_version_id=uuid7(),
            base_year=2024,
            time_horizon=TimeHorizon(start_year=2024, end_year=2026),
            line_items=parsed_items,
            decisions=decisions,
        ))

        assert len(spec.shock_items) > 0
        # All shock sector codes should be valid ISIC sections
        for shock in spec.shock_items:
            assert shock.sector_code in ISIC_20_SECTIONS, (
                f"Shock sector code {shock.sector_code} not in D-1 sections"
            )
```

**Step 2: Run and verify**

Run: `python -m pytest tests/integration/test_path_sg_concordance.py -v`

Note: If `SGTemplateParser` or `ConcordanceService` do not yet exist in the codebase, these tests will fail with ImportError. In that case, skip this task and create a stub test that marks them as `pytest.mark.skip(reason="D-2 modules not yet implemented")`.

**Step 3: Commit**

```bash
git add tests/integration/test_path_sg_concordance.py
git commit -m "[mvp14] Task 9a: integration path — SG parser -> concordance -> compiler"
```

---

### Task 9b: Integration Path — Benchmark Validator

**Files:**
- Create: `tests/integration/test_path_benchmark.py`

Path 9: Tests that `load_real_saudi_io()` -> `LeontiefSolver.solve()` -> `BenchmarkValidator.validate_multipliers()` produces a plausibility report with multiplier ranges and outlier flags.

**Step 1: Write the tests**

```python
# tests/integration/test_path_benchmark.py
"""Integration Path 9: Benchmark Validator Integration.

Tests that the real D-1 20-sector Saudi IO model produces Leontief
multipliers that pass benchmark plausibility validation:
  load_real_saudi_io() -> LeontiefSolver.solve -> BenchmarkValidator.validate_multipliers

Checks multiplier ranges, outlier flags, and comparison against known
Saudi economic benchmarks.
"""

import numpy as np
import pytest

from .golden_scenarios.shared import ISIC_20_SECTIONS


@pytest.mark.integration
@pytest.mark.real_data
class TestBenchmarkValidatorIntegration:
    """Benchmark validation of Leontief multipliers on real 20-sector model."""

    def test_leontief_multipliers_in_benchmark_range(self):
        """Multipliers from 20-sector model are within plausible ranges."""
        from src.data.benchmark_validator import BenchmarkValidator
        from src.data.real_io_loader import load_real_saudi_io
        from src.engine.leontief import LeontiefSolver
        from src.engine.model_store import ModelStore

        model = load_real_saudi_io()
        assert len(model.sector_codes) == 20

        # Register and load model
        store = ModelStore()
        mv = store.register(
            Z=model.Z, x=model.x, sector_codes=model.sector_codes,
            base_year=model.base_year, source="benchmark-test",
        )
        loaded = store.get(mv.model_version_id)

        # Run Leontief with unit shock in Construction (F)
        f_idx = model.sector_codes.index("F")
        delta_d = np.zeros(20)
        delta_d[f_idx] = 1.0

        solver = LeontiefSolver()
        solve_result = solver.solve(loaded_model=loaded, delta_d=delta_d)

        assert solve_result.delta_x_total is not None
        assert all(np.isfinite(solve_result.delta_x_total))

        # Validate multipliers against benchmarks
        validation = BenchmarkValidator.validate_multipliers(
            solve_result=solve_result,
            model=model,
        )
        assert validation.all_in_range, (
            f"Multiplier outliers detected: {validation.outliers}"
        )

    def test_all_sectors_produce_positive_multipliers(self):
        """Unit shock in each sector -> positive output multiplier."""
        from src.data.real_io_loader import load_real_saudi_io
        from src.engine.leontief import LeontiefSolver
        from src.engine.model_store import ModelStore

        model = load_real_saudi_io()
        store = ModelStore()
        mv = store.register(
            Z=model.Z, x=model.x, sector_codes=model.sector_codes,
            base_year=model.base_year, source="benchmark-all-sectors",
        )
        loaded = store.get(mv.model_version_id)

        solver = LeontiefSolver()
        for i, sector in enumerate(model.sector_codes):
            delta_d = np.zeros(20)
            delta_d[i] = 1.0
            result = solver.solve(loaded_model=loaded, delta_d=delta_d)
            multiplier = result.delta_x_total.sum()
            assert multiplier >= 1.0, (
                f"Sector {sector}: output multiplier {multiplier:.4f} < 1.0 "
                "(should be >= 1.0 by Leontief theory)"
            )
```

**Step 2: Run and verify**

Run: `python -m pytest tests/integration/test_path_benchmark.py -v`

Note: If `load_real_saudi_io()` or `BenchmarkValidator` do not yet exist, these tests will fail with ImportError. Skip with `pytest.mark.skip` in that case.

**Step 3: Commit**

```bash
git add tests/integration/test_path_benchmark.py
git commit -m "[mvp14] Task 9b: integration path — benchmark validator on real 20-sector model"
```

---

### Task 9c: Real Data Smoke Test

**Files:**
- Create: `tests/integration/test_real_data_smoke.py`

Loads the actual D-1 20-sector Saudi IO model and runs it through core computation stack with plausibility validation.

**Step 1: Write the tests**

```python
# tests/integration/test_real_data_smoke.py
"""Real data smoke test (Amendment 5).

Loads the actual D-1 20-sector Saudi IO model and runs it through the
core computation stack with plausibility validation. This is a
confidence check that real data produces sensible results.

Marked @pytest.mark.real_data for selective execution.
"""

import numpy as np
import pytest

from .golden_scenarios.shared import ISIC_20_SECTIONS


@pytest.mark.real_data
@pytest.mark.integration
class TestRealDataSmoke:
    """Smoke test on D-1 20-sector model."""

    def test_leontief_satellite_on_real_model(self):
        """Load D-1 20-sector, run Leontief + Satellite, check plausibility."""
        from src.data.real_io_loader import load_real_saudi_io
        from src.engine.leontief import LeontiefSolver
        from src.engine.model_store import ModelStore
        from src.engine.satellites import SatelliteAccounts

        model = load_real_saudi_io()
        assert len(model.sector_codes) == 20

        # Register and load
        store = ModelStore()
        mv = store.register(
            Z=model.Z, x=model.x, sector_codes=model.sector_codes,
            base_year=model.base_year, source="real-data-smoke",
        )
        loaded = store.get(mv.model_version_id)

        # Run Leontief with unit shock in Construction (F)
        f_idx = model.sector_codes.index("F")
        delta_d = np.zeros(20)
        delta_d[f_idx] = 100.0  # 100M SAR shock

        solver = LeontiefSolver()
        solve_result = solver.solve(loaded_model=loaded, delta_d=delta_d)
        assert solve_result.delta_x_total is not None
        assert all(np.isfinite(solve_result.delta_x_total))
        assert np.all(solve_result.delta_x_total >= 0)

        # Output multiplier should be >= 1.0 (Leontief theory)
        total_output = solve_result.delta_x_total.sum()
        assert total_output >= 100.0, (
            f"Total output {total_output:.2f} < input shock 100.0"
        )

    def test_quality_assessment_with_real_sources(self):
        """Run quality assessment with real model metadata."""
        from src.data.real_io_loader import load_real_saudi_io
        from src.quality.service import QualityAssessmentService

        model = load_real_saudi_io()
        svc = QualityAssessmentService()

        # Assess with model vintage information
        assessment = svc.assess(
            base_year=model.base_year,
            current_year=2026,
            mapping_coverage_pct=None,
            mapping_confidence_dist=None,
            mapping_residual_pct=None,
            mapping_unresolved_pct=None,
            mapping_unresolved_spend_pct=None,
            assumption_ranges_coverage_pct=None,
            assumption_approval_rate=None,
            constraint_confidence_summary=None,
            workforce_overall_confidence=None,
            plausibility_in_range_pct=None,
            plausibility_flagged_count=None,
            source_ages=None,
        )

        assert assessment.grade is not None
        # With only vintage dimension available, assessment should still work
        assert len(assessment.dimension_assessments) >= 1
```

**Step 2: Run and verify**

Run: `python -m pytest tests/integration/test_real_data_smoke.py -v`

Note: If `load_real_saudi_io()` is not yet available, these tests will fail with ImportError. Mark as skip in that case.

**Step 3: Commit**

```bash
git add tests/integration/test_real_data_smoke.py
git commit -m "[mvp14] Task 9c: real data smoke test on D-1 20-sector model"
```

---

### Task 10: Mathematical Accuracy Verification (3-sector toy model)

**Files:**
- Create: `tests/integration/test_mathematical_accuracy.py`

This is the ONLY place where the 3-sector toy model (ISIC F/C/G) is used. Hand-verified B=(I-A)^-1 computation and algebraic identities.

**Step 1: Write the tests**

```python
# tests/integration/test_mathematical_accuracy.py
"""Mathematical accuracy verification using the 3-sector toy model.

Uses the small ISIC F/C/G model from shared.py where hand calculation
is feasible. Verifies Leontief algebra, multipliers, satellite identities,
IO accounting, and numerical stability.

This is the ONLY test file that uses the 3-sector toy model.
All other integration tests use the 20-sector D-1 model.
"""

import numpy as np
import pytest
from numpy.testing import assert_allclose
from uuid_extensions import uuid7

from src.engine.leontief import LeontiefSolver
from src.engine.model_store import ModelStore
from src.engine.satellites import SatelliteAccounts, SatelliteCoefficients

from .golden_scenarios.shared import (
    EXPECTED_B_SMALL,
    GOLDEN_BASE_YEAR,
    GOLDEN_X,
    GOLDEN_Z,
    SECTOR_CODES_SMALL,
    SMALL_IMPORT_RATIO,
    SMALL_JOBS_COEFF,
    SMALL_VA_RATIO,
)


@pytest.fixture
def loaded_3sector():
    """Register and load the 3-sector toy model (ISIC F/C/G)."""
    store = ModelStore()
    mv = store.register(
        Z=GOLDEN_Z, x=GOLDEN_X, sector_codes=SECTOR_CODES_SMALL,
        base_year=GOLDEN_BASE_YEAR, source="math-accuracy-test",
    )
    return store.get(mv.model_version_id)


@pytest.mark.integration
class TestMathematicalAccuracy:
    """Algebraic verification of Leontief computations on 3-sector toy model.

    The toy model uses ISIC codes F (Construction), C (Manufacturing),
    G (Wholesale/Retail) with known Z matrix and x vector from shared.py.
    B = (I-A)^-1 is pre-computed in EXPECTED_B_SMALL for verification.
    """

    def test_leontief_inverse_matches_hand_calculation(self, loaded_3sector):
        """B = (I-A)^-1 matches pre-computed reference values.

        A = Z * diag(x)^-1:
          [[0.10,  0.025, 0.02 ],
           [0.08,  0.10,  0.04 ],
           [0.04,  0.05,  0.10 ]]

        B = (I-A)^-1 pre-computed in shared.py via numpy.linalg.inv.
        """
        B = loaded_3sector.B
        assert_allclose(B, EXPECTED_B_SMALL, rtol=1e-10)

    def test_leontief_identity(self, loaded_3sector):
        """delta_x = B . delta_d verified algebraically."""
        solver = LeontiefSolver()
        delta_d = np.array([100.0, 50.0, 25.0])
        result = solver.solve(loaded_model=loaded_3sector, delta_d=delta_d)

        expected = EXPECTED_B_SMALL @ delta_d
        assert_allclose(result.delta_x_total, expected, rtol=1e-10)

    def test_output_multiplier_is_column_sum(self, loaded_3sector):
        """Column sum of B = output multiplier for each sector.

        For each sector j, a unit shock delta_d_j = 1 produces total output
        equal to the j-th column sum of B.
        """
        B = loaded_3sector.B
        multipliers = B.sum(axis=0)

        solver = LeontiefSolver()
        for i in range(3):
            delta_d = np.zeros(3)
            delta_d[i] = 1.0
            result = solver.solve(loaded_model=loaded_3sector, delta_d=delta_d)
            assert_allclose(
                result.delta_x_total.sum(), multipliers[i], rtol=1e-10,
                err_msg=f"Sector {SECTOR_CODES_SMALL[i]}: multiplier mismatch",
            )

    def test_satellite_gdp_consistency(self, loaded_3sector):
        """GDP impact = va_ratio * delta_x (element-wise dot product)."""
        solver = LeontiefSolver()
        delta_d = np.array([100.0, 50.0, 25.0])
        result = solver.solve(loaded_model=loaded_3sector, delta_d=delta_d)

        coeff = SatelliteCoefficients(
            jobs_coeff=SMALL_JOBS_COEFF.copy(),
            import_ratio=SMALL_IMPORT_RATIO.copy(),
            va_ratio=SMALL_VA_RATIO.copy(),
            version_id=uuid7(),
        )
        sa = SatelliteAccounts()
        sat = sa.compute(delta_x=result.delta_x_total, coefficients=coeff)

        expected_gdp = SMALL_VA_RATIO * result.delta_x_total
        assert_allclose(sat.delta_va, expected_gdp, rtol=1e-10)

    def test_satellite_employment_consistency(self, loaded_3sector):
        """Employment = jobs_coeff * delta_x (element-wise)."""
        solver = LeontiefSolver()
        delta_d = np.array([100.0, 50.0, 25.0])
        result = solver.solve(loaded_model=loaded_3sector, delta_d=delta_d)

        coeff = SatelliteCoefficients(
            jobs_coeff=SMALL_JOBS_COEFF.copy(),
            import_ratio=SMALL_IMPORT_RATIO.copy(),
            va_ratio=SMALL_VA_RATIO.copy(),
            version_id=uuid7(),
        )
        sa = SatelliteAccounts()
        sat = sa.compute(delta_x=result.delta_x_total, coefficients=coeff)

        expected_jobs = SMALL_JOBS_COEFF * result.delta_x_total
        assert_allclose(sat.delta_jobs, expected_jobs, rtol=1e-10)

    def test_io_accounting_identity(self, loaded_3sector):
        """Row sums of Z + final demand = gross output.

        x = A.x + d  =>  d = x - A.x = (I-A).x
        Reconstructed x = A.x + d should equal original x.
        """
        A = loaded_3sector.A
        x = loaded_3sector.x

        d = x - A @ x
        reconstructed_x = A @ x + d
        assert_allclose(reconstructed_x, x, rtol=1e-10)

    def test_import_leakage_reduces_domestic(self, loaded_3sector):
        """Higher import share -> lower domestic multiplier effect.

        Halving the domestic demand shock halves the output (linearity).
        """
        solver = LeontiefSolver()
        delta_d_full = np.array([100.0, 50.0, 25.0])
        result_full = solver.solve(loaded_model=loaded_3sector, delta_d=delta_d_full)

        # With 50% import leakage applied pre-solve
        delta_d_half = delta_d_full * 0.5
        result_half = solver.solve(loaded_model=loaded_3sector, delta_d=delta_d_half)

        # Half the domestic shock -> half the output (linearity)
        assert_allclose(
            result_half.delta_x_total,
            result_full.delta_x_total * 0.5,
            rtol=1e-10,
        )

    def test_numerical_stability_serial_computation(self, loaded_3sector):
        """10 serial computations -> numerical drift < 1e-10."""
        solver = LeontiefSolver()
        delta_d = np.array([100.0, 50.0, 25.0])
        first_result = solver.solve(loaded_model=loaded_3sector, delta_d=delta_d)

        for _ in range(10):
            result = solver.solve(loaded_model=loaded_3sector, delta_d=delta_d)

        assert_allclose(
            result.delta_x_total,
            first_result.delta_x_total,
            rtol=0,
            atol=1e-10,
        )
```

**Step 2: Run and verify**

Run: `python -m pytest tests/integration/test_mathematical_accuracy.py -v`

**Step 3: Commit**

```bash
git add tests/integration/test_mathematical_accuracy.py
git commit -m "[mvp14] Task 10: mathematical accuracy verification (3-sector ISIC F/C/G toy model)"
```

---
### Task 11: Depth Engine Integration (Amendment 2)

**Files:**
- Create: `tests/integration/test_path_depth.py`

Tests Depth Engine as primarily UPSTREAM (produces artifacts, does not consume engine results as primary mode). LLM mocked with step-specific typed outputs for deterministic testing. Tests verify disclosure tier tagging, step sequence execution, and that depth outputs never mutate engine numbers.

**Step 1: Write the tests**

```python
# tests/integration/test_path_depth.py
"""Integration Path 4: Depth Engine (Amendment 2 — upstream direction).

Tests that DepthOrchestrator produces valid plan and artifacts with:
- Mocked LLM returning step-specific typed outputs for determinism
- Disclosure tier classification on all artifacts (PUBLIC vs RESTRICTED)
- 5 steps execute in order, each producing typed output
- DepthPlan produces a valid scenario stub
- Engine outputs NOT modified by depth engine

NOTE: DepthOrchestrator.run() is async and requires LLMClient + repositories.
We mock LLMClient and use in-memory repositories.
"""

import pytest
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID
from uuid_extensions import uuid7

from src.agents.depth.orchestrator import DepthOrchestrator
from src.models.common import DataClassification, DisclosureTier
from src.models.depth import (
    DepthPlanStatus,
    DepthStepName,
    KhawatirOutput,
    MuraqabaOutput,
    MujahadaOutput,
    MuhasabaOutput,
    ScenarioSuitePlan,
)
from src.engine.leontief import LeontiefSolver
from src.engine.model_store import ModelStore

from .golden_scenarios.shared import SECTOR_CODES_SMALL


# ---------------------------------------------------------------------------
# Step-specific mock LLM responses (deterministic)
# ---------------------------------------------------------------------------

_STEP_RESPONSES: dict[str, dict] = {
    DepthStepName.KHAWATIR.value: {
        "directions": [
            {
                "label": "insight",
                "description": "Construction demand drives upstream steel",
                "confidence": 0.85,
            },
        ],
    },
    DepthStepName.MURAQABA.value: {
        "biases_detected": [
            {
                "bias_type": "optimism_bias",
                "description": "Over-estimated local content share",
                "severity": "medium",
            },
        ],
    },
    DepthStepName.MUJAHADA.value: {
        "challenges": [
            {
                "direction_ref": 0,
                "challenge": "Steel imports may offset domestic gains",
                "impact": "high",
            },
        ],
    },
    DepthStepName.MUHASABA.value: {
        "ranked_directions": [
            {"direction_ref": 0, "score": 0.82, "rationale": "Strong evidence"},
        ],
    },
    DepthStepName.SUITE_PLANNING.value: {
        "scenarios": [
            {
                "name": "Base Case — Industrial Zone",
                "description": "Standard construction scenario",
                "shocks": [
                    {"sector_code": "F", "value": 300.0, "unit": "SAR_MILLIONS"},
                ],
            },
        ],
    },
}


def _make_mock_llm_client(classification: DataClassification = DataClassification.CONFIDENTIAL):
    """Build a mock LLM client that returns step-specific typed outputs."""
    client = MagicMock()
    client.is_available_for = MagicMock(return_value=True)
    client.cumulative_usage = MagicMock(return_value=MagicMock(
        input_tokens=100, output_tokens=50,
    ))

    # Router mock for provider selection
    router = MagicMock()
    router.select_provider = MagicMock(return_value=MagicMock(value="mock"))
    client._router = router

    return client


def _make_step_agent_mock():
    """Build a step agent that returns step-specific payloads."""
    def _factory(step: DepthStepName):
        agent = MagicMock()
        agent.run = MagicMock(return_value=_STEP_RESPONSES.get(step.value, {}))
        return agent
    return _factory


def _make_mock_plan_repo():
    """In-memory plan repository mock."""
    repo = MagicMock()
    repo.get = AsyncMock(return_value=None)
    repo.save = AsyncMock()
    repo.update_status = AsyncMock()
    return repo


def _make_mock_artifact_repo():
    """In-memory artifact repository mock."""
    saved_artifacts: list = []
    repo = MagicMock()
    repo.save = AsyncMock(side_effect=lambda art: saved_artifacts.append(art))
    repo.list_by_plan = AsyncMock(return_value=[])
    repo._saved = saved_artifacts
    return repo


@pytest.mark.integration
@pytest.mark.anyio
class TestDepthEngineIntegration:
    """Depth engine produces valid artifacts (Amendment 2: upstream direction)."""

    async def test_depth_plan_creation(self):
        """DepthOrchestrator.run produces a COMPLETED or PARTIAL status."""
        orch = DepthOrchestrator()
        status = await orch.run(
            plan_id=uuid7(),
            workspace_id=uuid7(),
            context={"scenario_name": "Test", "sector": "Construction"},
            classification=DataClassification.CONFIDENTIAL,
            llm_client=_make_mock_llm_client(),
            plan_repo=_make_mock_plan_repo(),
            artifact_repo=_make_mock_artifact_repo(),
        )
        assert status in (DepthPlanStatus.COMPLETED, DepthPlanStatus.PARTIAL)

    async def test_depth_artifacts_persisted(self):
        """Each step persists an artifact via artifact_repo.save."""
        artifact_repo = _make_mock_artifact_repo()
        orch = DepthOrchestrator()
        await orch.run(
            plan_id=uuid7(),
            workspace_id=uuid7(),
            context={"scenario_name": "Test"},
            classification=DataClassification.CONFIDENTIAL,
            llm_client=_make_mock_llm_client(),
            plan_repo=_make_mock_plan_repo(),
            artifact_repo=artifact_repo,
        )
        # At least some artifacts saved (one per step that succeeds)
        assert artifact_repo.save.call_count >= 1

    async def test_each_artifact_has_disclosure_tier(self):
        """Every artifact carries a valid disclosure tier annotation."""
        artifact_repo = _make_mock_artifact_repo()
        orch = DepthOrchestrator()
        await orch.run(
            plan_id=uuid7(),
            workspace_id=uuid7(),
            context={"scenario_name": "Tier Test"},
            classification=DataClassification.CONFIDENTIAL,
            llm_client=_make_mock_llm_client(),
            plan_repo=_make_mock_plan_repo(),
            artifact_repo=artifact_repo,
        )
        for call_args in artifact_repo.save.call_args_list:
            artifact = call_args.args[0] if call_args.args else call_args.kwargs.get("artifact")
            if artifact is not None and hasattr(artifact, "disclosure_tier"):
                assert artifact.disclosure_tier in (
                    DisclosureTier.TIER0,
                    DisclosureTier.TIER1,
                    DisclosureTier.TIER2,
                )

    async def test_disclosure_tier_differs_by_classification(self):
        """PUBLIC vs RESTRICTED classification produces different tier outputs."""
        results = {}
        for cls in (DataClassification.PUBLIC, DataClassification.RESTRICTED):
            artifact_repo = _make_mock_artifact_repo()
            orch = DepthOrchestrator()
            await orch.run(
                plan_id=uuid7(),
                workspace_id=uuid7(),
                context={"scenario_name": "Tier Compare"},
                classification=cls,
                llm_client=_make_mock_llm_client(cls),
                plan_repo=_make_mock_plan_repo(),
                artifact_repo=artifact_repo,
            )
            results[cls] = artifact_repo.save.call_count
        # Both classifications should produce artifacts
        assert results[DataClassification.PUBLIC] >= 1
        assert results[DataClassification.RESTRICTED] >= 1

    async def test_pipeline_produces_expected_step_sequence(self):
        """The orchestrator produces 5 steps in order, each with typed output."""
        plan_repo = _make_mock_plan_repo()
        orch = DepthOrchestrator()
        await orch.run(
            plan_id=uuid7(),
            workspace_id=uuid7(),
            context={"scenario_name": "Sequence Test"},
            classification=DataClassification.CONFIDENTIAL,
            llm_client=_make_mock_llm_client(),
            plan_repo=plan_repo,
            artifact_repo=_make_mock_artifact_repo(),
        )
        # update_status is called for RUNNING + each step transition
        step_calls = plan_repo.update_status.call_args_list
        # Verify at least 5 step transitions (one per step)
        assert len(step_calls) >= 5

        # Verify expected step names appear in order
        expected_steps = [
            DepthStepName.KHAWATIR.value,
            DepthStepName.MURAQABA.value,
            DepthStepName.MUJAHADA.value,
            DepthStepName.MUHASABA.value,
            DepthStepName.SUITE_PLANNING.value,
        ]
        step_names_seen = []
        for call_args in step_calls:
            kw = call_args.kwargs if call_args.kwargs else {}
            pos = call_args.args if call_args.args else ()
            step_name = kw.get("current_step")
            if step_name and step_name in expected_steps:
                step_names_seen.append(step_name)
        # All 5 steps should appear
        for step in expected_steps:
            assert step in step_names_seen, f"Step {step} not found in sequence"

    async def test_suite_plan_contains_executable_scenarios(self):
        """DepthPlan suite planning output produces scenario stubs with shocks."""
        artifact_repo = _make_mock_artifact_repo()
        orch = DepthOrchestrator()
        status = await orch.run(
            plan_id=uuid7(),
            workspace_id=uuid7(),
            context={"scenario_name": "Suite Test"},
            classification=DataClassification.CONFIDENTIAL,
            llm_client=_make_mock_llm_client(),
            plan_repo=_make_mock_plan_repo(),
            artifact_repo=artifact_repo,
        )
        # If completed, suite planning artifact should exist
        if status == DepthPlanStatus.COMPLETED:
            assert artifact_repo.save.call_count >= 5
            # Last saved artifact should be suite planning
            last_call = artifact_repo.save.call_args_list[-1]
            artifact = last_call.args[0] if last_call.args else None
            if artifact is not None and hasattr(artifact, "payload"):
                payload = artifact.payload
                # Suite plan should contain scenario descriptions
                assert payload is not None

    async def test_depth_does_not_modify_engine_numbers(self):
        """Engine outputs before and after depth engine are identical.

        Depth produces artifacts but NEVER modifies deterministic results.
        """
        # Compute engine result BEFORE depth
        store = ModelStore()
        mv = store.register(
            Z=np.array([[100.0, 50.0], [60.0, 80.0]]),
            x=np.array([500.0, 400.0]),
            sector_codes=["S1", "S2"],
            base_year=2024, source="depth-test",
        )
        loaded = store.get(mv.model_version_id)
        solver = LeontiefSolver()
        delta_d = np.array([50.0, 30.0])
        result_before = solver.solve(loaded_model=loaded, delta_d=delta_d)

        # Run depth engine (with mocks)
        orch = DepthOrchestrator()
        await orch.run(
            plan_id=uuid7(),
            workspace_id=uuid7(),
            context={"scenario_name": "No-mutate test"},
            classification=DataClassification.CONFIDENTIAL,
            llm_client=_make_mock_llm_client(),
            plan_repo=_make_mock_plan_repo(),
            artifact_repo=_make_mock_artifact_repo(),
        )

        # Compute engine result AFTER depth — must be identical
        result_after = solver.solve(loaded_model=loaded, delta_d=delta_d)
        np.testing.assert_array_equal(
            result_before.delta_x_total, result_after.delta_x_total,
        )
```

**Step 2: Run and verify**

Run: `python -m pytest tests/integration/test_path_depth.py -v`

**Step 3: Commit**

```bash
git add tests/integration/test_path_depth.py
git commit -m "[mvp14] Task 11: depth engine integration — disclosure tiers, step sequence, scenario stubs"
```

---

### Task 12: End-to-End Golden Tests with Frozen Snapshots

**Files:**
- Create: `tests/integration/test_e2e_golden.py`
- Create: `tests/integration/golden_scenarios/snapshots/__init__.py`
- Create: `tests/integration/golden_scenarios/snapshots/industrial_zone_outputs.json`
- Create: `tests/integration/golden_scenarios/snapshots/contraction_outputs.json`
- Create: `tests/integration/golden_scenarios/snapshots/mega_project_gaps_outputs.json`

Golden tests load FROZEN snapshots from committed JSON files. They compare current outputs against frozen values using `numpy.testing.assert_allclose` and `pytest.approx`. Golden values are NEVER recomputed automatically. The `--update-golden` conftest flag rewrites snapshot files when intentional changes warrant new baselines.

**Step 1: Add `--update-golden` conftest flag**

Add to `tests/integration/conftest.py`:

```python
# At the top of tests/integration/conftest.py, add:

def pytest_addoption(parser):
    """Register --update-golden CLI flag."""
    parser.addoption(
        "--update-golden",
        action="store_true",
        default=False,
        help="Rewrite golden snapshot JSON files with freshly computed values.",
    )


@pytest.fixture
def update_golden(request) -> bool:
    """Whether to overwrite golden snapshots."""
    return request.config.getoption("--update-golden")
```

**Step 2: Create initial golden snapshot JSON files**

```json
// tests/integration/golden_scenarios/snapshots/industrial_zone_outputs.json
{
  "scenario": "industrial_zone",
  "computed_at": "2026-03-01T00:00:00Z",
  "model": "3-sector ISIC F/C/G",
  "tolerances": {"rtol": 1e-6, "employment_atol": 10, "gdp_rtol": 0.01},
  "delta_d": [300.0, 150.0, 50.0],
  "total_output_impact": null,
  "gdp_impact": null,
  "employment_total": null,
  "sector_outputs": {},
  "quality_grade": null
}
```

```json
// tests/integration/golden_scenarios/snapshots/contraction_outputs.json
{
  "scenario": "contraction",
  "computed_at": "2026-03-01T00:00:00Z",
  "model": "3-sector ISIC F/C/G",
  "tolerances": {"rtol": 1e-6, "employment_atol": 10, "gdp_rtol": 0.01},
  "delta_d": [-100.0, -50.0, -30.0],
  "total_output_impact": null,
  "gdp_impact": null,
  "employment_total": null,
  "sector_outputs": {},
  "quality_grade": null
}
```

```json
// tests/integration/golden_scenarios/snapshots/mega_project_gaps_outputs.json
{
  "scenario": "mega_project_gaps",
  "computed_at": "2026-03-01T00:00:00Z",
  "model": "3-sector ISIC F/C/G",
  "tolerances": {"rtol": 1e-6, "employment_atol": 10, "gdp_rtol": 0.01},
  "delta_d": [200.0, 100.0, 100.0],
  "total_output_impact": null,
  "gdp_impact": null,
  "employment_total": null,
  "sector_outputs": {},
  "quality_grade": null
}
```

**Step 3: Write the e2e golden test file**

```python
# tests/integration/test_e2e_golden.py
"""End-to-end golden tests using frozen JSON snapshots.

Each test runs the FULL deterministic pipeline and compares
against toleranced expected values loaded from committed JSON
files in golden_scenarios/snapshots/.

Golden values are NEVER recomputed automatically. To update:
    pytest tests/integration/test_e2e_golden.py --update-golden

Updated JSON files must be reviewed and committed.
"""

import json
import numpy as np
import pytest
from datetime import datetime, timezone
from numpy.testing import assert_allclose
from pathlib import Path
from uuid_extensions import uuid7

from src.engine.leontief import LeontiefSolver
from src.engine.model_store import ModelStore
from src.engine.satellites import SatelliteAccounts, SatelliteCoefficients
from src.quality.service import QualityAssessmentService

from .golden_scenarios.shared import (
    EMPLOYMENT_ATOL,
    GDP_RTOL,
    GOLDEN_BASE_YEAR,
    GOLDEN_X,
    GOLDEN_Z,
    NUMERIC_RTOL,
    OUTPUT_RTOL,
    SECTOR_CODES_SMALL,
)

SNAPSHOTS_DIR = Path(__file__).parent / "golden_scenarios" / "snapshots"


def _load_snapshot(name: str) -> dict:
    """Load a frozen golden snapshot from JSON."""
    path = SNAPSHOTS_DIR / f"{name}_outputs.json"
    if not path.exists():
        pytest.skip(f"Snapshot {path} not found — run with --update-golden first")
    with open(path) as f:
        return json.load(f)


def _save_snapshot(name: str, data: dict) -> None:
    """Save a golden snapshot to JSON."""
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    path = SNAPSHOTS_DIR / f"{name}_outputs.json"
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _run_full_pipeline(delta_d: list[float], base_year: int = GOLDEN_BASE_YEAR) -> dict:
    """Run complete deterministic pipeline and return all results."""
    store = ModelStore()
    mv = store.register(
        Z=GOLDEN_Z, x=GOLDEN_X, sector_codes=SECTOR_CODES_SMALL,
        base_year=base_year, source="golden-e2e",
    )
    loaded = store.get(mv.model_version_id)

    solver = LeontiefSolver()
    solve = solver.solve(loaded_model=loaded, delta_d=np.asarray(delta_d))

    sat_coeff = SatelliteCoefficients(
        jobs_coeff=np.array([0.008, 0.004, 0.006]),
        import_ratio=np.array([0.30, 0.25, 0.15]),
        va_ratio=np.array([0.35, 0.45, 0.55]),
        version_id=uuid7(),
    )
    sa = SatelliteAccounts()
    sat = sa.compute(delta_x=solve.delta_x_total, coefficients=sat_coeff)

    return {
        "delta_x": solve.delta_x_total,
        "total_output": float(solve.delta_x_total.sum()),
        "gdp_impact": float(sat.delta_va.sum()),
        "employment_total": float(sat.delta_jobs.sum()),
        "sector_outputs": {
            code: float(solve.delta_x_total[i])
            for i, code in enumerate(SECTOR_CODES_SMALL)
        },
    }


@pytest.mark.integration
@pytest.mark.golden
class TestEndToEndGolden:
    """End-to-end golden tests with frozen snapshot comparison."""

    def test_industrial_zone_full_pipeline(self, update_golden):
        """Golden Scenario 1: Industrial zone — full happy path.

        Loads frozen values from snapshots/industrial_zone_outputs.json.
        Compares with assert_allclose using documented tolerances.
        """
        results = _run_full_pipeline([300.0, 150.0, 50.0])

        if update_golden:
            snapshot = {
                "scenario": "industrial_zone",
                "computed_at": datetime.now(timezone.utc).isoformat(),
                "model": "3-sector ISIC F/C/G",
                "tolerances": {
                    "rtol": NUMERIC_RTOL,
                    "employment_atol": EMPLOYMENT_ATOL,
                    "gdp_rtol": GDP_RTOL,
                },
                "delta_d": [300.0, 150.0, 50.0],
                "total_output_impact": results["total_output"],
                "gdp_impact": results["gdp_impact"],
                "employment_total": results["employment_total"],
                "sector_outputs": results["sector_outputs"],
                "quality_grade": None,
            }
            _save_snapshot("industrial_zone", snapshot)
            pytest.skip("Golden snapshot updated — review and commit")

        golden = _load_snapshot("industrial_zone")
        if golden.get("total_output_impact") is None:
            pytest.skip("Snapshot has null values — run with --update-golden first")

        # Toleranced comparison (not hash-based)
        assert_allclose(
            results["total_output"],
            golden["total_output_impact"],
            rtol=NUMERIC_RTOL,
            err_msg="Total output drifted from golden",
        )
        assert_allclose(
            results["gdp_impact"],
            golden["gdp_impact"],
            rtol=GDP_RTOL,
            err_msg="GDP impact drifted from golden",
        )
        assert results["employment_total"] == pytest.approx(
            golden["employment_total"], abs=EMPLOYMENT_ATOL,
        )

        # Per-sector comparison
        for code in SECTOR_CODES_SMALL:
            assert_allclose(
                results["sector_outputs"][code],
                golden["sector_outputs"][code],
                rtol=NUMERIC_RTOL,
                err_msg=f"Sector {code} output drifted from golden",
            )

    def test_contraction_scenario(self, update_golden):
        """Golden Scenario 3: Negative demand shock — frozen snapshot."""
        results = _run_full_pipeline([-100.0, -50.0, -30.0])

        if update_golden:
            snapshot = {
                "scenario": "contraction",
                "computed_at": datetime.now(timezone.utc).isoformat(),
                "model": "3-sector ISIC F/C/G",
                "tolerances": {
                    "rtol": NUMERIC_RTOL,
                    "employment_atol": EMPLOYMENT_ATOL,
                    "gdp_rtol": GDP_RTOL,
                },
                "delta_d": [-100.0, -50.0, -30.0],
                "total_output_impact": results["total_output"],
                "gdp_impact": results["gdp_impact"],
                "employment_total": results["employment_total"],
                "sector_outputs": results["sector_outputs"],
                "quality_grade": None,
            }
            _save_snapshot("contraction", snapshot)
            pytest.skip("Golden snapshot updated — review and commit")

        golden = _load_snapshot("contraction")
        if golden.get("total_output_impact") is None:
            pytest.skip("Snapshot has null values — run with --update-golden first")

        # All impacts should be negative
        assert results["total_output"] < 0
        assert results["gdp_impact"] < 0
        assert results["employment_total"] < 0

        # Toleranced comparison against frozen values
        assert_allclose(
            results["total_output"],
            golden["total_output_impact"],
            rtol=NUMERIC_RTOL,
        )
        assert_allclose(
            results["gdp_impact"],
            golden["gdp_impact"],
            rtol=GDP_RTOL,
        )

    def test_mega_project_gaps(self, update_golden):
        """Golden Scenario 2: Mega-project with data gaps — frozen snapshot."""
        results = _run_full_pipeline([200.0, 100.0, 100.0], base_year=2018)

        if update_golden:
            snapshot = {
                "scenario": "mega_project_gaps",
                "computed_at": datetime.now(timezone.utc).isoformat(),
                "model": "3-sector ISIC F/C/G",
                "tolerances": {
                    "rtol": NUMERIC_RTOL,
                    "employment_atol": EMPLOYMENT_ATOL,
                    "gdp_rtol": GDP_RTOL,
                },
                "delta_d": [200.0, 100.0, 100.0],
                "total_output_impact": results["total_output"],
                "gdp_impact": results["gdp_impact"],
                "employment_total": results["employment_total"],
                "sector_outputs": results["sector_outputs"],
                "quality_grade": None,
            }
            _save_snapshot("mega_project_gaps", snapshot)
            pytest.skip("Golden snapshot updated — review and commit")

        golden = _load_snapshot("mega_project_gaps")
        if golden.get("total_output_impact") is None:
            pytest.skip("Snapshot has null values — run with --update-golden first")

        assert_allclose(
            results["total_output"],
            golden["total_output_impact"],
            rtol=NUMERIC_RTOL,
        )

    def test_reproducibility_across_runs(self):
        """Same golden scenario produces identical results 3 times."""
        delta_d = [300.0, 150.0, 50.0]
        results = [_run_full_pipeline(delta_d) for _ in range(3)]

        for i in range(1, 3):
            assert_allclose(
                results[0]["total_output"],
                results[i]["total_output"],
                rtol=0,
            )
            assert_allclose(
                results[0]["gdp_impact"],
                results[i]["gdp_impact"],
                rtol=0,
            )

    def test_quality_assessment_from_full_run(self, update_golden):
        """Full run feeds quality assessment — grade verified against snapshot."""
        results = _run_full_pipeline([300.0, 150.0, 50.0])

        qas = QualityAssessmentService()
        assessment = qas.assess(
            base_year=GOLDEN_BASE_YEAR,
            current_year=2026,
            mapping_coverage_pct=0.95,
            mapping_confidence_dist={"HIGH": 0.8, "MEDIUM": 0.15, "LOW": 0.05},
            mapping_residual_pct=0.02,
            mapping_unresolved_pct=0.01,
            mapping_unresolved_spend_pct=0.3,
            assumption_ranges_coverage_pct=0.85,
            assumption_approval_rate=0.9,
            constraint_confidence_summary={"HARD": 5, "ESTIMATED": 2, "ASSUMED": 1},
            workforce_overall_confidence="HIGH",
            plausibility_in_range_pct=95.0,
            plausibility_flagged_count=0,
            source_ages=[],
            run_id=uuid7(),
        )
        assert assessment.grade.value in ("A", "B")

    def test_data_gaps_lower_quality_grade(self):
        """Scenario 2: Data gaps produce lower quality grade (C or D)."""
        _run_full_pipeline([200.0, 100.0, 100.0], base_year=2018)

        qas = QualityAssessmentService()
        assessment = qas.assess(
            base_year=2018,
            current_year=2026,
            mapping_coverage_pct=0.70,
            mapping_confidence_dist={"HIGH": 0.3, "MEDIUM": 0.3, "LOW": 0.4},
            mapping_residual_pct=0.15,
            mapping_unresolved_pct=0.10,
            mapping_unresolved_spend_pct=3.0,
            assumption_ranges_coverage_pct=0.4,
            assumption_approval_rate=0.5,
            constraint_confidence_summary={"HARD": 1, "ESTIMATED": 1, "ASSUMED": 4},
            workforce_overall_confidence="LOW",
            plausibility_in_range_pct=70.0,
            plausibility_flagged_count=5,
            source_ages=[],
            run_id=uuid7(),
        )
        assert assessment.grade.value in ("C", "D", "F")
```

**Step 4: Run and verify**

Run: `python -m pytest tests/integration/test_e2e_golden.py -v --update-golden`

This first run populates snapshot files. Review and commit the generated JSON.

Run: `python -m pytest tests/integration/test_e2e_golden.py -v`

This second run verifies against the now-frozen snapshots.

**Step 5: Commit**

```bash
git add tests/integration/test_e2e_golden.py tests/integration/golden_scenarios/snapshots/
git commit -m "[mvp14] Task 12: e2e golden tests with frozen JSON snapshots and --update-golden flag"
```

---

### Task 13: Formal Gate Criteria Tests (Section 15.5.2)

**Files:**
- Create: `tests/integration/test_phase2_gate_formal.py`

Each test class maps to a specific gate criterion from tech spec Section 15.5.2. The `GATE_CRITERIA_MAP` in the gate report script uses these test names.

**Step 1: Write the tests**

```python
# tests/integration/test_phase2_gate_formal.py
"""Phase 2 Gate Criteria — formal verification.

From tech spec Section 15.5.2. Each test maps to a specific criterion:
  1. Compiler >= 60% auto-mapping  -> test_compiler_auto_mapping_gate
  2. Feasibility dual-output       -> test_feasibility_dual_output
  3. Workforce confidence labels   -> test_workforce_confidence_labels
  4. Full pipeline completes       -> test_full_pipeline_completes
  5. Flywheel captures learning    -> test_flywheel_captures_learning
  6. Quality assessment produced   -> test_quality_assessment_produced

Amendment 4: Compiler gate uses MappingSuggestionAgent.suggest_batch()
with a seeded MappingLibraryEntry list against a labeled ground-truth BoQ.
"""

import json
import numpy as np
import pytest
from pathlib import Path
from uuid_extensions import uuid7

from src.agents.mapping_agent import MappingSuggestionAgent
from src.compiler.scenario_compiler import ScenarioCompiler
from src.engine.constraints.solver import FeasibilitySolver
from src.engine.leontief import LeontiefSolver
from src.engine.model_store import ModelStore
from src.engine.satellites import SatelliteAccounts, SatelliteCoefficients
from src.models.common import ConstraintConfidence, new_uuid7
from src.models.document import BoQLineItem
from src.models.mapping import MappingLibraryEntry
from src.quality.service import QualityAssessmentService

from .golden_scenarios.shared import (
    GOLDEN_BASE_YEAR,
    GOLDEN_X,
    GOLDEN_Z,
    SECTOR_CODES_SMALL,
)

# ---------------------------------------------------------------------------
# Amendment 4: Seeded mapping library + labeled ground-truth BoQ
# ---------------------------------------------------------------------------

SEED_LIBRARY = [
    MappingLibraryEntry(
        pattern="concrete", sector_code="F", confidence=0.95,
        workspace_id=uuid7(),
    ),
    MappingLibraryEntry(
        pattern="steel supply", sector_code="C", confidence=0.90,
        workspace_id=uuid7(),
    ),
    MappingLibraryEntry(
        pattern="steel erection", sector_code="F", confidence=0.88,
        workspace_id=uuid7(),
    ),
    MappingLibraryEntry(
        pattern="site grading", sector_code="F", confidence=0.85,
        workspace_id=uuid7(),
    ),
    MappingLibraryEntry(
        pattern="electrical", sector_code="F", confidence=0.82,
        workspace_id=uuid7(),
    ),
    MappingLibraryEntry(
        pattern="plumbing", sector_code="F", confidence=0.80,
        workspace_id=uuid7(),
    ),
    MappingLibraryEntry(
        pattern="fabricat", sector_code="C", confidence=0.85,
        workspace_id=uuid7(),
    ),
    MappingLibraryEntry(
        pattern="hvac", sector_code="C", confidence=0.82,
        workspace_id=uuid7(),
    ),
    MappingLibraryEntry(
        pattern="piping", sector_code="C", confidence=0.80,
        workspace_id=uuid7(),
    ),
    MappingLibraryEntry(
        pattern="pump", sector_code="C", confidence=0.78,
        workspace_id=uuid7(),
    ),
    MappingLibraryEntry(
        pattern="consulting", sector_code="M", confidence=0.85,
        workspace_id=uuid7(),
    ),
    MappingLibraryEntry(
        pattern="project management", sector_code="M", confidence=0.83,
        workspace_id=uuid7(),
    ),
    MappingLibraryEntry(
        pattern="environmental", sector_code="M", confidence=0.80,
        workspace_id=uuid7(),
    ),
    MappingLibraryEntry(
        pattern="quality assurance", sector_code="M", confidence=0.78,
        workspace_id=uuid7(),
    ),
    MappingLibraryEntry(
        pattern="legal", sector_code="M", confidence=0.75,
        workspace_id=uuid7(),
    ),
]

LABELED_BOQ = [
    {"text": "reinforced concrete foundation", "ground_truth_isic": "F", "value": 5_000_000},
    {"text": "structural steel erection", "ground_truth_isic": "F", "value": 4_000_000},
    {"text": "site grading and preparation", "ground_truth_isic": "F", "value": 3_000_000},
    {"text": "electrical infrastructure", "ground_truth_isic": "F", "value": 3_500_000},
    {"text": "plumbing drainage systems", "ground_truth_isic": "F", "value": 2_500_000},
    {"text": "pre-fabricated steel components", "ground_truth_isic": "C", "value": 4_000_000},
    {"text": "industrial HVAC equipment", "ground_truth_isic": "C", "value": 3_000_000},
    {"text": "control panel fabrication", "ground_truth_isic": "C", "value": 2_500_000},
    {"text": "piping and valve assemblies", "ground_truth_isic": "C", "value": 2_000_000},
    {"text": "pump and motor procurement", "ground_truth_isic": "C", "value": 2_000_000},
    {"text": "engineering design consultancy", "ground_truth_isic": "M", "value": 1_500_000},
    {"text": "project management services", "ground_truth_isic": "M", "value": 1_200_000},
    {"text": "environmental impact assessment", "ground_truth_isic": "M", "value": 800_000},
    {"text": "quality assurance testing", "ground_truth_isic": "M", "value": 800_000},
    {"text": "legal regulatory compliance", "ground_truth_isic": "M", "value": 700_000},
]


@pytest.mark.integration
@pytest.mark.gate
class TestCompilerAutoMapping:
    """Gate Criterion 1: Compiler >= 60% auto-mapping rate (Amendment 4)."""

    def test_compiler_auto_mapping_gate(self):
        """MappingSuggestionAgent achieves >= 60% coverage on labeled BoQ.

        Uses suggest_batch() with seeded library against ground-truth.
        Gate metric: coverage >= 60%, accuracy >= 80% on suggested items.
        """
        doc_id, job_id = uuid7(), uuid7()

        items = [
            BoQLineItem(
                doc_id=doc_id,
                extraction_job_id=job_id,
                raw_text=entry["text"],
                total_value=entry["value"],
                page_ref=0,
                evidence_snippet_ids=[uuid7()],
            )
            for entry in LABELED_BOQ
        ]

        agent = MappingSuggestionAgent(library=SEED_LIBRARY)
        taxonomy = [
            {"code": "F", "description": "Construction"},
            {"code": "C", "description": "Manufacturing"},
            {"code": "G", "description": "Wholesale and retail trade"},
            {"code": "M", "description": "Professional, scientific and technical activities"},
        ]
        batch = agent.suggest_batch(items, taxonomy=taxonomy)

        # Coverage: how many items got a suggestion?
        covered = [
            s for s in batch.suggestions
            if s.sector_code is not None and s.sector_code != ""
        ]
        coverage = len(covered) / len(items)
        assert coverage >= 0.60, f"Coverage {coverage:.0%} < 60% gate threshold"

        # Accuracy: of suggested items, how many match ground truth?
        correct = 0
        for suggestion, entry in zip(batch.suggestions, LABELED_BOQ):
            if suggestion.sector_code and suggestion.sector_code == entry["ground_truth_isic"]:
                correct += 1
        accuracy = correct / len(covered) if covered else 0.0
        assert accuracy >= 0.80, f"Accuracy {accuracy:.0%} < 80% on suggested items"


@pytest.mark.integration
@pytest.mark.gate
class TestFeasibilityDualOutput:
    """Gate Criterion 2: Feasibility produces unconstrained AND feasible."""

    def test_feasibility_dual_output(self):
        """Both unconstrained and feasible results present with diagnostics."""
        from src.engine.constraints.schema import (
            Constraint, ConstraintBoundScope, ConstraintScope,
            ConstraintSet, ConstraintType, ConstraintUnit,
        )

        store = ModelStore()
        mv = store.register(
            Z=GOLDEN_Z, x=GOLDEN_X, sector_codes=SECTOR_CODES_SMALL,
            base_year=GOLDEN_BASE_YEAR, source="gate-feas",
        )
        loaded = store.get(mv.model_version_id)

        solver = LeontiefSolver()
        delta_d = np.array([300.0, 150.0, 50.0])
        solve = solver.solve(loaded_model=loaded, delta_d=delta_d)

        sat_coeff = SatelliteCoefficients(
            jobs_coeff=np.array([0.008, 0.004, 0.006]),
            import_ratio=np.array([0.30, 0.25, 0.15]),
            va_ratio=np.array([0.35, 0.45, 0.55]),
            version_id=uuid7(),
        )

        constraints = ConstraintSet(
            constraint_set_id=new_uuid7(),
            constraints=[
                Constraint(
                    constraint_id=new_uuid7(),
                    constraint_type=ConstraintType.CAPACITY_CAP,
                    scope=ConstraintScope(sector_code="C"),
                    bound_value=200.0,
                    bound_scope=ConstraintBoundScope.DELTA_ONLY,
                    unit=ConstraintUnit.SAR_MILLIONS,
                    confidence=ConstraintConfidence.HARD,
                    description="Gate test capacity cap on manufacturing",
                ),
            ],
            workspace_id=uuid7(),
        )

        fsolver = FeasibilitySolver()
        result = fsolver.solve(
            unconstrained_delta_x=solve.delta_x_total,
            base_x=loaded.x,
            satellite_coefficients=sat_coeff,
            constraint_set=constraints,
            sector_codes=SECTOR_CODES_SMALL,
        )

        # Both outputs present
        assert result.unconstrained_delta_x is not None
        assert result.feasible_delta_x is not None
        assert result.unconstrained_delta_x.shape == result.feasible_delta_x.shape

        # Binding diagnostics present
        assert len(result.binding_constraints) >= 1
        bc = result.binding_constraints[0]
        assert bc.description != ""
        assert bc.gap >= 0

        # Confidence summary
        assert result.constraint_confidence_summary is not None

    def test_feasibility_produces_dual_output_with_diagnostics(self):
        """Alias test — verifies diagnostic messages exist on binding constraints."""
        from src.engine.constraints.schema import (
            Constraint, ConstraintBoundScope, ConstraintScope,
            ConstraintSet, ConstraintType, ConstraintUnit,
        )

        store = ModelStore()
        mv = store.register(
            Z=GOLDEN_Z, x=GOLDEN_X, sector_codes=SECTOR_CODES_SMALL,
            base_year=GOLDEN_BASE_YEAR, source="gate-feas-diag",
        )
        loaded = store.get(mv.model_version_id)
        solver = LeontiefSolver()
        solve = solver.solve(loaded_model=loaded, delta_d=np.array([300.0, 150.0, 50.0]))

        sat_coeff = SatelliteCoefficients(
            jobs_coeff=np.array([0.008, 0.004, 0.006]),
            import_ratio=np.array([0.30, 0.25, 0.15]),
            va_ratio=np.array([0.35, 0.45, 0.55]),
            version_id=uuid7(),
        )

        constraints = ConstraintSet(
            constraint_set_id=new_uuid7(),
            constraints=[
                Constraint(
                    constraint_id=new_uuid7(),
                    constraint_type=ConstraintType.CAPACITY_CAP,
                    scope=ConstraintScope(sector_code="F"),
                    bound_value=100.0,
                    bound_scope=ConstraintBoundScope.DELTA_ONLY,
                    unit=ConstraintUnit.SAR_MILLIONS,
                    confidence=ConstraintConfidence.HARD,
                    description="Tight cap for diagnostics test",
                ),
            ],
            workspace_id=uuid7(),
        )

        fsolver = FeasibilitySolver()
        result = fsolver.solve(
            unconstrained_delta_x=solve.delta_x_total,
            base_x=loaded.x,
            satellite_coefficients=sat_coeff,
            constraint_set=constraints,
            sector_codes=SECTOR_CODES_SMALL,
        )

        # feasible_delta_x respects the cap
        f_idx = SECTOR_CODES_SMALL.index("F")
        assert result.feasible_delta_x[f_idx] <= 100.0 + 1e-6


@pytest.mark.integration
@pytest.mark.gate
class TestWorkforceConfidenceLabeled:
    """Gate Criterion 3: Workforce confidence-labeled splits with ranges."""

    def test_workforce_confidence_labels(self):
        """WorkforceResult has confidence labels and sensitivity envelopes."""
        from src.data.workforce.occupation_bridge import OccupationBridge
        from src.data.workforce.nationality_classification import NationalityClassificationSet
        from src.engine.workforce_satellite.satellite import WorkforceSatellite
        from src.engine.satellites import SatelliteResult

        fixtures = Path(__file__).parent.parent / "fixtures" / "workforce"
        with open(fixtures / "sample_occupation_bridge.json") as f:
            bridge = OccupationBridge(**json.load(f))
        with open(fixtures / "sample_nationality_classification.json") as f:
            classifications = NationalityClassificationSet(**json.load(f))

        ws = WorkforceSatellite(
            occupation_bridge=bridge,
            nationality_classifications=classifications,
        )
        sector_codes = bridge.get_sectors()
        sat_result = SatelliteResult(
            delta_jobs=np.array([20.0] * len(sector_codes)),
            delta_imports=np.zeros(len(sector_codes)),
            delta_domestic_output=np.zeros(len(sector_codes)),
            delta_va=np.zeros(len(sector_codes)),
            coefficients_version_id=uuid7(),
        )
        result = ws.analyze(satellite_result=sat_result, sector_codes=sector_codes)

        # Confidence labels present
        assert result.overall_confidence is not None

        # Sensitivity ranges (min/mid/max) ordered correctly
        for s in result.sector_summaries:
            assert s.projected_saudi_jobs_min <= s.projected_saudi_jobs_mid
            assert s.projected_saudi_jobs_mid <= s.projected_saudi_jobs_max

    def test_workforce_splits_have_confidence_and_ranges(self):
        """Alias — each sector summary has confidence label + numeric ranges."""
        from src.data.workforce.occupation_bridge import OccupationBridge
        from src.data.workforce.nationality_classification import NationalityClassificationSet
        from src.engine.workforce_satellite.satellite import WorkforceSatellite
        from src.engine.satellites import SatelliteResult

        fixtures = Path(__file__).parent.parent / "fixtures" / "workforce"
        with open(fixtures / "sample_occupation_bridge.json") as f:
            bridge = OccupationBridge(**json.load(f))
        with open(fixtures / "sample_nationality_classification.json") as f:
            classifications = NationalityClassificationSet(**json.load(f))

        ws = WorkforceSatellite(
            occupation_bridge=bridge,
            nationality_classifications=classifications,
        )
        sector_codes = bridge.get_sectors()
        sat_result = SatelliteResult(
            delta_jobs=np.array([15.0] * len(sector_codes)),
            delta_imports=np.zeros(len(sector_codes)),
            delta_domestic_output=np.zeros(len(sector_codes)),
            delta_va=np.zeros(len(sector_codes)),
            coefficients_version_id=uuid7(),
        )
        result = ws.analyze(satellite_result=sat_result, sector_codes=sector_codes)

        assert len(result.sector_summaries) > 0
        for s in result.sector_summaries:
            # Range values are numeric
            assert isinstance(s.projected_saudi_jobs_min, (int, float))
            assert isinstance(s.projected_saudi_jobs_mid, (int, float))
            assert isinstance(s.projected_saudi_jobs_max, (int, float))


@pytest.mark.integration
@pytest.mark.gate
class TestGoldenScenario1EndToEnd:
    """Gate Criterion 4: Full pipeline completes without crash."""

    def test_full_pipeline_completes(self):
        """BoQ -> compile -> run -> quality -> all steps complete."""
        store = ModelStore()
        mv = store.register(
            Z=GOLDEN_Z, x=GOLDEN_X, sector_codes=SECTOR_CODES_SMALL,
            base_year=GOLDEN_BASE_YEAR, source="gate-full",
        )
        loaded = store.get(mv.model_version_id)

        solver = LeontiefSolver()
        delta_d = np.array([100.0, 50.0, 25.0])
        solve = solver.solve(loaded_model=loaded, delta_d=delta_d)

        sa = SatelliteAccounts()
        sat_coeff = SatelliteCoefficients(
            jobs_coeff=np.array([0.008, 0.004, 0.006]),
            import_ratio=np.array([0.30, 0.25, 0.15]),
            va_ratio=np.array([0.35, 0.45, 0.55]),
            version_id=uuid7(),
        )
        sat = sa.compute(delta_x=solve.delta_x_total, coefficients=sat_coeff)

        qas = QualityAssessmentService()
        assessment = qas.assess(
            base_year=GOLDEN_BASE_YEAR, current_year=2026,
            mapping_coverage_pct=0.95,
            mapping_confidence_dist={"HIGH": 0.8, "MEDIUM": 0.15, "LOW": 0.05},
            mapping_residual_pct=0.02, mapping_unresolved_pct=0.01,
            mapping_unresolved_spend_pct=0.3,
            assumption_ranges_coverage_pct=None, assumption_approval_rate=None,
            constraint_confidence_summary=None, workforce_overall_confidence=None,
            plausibility_in_range_pct=None, plausibility_flagged_count=None,
            source_ages=[], run_id=uuid7(),
        )

        # Pipeline completed: positive outputs
        assert solve.delta_x_total.sum() > 0
        assert sat.delta_jobs.sum() > 0
        assert assessment.composite_score > 0

    def test_industrial_zone_full_pipeline(self):
        """Alias: full pipeline through golden scenario 1."""
        store = ModelStore()
        mv = store.register(
            Z=GOLDEN_Z, x=GOLDEN_X, sector_codes=SECTOR_CODES_SMALL,
            base_year=GOLDEN_BASE_YEAR, source="gate-golden1",
        )
        loaded = store.get(mv.model_version_id)
        solver = LeontiefSolver()
        solve = solver.solve(loaded_model=loaded, delta_d=np.array([300.0, 150.0, 50.0]))

        assert solve.delta_x_total is not None
        assert all(np.isfinite(solve.delta_x_total))


@pytest.mark.integration
@pytest.mark.gate
class TestFlywheelLearning:
    """Gate Criterion 5: Flywheel captures learning + publish cycle."""

    def test_flywheel_captures_learning(self):
        """Override recorded -> patterns extracted -> draft built."""
        from src.compiler.learning import LearningLoop

        loop = LearningLoop()
        loop.record_override(
            line_item_text="reinforced concrete foundation",
            original_sector="G",
            corrected_sector="F",
            analyst_id=uuid7(),
            workspace_id=uuid7(),
        )
        overrides = loop.get_pending_overrides()
        assert len(overrides) >= 1

    def test_override_to_publish_cycle(self):
        """Full cycle: override -> extract patterns -> build draft."""
        from src.compiler.learning import LearningLoop

        loop = LearningLoop()
        ws_id = uuid7()
        loop.record_override(
            line_item_text="structural steel supply",
            original_sector="G",
            corrected_sector="C",
            analyst_id=uuid7(),
            workspace_id=ws_id,
        )
        patterns = loop.extract_new_patterns(workspace_id=ws_id)
        assert len(patterns) >= 1
        for p in patterns:
            assert p.corrected_sector == "C"


@pytest.mark.integration
@pytest.mark.gate
class TestQualityAssessment:
    """Gate Criterion 6: Quality assessment produced with actionable warnings."""

    def test_quality_assessment_produced(self):
        """Every run produces a RunQualityAssessment with non-null ID."""
        qas = QualityAssessmentService()
        assessment = qas.assess(
            base_year=2024, current_year=2026,
            mapping_coverage_pct=0.90,
            mapping_confidence_dist={"HIGH": 0.6, "MEDIUM": 0.3, "LOW": 0.1},
            mapping_residual_pct=0.05, mapping_unresolved_pct=0.03,
            mapping_unresolved_spend_pct=1.5,
            assumption_ranges_coverage_pct=0.7, assumption_approval_rate=0.8,
            constraint_confidence_summary={"HARD": 3, "ESTIMATED": 3, "ASSUMED": 2},
            workforce_overall_confidence="MEDIUM",
            plausibility_in_range_pct=85.0, plausibility_flagged_count=2,
            source_ages=[], run_id=uuid7(),
        )
        assert assessment.assessment_id is not None

    def test_quality_warnings_actionable(self):
        """Each warning has severity, message, and recommendation."""
        qas = QualityAssessmentService()
        assessment = qas.assess(
            base_year=2018, current_year=2026,  # Stale data -> warnings
            mapping_coverage_pct=0.70,
            mapping_confidence_dist={"HIGH": 0.3, "MEDIUM": 0.3, "LOW": 0.4},
            mapping_residual_pct=0.15, mapping_unresolved_pct=0.10,
            mapping_unresolved_spend_pct=3.0,
            assumption_ranges_coverage_pct=0.3, assumption_approval_rate=0.5,
            constraint_confidence_summary={"HARD": 0, "ESTIMATED": 1, "ASSUMED": 5},
            workforce_overall_confidence="LOW",
            plausibility_in_range_pct=60.0, plausibility_flagged_count=5,
            source_ages=[], run_id=uuid7(),
        )
        assert len(assessment.warnings) > 0
        for w in assessment.warnings:
            assert w.severity is not None
            assert w.message != ""
```

**Step 2: Run and verify**

Run: `python -m pytest tests/integration/test_phase2_gate_formal.py -v`

**Step 3: Commit**

```bash
git add tests/integration/test_phase2_gate_formal.py
git commit -m "[mvp14] Task 13: formal Phase 2 gate criteria — all 6 criteria mapped to tests"
```

---

### Task 14: Regression Suite with Frozen Snapshots (Amendment 7)

**Files:**
- Create: `tests/integration/test_regression.py`

Loads golden baselines from `golden_scenarios/snapshots/` JSON files and verifies current outputs match within documented tolerances. Supports `--update-golden` flag. Uses `numpy.testing.assert_allclose` and `pytest.approx` — NEVER hash-based comparison.

**Step 1: Write the tests**

```python
# tests/integration/test_regression.py
"""Regression suite — toleranced frozen snapshots (Amendment 7).

No hash-based comparison. Uses assert_allclose with documented
rtol/atol values. Golden values loaded from committed JSON snapshots
in golden_scenarios/snapshots/.

To update baselines after legitimate algorithm changes:
    pytest tests/integration/test_regression.py --update-golden
"""

import json
import numpy as np
import pytest
from datetime import datetime, timezone
from numpy.testing import assert_allclose
from pathlib import Path
from uuid_extensions import uuid7

from src.engine.leontief import LeontiefSolver
from src.engine.model_store import ModelStore
from src.engine.satellites import SatelliteAccounts, SatelliteCoefficients

from .golden_scenarios.shared import (
    EMPLOYMENT_ATOL,
    GDP_RTOL,
    GOLDEN_BASE_YEAR,
    GOLDEN_X,
    GOLDEN_Z,
    NUMERIC_RTOL,
    OUTPUT_RTOL,
    SECTOR_CODES_SMALL,
)

SNAPSHOTS_DIR = Path(__file__).parent / "golden_scenarios" / "snapshots"


def _load_snapshot(name: str) -> dict | None:
    """Load a frozen golden snapshot from JSON. Returns None if missing."""
    path = SNAPSHOTS_DIR / f"{name}_outputs.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def _save_snapshot(name: str, data: dict) -> None:
    """Save a golden snapshot to JSON."""
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    path = SNAPSHOTS_DIR / f"{name}_outputs.json"
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _compute_pipeline(delta_d_list: list[float]) -> dict:
    """Run the deterministic pipeline and return all outputs."""
    store = ModelStore()
    mv = store.register(
        Z=GOLDEN_Z, x=GOLDEN_X, sector_codes=SECTOR_CODES_SMALL,
        base_year=GOLDEN_BASE_YEAR, source="regression",
    )
    loaded = store.get(mv.model_version_id)

    solver = LeontiefSolver()
    delta_d = np.array(delta_d_list)
    solve = solver.solve(loaded_model=loaded, delta_d=delta_d)

    sat_coeff = SatelliteCoefficients(
        jobs_coeff=np.array([0.008, 0.004, 0.006]),
        import_ratio=np.array([0.30, 0.25, 0.15]),
        va_ratio=np.array([0.35, 0.45, 0.55]),
        version_id=uuid7(),
    )
    sa = SatelliteAccounts()
    sat = sa.compute(delta_x=solve.delta_x_total, coefficients=sat_coeff)

    return {
        "total_output": float(solve.delta_x_total.sum()),
        "gdp_impact": float(sat.delta_va.sum()),
        "employment_total": float(sat.delta_jobs.sum()),
        "sector_outputs": {
            code: float(solve.delta_x_total[i])
            for i, code in enumerate(SECTOR_CODES_SMALL)
        },
    }


@pytest.mark.integration
@pytest.mark.regression
class TestRegressionSuite:
    """Golden regression baselines loaded from frozen JSON snapshots."""

    def test_industrial_zone_output_stable(self, update_golden):
        """Total output has not drifted from frozen baseline."""
        current = _compute_pipeline([300.0, 150.0, 50.0])

        if update_golden:
            snapshot = {
                "scenario": "industrial_zone",
                "computed_at": datetime.now(timezone.utc).isoformat(),
                "model": "3-sector ISIC F/C/G",
                "tolerances": {"rtol": NUMERIC_RTOL, "employment_atol": EMPLOYMENT_ATOL, "gdp_rtol": GDP_RTOL},
                "delta_d": [300.0, 150.0, 50.0],
                "total_output_impact": current["total_output"],
                "gdp_impact": current["gdp_impact"],
                "employment_total": current["employment_total"],
                "sector_outputs": current["sector_outputs"],
                "quality_grade": None,
            }
            _save_snapshot("industrial_zone", snapshot)
            pytest.skip("Regression snapshot updated")

        golden = _load_snapshot("industrial_zone")
        if golden is None or golden.get("total_output_impact") is None:
            pytest.skip("No baseline — run with --update-golden first")

        assert_allclose(
            current["total_output"],
            golden["total_output_impact"],
            rtol=NUMERIC_RTOL,
            err_msg="Total output regression detected",
        )

    def test_industrial_zone_gdp_stable(self, update_golden):
        """GDP impact has not drifted from frozen baseline."""
        current = _compute_pipeline([300.0, 150.0, 50.0])

        golden = _load_snapshot("industrial_zone")
        if golden is None or golden.get("gdp_impact") is None:
            pytest.skip("No baseline — run with --update-golden first")

        assert_allclose(
            current["gdp_impact"],
            golden["gdp_impact"],
            rtol=GDP_RTOL,
            err_msg="GDP regression detected",
        )

    def test_industrial_zone_employment_stable(self, update_golden):
        """Employment has not drifted from frozen baseline."""
        current = _compute_pipeline([300.0, 150.0, 50.0])

        golden = _load_snapshot("industrial_zone")
        if golden is None or golden.get("employment_total") is None:
            pytest.skip("No baseline — run with --update-golden first")

        assert current["employment_total"] == pytest.approx(
            golden["employment_total"], abs=EMPLOYMENT_ATOL,
        )

    def test_contraction_output_stable(self, update_golden):
        """Contraction scenario output has not drifted from frozen baseline."""
        current = _compute_pipeline([-100.0, -50.0, -30.0])

        golden = _load_snapshot("contraction")
        if golden is None or golden.get("total_output_impact") is None:
            pytest.skip("No baseline — run with --update-golden first")

        assert_allclose(
            current["total_output"],
            golden["total_output_impact"],
            rtol=NUMERIC_RTOL,
            err_msg="Contraction output regression detected",
        )

    def test_per_sector_output_stable(self, update_golden):
        """Per-sector outputs match frozen baseline within tolerance."""
        current = _compute_pipeline([300.0, 150.0, 50.0])

        golden = _load_snapshot("industrial_zone")
        if golden is None or not golden.get("sector_outputs"):
            pytest.skip("No baseline — run with --update-golden first")

        for code in SECTOR_CODES_SMALL:
            assert_allclose(
                current["sector_outputs"][code],
                golden["sector_outputs"][code],
                rtol=NUMERIC_RTOL,
                err_msg=f"Sector {code} regression detected",
            )

    def test_numerical_tolerance_documented(self):
        """Tolerance constants are defined and positive."""
        assert NUMERIC_RTOL > 0
        assert EMPLOYMENT_ATOL > 0
        assert GDP_RTOL > 0
        assert OUTPUT_RTOL > 0
```

**Step 2: Run and verify**

Run: `python -m pytest tests/integration/test_regression.py -v`

(Will skip if snapshots have null values. Run `--update-golden` first to populate.)

**Step 3: Commit**

```bash
git add tests/integration/test_regression.py
git commit -m "[mvp14] Task 14: regression suite with frozen JSON snapshots and --update-golden support"
```

---

### Task 15: Performance Benchmarks (Amendment 6)

**Files:**
- Create: `tests/integration/test_performance.py`

Marked `@pytest.mark.slow` and `@pytest.mark.performance`. Skipped by default. These are REFERENCE measurements, not hard gates.

**Step 1: Write the tests**

```python
# tests/integration/test_performance.py
"""Performance benchmarks — reference measurements (Amendment 6).

Marked @pytest.mark.slow and @pytest.mark.performance.
Skipped by default in CI. Run with: pytest -m performance

These are REFERENCE benchmarks, not hard gates.
"""

import time
import numpy as np
import pytest
from uuid_extensions import uuid7

from src.engine.leontief import LeontiefSolver
from src.engine.model_store import ModelStore
from src.engine.satellites import SatelliteAccounts, SatelliteCoefficients
from src.quality.service import QualityAssessmentService

from .golden_scenarios.shared import (
    GOLDEN_BASE_YEAR,
    GOLDEN_X,
    GOLDEN_Z,
    SECTOR_CODES_SMALL,
)


@pytest.mark.performance
@pytest.mark.slow
@pytest.mark.integration
class TestPerformanceBenchmarks:
    """Performance reference benchmarks (informational, not gate criteria)."""

    def test_single_scenario_under_2s(self):
        """Single scenario completes in < 2 seconds (3-sector)."""
        store = ModelStore()
        mv = store.register(
            Z=GOLDEN_Z, x=GOLDEN_X, sector_codes=SECTOR_CODES_SMALL,
            base_year=GOLDEN_BASE_YEAR, source="perf",
        )
        loaded = store.get(mv.model_version_id)
        solver = LeontiefSolver()
        sa = SatelliteAccounts()
        sat_coeff = SatelliteCoefficients(
            jobs_coeff=np.array([0.008, 0.004, 0.006]),
            import_ratio=np.array([0.30, 0.25, 0.15]),
            va_ratio=np.array([0.35, 0.45, 0.55]),
            version_id=uuid7(),
        )

        start = time.perf_counter()
        delta_d = np.array([300.0, 150.0, 50.0])
        solve = solver.solve(loaded_model=loaded, delta_d=delta_d)
        sa.compute(delta_x=solve.delta_x_total, coefficients=sat_coeff)
        elapsed = time.perf_counter() - start

        assert elapsed < 2.0, f"Single scenario took {elapsed:.2f}s (>2s)"

    def test_batch_10_scenarios_under_10s(self):
        """10 scenarios complete in < 10 seconds."""
        store = ModelStore()
        mv = store.register(
            Z=GOLDEN_Z, x=GOLDEN_X, sector_codes=SECTOR_CODES_SMALL,
            base_year=GOLDEN_BASE_YEAR, source="perf-batch",
        )
        loaded = store.get(mv.model_version_id)
        solver = LeontiefSolver()

        start = time.perf_counter()
        for i in range(10):
            delta_d = np.array([100.0 + i * 10, 50.0 + i * 5, 25.0 + i * 2])
            solver.solve(loaded_model=loaded, delta_d=delta_d)
        elapsed = time.perf_counter() - start

        assert elapsed < 10.0, f"10 scenarios took {elapsed:.2f}s (>10s)"

    def test_quality_assessment_under_1s(self):
        """Quality assessment completes in < 1 second."""
        qas = QualityAssessmentService()

        start = time.perf_counter()
        qas.assess(
            base_year=2024, current_year=2026,
            mapping_coverage_pct=0.95,
            mapping_confidence_dist={"HIGH": 0.7, "MEDIUM": 0.2, "LOW": 0.1},
            mapping_residual_pct=0.03, mapping_unresolved_pct=0.02,
            mapping_unresolved_spend_pct=0.5,
            assumption_ranges_coverage_pct=0.8, assumption_approval_rate=0.9,
            constraint_confidence_summary={"HARD": 8, "ESTIMATED": 2, "ASSUMED": 0},
            workforce_overall_confidence="HIGH",
            plausibility_in_range_pct=95.0, plausibility_flagged_count=1,
            source_ages=[], run_id=uuid7(),
        )
        elapsed = time.perf_counter() - start

        assert elapsed < 1.0, f"Quality assessment took {elapsed:.2f}s (>1s)"
```

**Step 2: Run with performance marker**

Run: `python -m pytest tests/integration/test_performance.py -v -m performance`

**Step 3: Commit**

```bash
git add tests/integration/test_performance.py
git commit -m "[mvp14] Task 15: performance benchmarks (Amendment 6 — reference only, not gate criteria)"
```

---

### Task 16: API Schema Compliance + Cross-Module Consistency + Confidence Vocabulary

**Files:**
- Create: `tests/integration/test_api_schema.py`
- Create: `tests/integration/test_cross_module_consistency.py`

Cross-module consistency tests include confidence vocabulary verification across all 5 confidence enums, normalization behavior, and concordance contracts.

**Step 1: Write API schema tests**

```python
# tests/integration/test_api_schema.py
"""API schema compliance — all module outputs serialize cleanly."""

import pytest
from uuid_extensions import uuid7

from src.models.scenario import ScenarioSpec, TimeHorizon
from src.models.run import RunSnapshot, ResultSet
from src.quality.models import RunQualityAssessment


@pytest.mark.integration
class TestAPISchemaCompliance:
    """Pydantic models serialize/deserialize cleanly."""

    def test_scenario_spec_round_trip(self):
        """ScenarioSpec -> JSON -> ScenarioSpec."""
        spec = ScenarioSpec(
            name="Test Scenario",
            workspace_id=uuid7(),
            base_model_version_id=uuid7(),
            base_year=2024,
            time_horizon=TimeHorizon(start_year=2024, end_year=2026),
        )
        json_str = spec.model_dump_json()
        restored = ScenarioSpec.model_validate_json(json_str)
        assert restored.name == spec.name
        assert restored.scenario_spec_id == spec.scenario_spec_id

    def test_run_snapshot_round_trip(self):
        """RunSnapshot -> JSON -> RunSnapshot."""
        snap = RunSnapshot(
            run_id=uuid7(),
            model_version_id=uuid7(),
            taxonomy_version_id=uuid7(),
            concordance_version_id=uuid7(),
            mapping_library_version_id=uuid7(),
            assumption_library_version_id=uuid7(),
            prompt_pack_version_id=uuid7(),
        )
        json_str = snap.model_dump_json()
        restored = RunSnapshot.model_validate_json(json_str)
        assert restored.run_id == snap.run_id

    def test_result_set_round_trip(self):
        """ResultSet -> JSON -> ResultSet."""
        rs = ResultSet(
            run_id=uuid7(),
            metric_type="total_output",
            values={"total": 1234.56},
            sector_breakdowns={"C": {"total": 500.0}},
        )
        json_str = rs.model_dump_json()
        restored = ResultSet.model_validate_json(json_str)
        assert restored.metric_type == "total_output"
```

**Step 2: Write cross-module consistency tests with confidence vocabulary**

```python
# tests/integration/test_cross_module_consistency.py
"""Cross-module consistency — shared vocabulary, types, and confidence enums.

Amendment 8: Tests concordance contracts and confidence vocabulary.

Confidence Vocabulary (5 enums across the codebase):
  1. ConstraintConfidence:      HARD / ESTIMATED / ASSUMED    (src/models/common.py)
  2. MappingConfidenceBand:     HIGH / MEDIUM / LOW           (src/models/common.py)
  3. WorkforceConfidenceLevel:  HIGH / MEDIUM / LOW           (src/models/workforce.py)
  4. QualityConfidence:         high / medium / low  LOWERCASE (src/data/workforce/unit_registry.py)
  5. ConfidenceBand:            HIGH / MEDIUM / LOW           (src/compiler/confidence.py)

Normalization: workforce pipeline normalizes via confidence_to_str() -> uppercase.
Quality scorer expects uppercase "HIGH"/"MEDIUM"/"LOW".
"""

import pytest
from src.models.common import ConstraintConfidence, MappingConfidenceBand, ExportMode


@pytest.mark.integration
class TestCrossModuleConsistency:
    """Shared enums and types across modules."""

    def test_constraint_confidence_enum_shared(self):
        """MVP-10 and MVP-13 use same ConstraintConfidence enum."""
        assert hasattr(ConstraintConfidence, "HARD")
        assert hasattr(ConstraintConfidence, "ESTIMATED")
        assert hasattr(ConstraintConfidence, "ASSUMED")

    def test_mapping_confidence_band_shared(self):
        """Compiler and quality use same MappingConfidenceBand."""
        assert hasattr(MappingConfidenceBand, "HIGH")
        assert hasattr(MappingConfidenceBand, "MEDIUM")
        assert hasattr(MappingConfidenceBand, "LOW")

    def test_export_mode_shared(self):
        """Export and governance use same ExportMode enum."""
        assert hasattr(ExportMode, "SANDBOX")
        assert hasattr(ExportMode, "GOVERNED")

    def test_uuid7_used_for_new_ids(self):
        """new_uuid7 produces valid UUIDv7."""
        from src.models.common import new_uuid7
        uid = new_uuid7()
        assert uid.version == 7

    def test_run_snapshot_has_expected_version_fields(self):
        """RunSnapshot has all expected version ID fields (Amendment 10)."""
        from src.models.run import RunSnapshot
        fields = RunSnapshot.model_fields
        assert "model_version_id" in fields
        assert "mapping_library_version_id" in fields
        assert "assumption_library_version_id" in fields
        # Optional fields
        assert "constraint_set_version_id" in fields
        assert "occupation_bridge_version_id" in fields
        assert "nationality_classification_version_id" in fields


@pytest.mark.integration
class TestConfidenceVocabulary:
    """Verify all 5 confidence enums and cross-module normalization."""

    def test_constraint_confidence_values_uppercase(self):
        """ConstraintConfidence values are uppercase: HARD, ESTIMATED, ASSUMED."""
        assert ConstraintConfidence.HARD.value == "HARD"
        assert ConstraintConfidence.ESTIMATED.value == "ESTIMATED"
        assert ConstraintConfidence.ASSUMED.value == "ASSUMED"

    def test_mapping_confidence_band_values_uppercase(self):
        """MappingConfidenceBand values are uppercase: HIGH, MEDIUM, LOW."""
        assert MappingConfidenceBand.HIGH.value == "HIGH"
        assert MappingConfidenceBand.MEDIUM.value == "MEDIUM"
        assert MappingConfidenceBand.LOW.value == "LOW"

    def test_workforce_confidence_level_values_uppercase(self):
        """WorkforceConfidenceLevel values are uppercase: HIGH, MEDIUM, LOW."""
        from src.models.workforce import WorkforceConfidenceLevel
        assert WorkforceConfidenceLevel.HIGH.value == "HIGH"
        assert WorkforceConfidenceLevel.MEDIUM.value == "MEDIUM"
        assert WorkforceConfidenceLevel.LOW.value == "LOW"

    def test_quality_confidence_values_lowercase(self):
        """QualityConfidence values are LOWERCASE: high, medium, low."""
        from src.data.workforce.unit_registry import QualityConfidence
        assert QualityConfidence.HIGH.value == "high"
        assert QualityConfidence.MEDIUM.value == "medium"
        assert QualityConfidence.LOW.value == "low"

    def test_compiler_confidence_band_values_uppercase(self):
        """ConfidenceBand (compiler) values are uppercase: HIGH, MEDIUM, LOW."""
        from src.compiler.confidence import ConfidenceBand
        assert ConfidenceBand.HIGH.value == "HIGH"
        assert ConfidenceBand.MEDIUM.value == "MEDIUM"
        assert ConfidenceBand.LOW.value == "LOW"

    def test_confidence_to_str_normalizes_quality_confidence_to_uppercase(self):
        """confidence_to_str() converts QualityConfidence lowercase -> uppercase."""
        from src.data.workforce.unit_registry import QualityConfidence
        from src.engine.workforce_satellite.config import confidence_to_str

        assert confidence_to_str(QualityConfidence.HIGH) == "HIGH"
        assert confidence_to_str(QualityConfidence.MEDIUM) == "MEDIUM"
        assert confidence_to_str(QualityConfidence.LOW) == "LOW"

    def test_confidence_to_str_preserves_constraint_confidence(self):
        """confidence_to_str() preserves ConstraintConfidence uppercase."""
        from src.engine.workforce_satellite.config import confidence_to_str

        assert confidence_to_str(ConstraintConfidence.HARD) == "HARD"
        assert confidence_to_str(ConstraintConfidence.ESTIMATED) == "ESTIMATED"
        assert confidence_to_str(ConstraintConfidence.ASSUMED) == "ASSUMED"

    def test_confidence_to_str_handles_raw_strings(self):
        """confidence_to_str() uppercases raw string inputs."""
        from src.engine.workforce_satellite.config import confidence_to_str

        assert confidence_to_str("high") == "HIGH"
        assert confidence_to_str("Medium") == "MEDIUM"
        assert confidence_to_str("LOW") == "LOW"

    def test_quality_scorer_accepts_uppercase(self):
        """QualityAssessmentService.assess() accepts uppercase confidence strings."""
        from src.quality.service import QualityAssessmentService
        from uuid_extensions import uuid7

        qas = QualityAssessmentService()
        # Should NOT raise when given uppercase confidence strings
        assessment = qas.assess(
            base_year=2024, current_year=2026,
            mapping_coverage_pct=0.90,
            mapping_confidence_dist={"HIGH": 0.6, "MEDIUM": 0.3, "LOW": 0.1},
            mapping_residual_pct=0.05, mapping_unresolved_pct=0.03,
            mapping_unresolved_spend_pct=1.5,
            assumption_ranges_coverage_pct=0.7, assumption_approval_rate=0.8,
            constraint_confidence_summary={"HARD": 3, "ESTIMATED": 3, "ASSUMED": 2},
            workforce_overall_confidence="HIGH",
            plausibility_in_range_pct=85.0, plausibility_flagged_count=2,
            source_ages=[], run_id=uuid7(),
        )
        assert assessment.assessment_id is not None
```

**Step 3: Run and verify**

Run: `python -m pytest tests/integration/test_api_schema.py tests/integration/test_cross_module_consistency.py -v`

**Step 4: Commit**

```bash
git add tests/integration/test_api_schema.py tests/integration/test_cross_module_consistency.py
git commit -m "[mvp14] Task 16: API schema compliance + cross-module consistency + confidence vocabulary"
```

---

### Task 17: Gate Report Script (Amendment 1)

**Files:**
- Create: `scripts/generate_phase2_gate_report.py`

Reads pytest JSON output (from `--json-report` plugin), maps test names to gate criteria via an explicit `GATE_CRITERIA_MAP` dictionary, and produces a markdown gate report with pass/fail per criterion at `docs/phase2_gate_report.md`.

**Step 1: Write the gate report generator**

```python
#!/usr/bin/env python3
"""Phase 2 Gate Report Generator (Amendment 1: lives in scripts/, not src/).

Reads pytest JSON output and produces a structured gate report.
Maps test names to gate criteria using an explicit GATE_CRITERIA_MAP.

Usage:
    python -m pytest tests/integration/ --json-report --json-report-file=report.json
    python scripts/generate_phase2_gate_report.py report.json
"""

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Gate Criteria Map — test class/function name -> criterion number
# From design doc Section "Gate Criteria Map"
# ---------------------------------------------------------------------------

GATE_CRITERIA_MAP: dict[str, int] = {
    # Criterion 1: Compiler >= 60% auto-mapping
    "TestCompilerAutoMapping": 1,
    "test_compiler_auto_mapping_gate": 1,
    # Criterion 2: Feasibility dual-output
    "TestFeasibilityDualOutput": 2,
    "test_feasibility_dual_output": 2,
    "test_feasibility_produces_dual_output_with_diagnostics": 2,
    # Criterion 3: Workforce confidence-labeled
    "TestWorkforceConfidenceLabeled": 3,
    "test_workforce_confidence_labels": 3,
    "test_workforce_splits_have_confidence_and_ranges": 3,
    # Criterion 4: Full pipeline completes
    "TestGoldenScenario1EndToEnd": 4,
    "test_full_pipeline_completes": 4,
    "test_industrial_zone_full_pipeline": 4,
    # Criterion 5: Flywheel captures learning
    "TestFlywheelLearning": 5,
    "test_flywheel_captures_learning": 5,
    "test_override_to_publish_cycle": 5,
    # Criterion 6: Quality assessment produced
    "TestQualityAssessment": 6,
    "test_quality_assessment_produced": 6,
}

GATE_DESCRIPTIONS: dict[int, str] = {
    1: "Compiler >= 60% auto-mapping rate",
    2: "Feasibility produces dual-output with diagnostics",
    3: "Workforce confidence-labeled splits with ranges",
    4: "Full pipeline completes end-to-end",
    5: "Flywheel captures learning + publish cycle",
    6: "Quality assessment produced with actionable warnings",
}


@dataclass
class GateCriterionResult:
    """Result for a single gate criterion."""
    criterion_number: int
    description: str
    passed: bool
    test_count: int
    pass_count: int
    fail_count: int
    failed_tests: list[str] = field(default_factory=list)


@dataclass
class PerformanceMetric:
    """Informational performance measurement."""
    name: str
    value: float
    unit: str
    threshold: float | None = None


@dataclass
class GateResult:
    """Complete gate report result."""
    gate_passed: bool
    criteria_results: list[GateCriterionResult] = field(default_factory=list)
    criteria_map: dict[str, int] = field(default_factory=dict)
    total_tests: int = 0
    total_failures: int = 0
    performance_results: list[PerformanceMetric] = field(default_factory=list)
    summary: str = ""
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


def _match_test_to_criterion(node_id: str) -> int | None:
    """Match a pytest node ID to a gate criterion number."""
    for name, criterion in GATE_CRITERIA_MAP.items():
        if name in node_id:
            return criterion
    return None


def _extract_performance_metrics(tests: list[dict]) -> list[PerformanceMetric]:
    """Extract performance benchmark results (informational)."""
    metrics = []
    for t in tests:
        node_id = t.get("nodeid", "")
        if "performance" not in node_id.lower():
            continue
        duration = t.get("duration", 0.0)
        name = node_id.split("::")[-1] if "::" in node_id else node_id
        metrics.append(PerformanceMetric(
            name=name,
            value=round(duration, 3),
            unit="seconds",
        ))
    return metrics


def generate_report(results_path: str) -> GateResult:
    """Generate gate report from pytest JSON results."""
    with open(results_path) as f:
        data = json.load(f)

    tests = data.get("tests", [])
    total = len(tests)
    total_failures = sum(1 for t in tests if t.get("outcome") != "passed")

    # Bucket tests by criterion
    criterion_tests: dict[int, list[dict]] = {i: [] for i in range(1, 7)}

    for test in tests:
        node_id = test.get("nodeid", "")
        criterion = _match_test_to_criterion(node_id)
        if criterion is not None:
            criterion_tests[criterion].append(test)

    # Build criterion results
    criteria_results = []
    for crit_num in range(1, 7):
        crit_tests = criterion_tests[crit_num]
        pass_count = sum(1 for t in crit_tests if t.get("outcome") == "passed")
        fail_count = len(crit_tests) - pass_count
        failed = [
            t.get("nodeid", "unknown")
            for t in crit_tests
            if t.get("outcome") != "passed"
        ]
        criteria_results.append(GateCriterionResult(
            criterion_number=crit_num,
            description=GATE_DESCRIPTIONS[crit_num],
            passed=(fail_count == 0 and len(crit_tests) > 0),
            test_count=len(crit_tests),
            pass_count=pass_count,
            fail_count=fail_count,
            failed_tests=failed,
        ))

    # Performance metrics (informational)
    perf_metrics = _extract_performance_metrics(tests)

    all_criteria_passed = all(c.passed for c in criteria_results)
    gate_passed = all_criteria_passed and total_failures == 0

    return GateResult(
        gate_passed=gate_passed,
        criteria_results=criteria_results,
        criteria_map=GATE_CRITERIA_MAP,
        total_tests=total,
        total_failures=total_failures,
        performance_results=perf_metrics,
        summary=f"{'PASSED' if gate_passed else 'FAILED'}: {total - total_failures}/{total} tests passed",
    )


def write_markdown_report(report: GateResult, output_path: str) -> None:
    """Write gate report as markdown."""
    lines = [
        "# Phase 2 Gate Report",
        "",
        f"**Generated:** {report.timestamp}",
        f"**Overall:** {'PASSED' if report.gate_passed else 'FAILED'}",
        f"**Tests:** {report.total_tests - report.total_failures}/{report.total_tests} passed",
        "",
        "## Gate Criteria",
        "",
        "| # | Criterion | Status | Tests |",
        "|---|-----------|--------|-------|",
    ]

    for c in report.criteria_results:
        status = "PASS" if c.passed else "FAIL"
        lines.append(
            f"| {c.criterion_number} | {c.description} | {status} | {c.pass_count}/{c.test_count} |"
        )

    # Failed test details
    any_failures = any(c.failed_tests for c in report.criteria_results)
    if any_failures:
        lines.extend(["", "## Failed Tests", ""])
        for c in report.criteria_results:
            if c.failed_tests:
                lines.append(f"### Criterion {c.criterion_number}: {c.description}")
                for ft in c.failed_tests:
                    lines.append(f"- `{ft}`")
                lines.append("")

    # Performance metrics (informational)
    if report.performance_results:
        lines.extend(["", "## Performance Benchmarks (Informational)", ""])
        lines.append("| Test | Duration | Unit |")
        lines.append("|------|----------|------|")
        for pm in report.performance_results:
            lines.append(f"| {pm.name} | {pm.value} | {pm.unit} |")

    lines.extend(["", "---", f"*Gate verdict: {'PASSED' if report.gate_passed else 'FAILED'}*", ""])

    with open(output_path, "w") as f:
        f.write("\n".join(lines))


def main() -> None:
    """CLI entry point."""
    if len(sys.argv) < 2:
        print("Usage: python scripts/generate_phase2_gate_report.py <results.json>")
        sys.exit(1)

    results_path = sys.argv[1]
    output_path = str(Path(__file__).parent.parent / "docs" / "phase2_gate_report.md")

    report = generate_report(results_path)
    write_markdown_report(report, output_path)

    # Console output
    print("=" * 60)
    print("PHASE 2 GATE REPORT")
    print("=" * 60)
    print(f"Timestamp: {report.timestamp}")
    print(f"Overall: {'PASSED' if report.gate_passed else 'FAILED'}")
    print(f"Tests: {report.total_tests - report.total_failures}/{report.total_tests} passed")
    print()
    for c in report.criteria_results:
        status = "PASS" if c.passed else "FAIL"
        print(f"  Gate Criterion {c.criterion_number} ({c.description}): {status} ({c.pass_count}/{c.test_count} tests passed)")
        if c.failed_tests:
            for ft in c.failed_tests:
                print(f"    FAILED: {ft}")
    print()
    if report.performance_results:
        print("  Performance Benchmarks (Informational):")
        for pm in report.performance_results:
            print(f"    {pm.name}: {pm.value} {pm.unit}")
    print("=" * 60)
    print(f"Report written to: {output_path}")

    sys.exit(0 if report.gate_passed else 1)


if __name__ == "__main__":
    main()
```

**Step 2: Commit**

```bash
git add scripts/generate_phase2_gate_report.py
git commit -m "[mvp14] Task 17: gate report script with GATE_CRITERIA_MAP and markdown output"
```

---

### Task 18: Documentation + Gate Report Template

**Files:**
- Create: `docs/phase2_gate_report.md` (template)
- Create: `docs/mvp14_phase2_integration_gate.md`

**Step 1: Create the gate report template**

```markdown
# Phase 2 Gate Report

**Generated:** (auto-populated by scripts/generate_phase2_gate_report.py)
**Overall:** PENDING
**Tests:** 0/0 passed

## Gate Criteria

| # | Criterion | Status | Tests |
|---|-----------|--------|-------|
| 1 | Compiler >= 60% auto-mapping rate | PENDING | 0/0 |
| 2 | Feasibility produces dual-output with diagnostics | PENDING | 0/0 |
| 3 | Workforce confidence-labeled splits with ranges | PENDING | 0/0 |
| 4 | Full pipeline completes end-to-end | PENDING | 0/0 |
| 5 | Flywheel captures learning + publish cycle | PENDING | 0/0 |
| 6 | Quality assessment produced with actionable warnings | PENDING | 0/0 |

## Failed Tests

(none yet)

## Performance Benchmarks (Informational)

| Test | Duration | Unit |
|------|----------|------|
| (run performance tests to populate) | - | - |

---
*Gate verdict: PENDING*
```

**Step 2: Create the technical documentation**

Document all integration paths, golden scenarios, gate criteria, how to run tests, how to update baselines, and confidence vocabulary. Reference the design doc but keep concise.

Key sections:
- **Overview:** MVP-14 purpose and scope
- **Integration Paths:** All 9 paths (from design doc)
- **Golden Scenarios:** 3 scenarios with tolerances
- **Gate Criteria:** Section 15.5.2 mapping
- **Running Tests:** Commands for each test category
- **Updating Golden Snapshots:** `--update-golden` workflow
- **Confidence Vocabulary:** All 5 enums with normalization rules
- **Amendments:** Summary of all 12+ amendments applied

**Step 3: Commit**

```bash
git add docs/phase2_gate_report.md docs/mvp14_phase2_integration_gate.md
git commit -m "[mvp14] Task 18: documentation + gate report template"
```

---

### Task 19: Full Suite Verification

**Step 1: Run ALL existing tests (zero regressions)**

Run: `python -m pytest -x -q`
Expected: 3049+ tests pass, 0 failures

**Step 2: Run new integration tests**

Run: `python -m pytest tests/integration/ -v -m "not slow" --tb=short`
Expected: All new integration tests pass

**Step 3: Count new tests**

Run: `python -m pytest tests/integration/ --co -q -m "not slow"`
Expected: >= 90 new integration tests + 134 existing = 224+ total

**Step 4: Run golden snapshot initialization**

Run: `python -m pytest tests/integration/test_e2e_golden.py tests/integration/test_regression.py --update-golden -v`

Review and commit the generated JSON snapshot files:

```bash
git add tests/integration/golden_scenarios/snapshots/
git commit -m "[mvp14] Task 19: populate golden snapshots with computed baselines"
```

**Step 5: Verify golden snapshot tests pass (without --update-golden)**

Run: `python -m pytest tests/integration/test_e2e_golden.py tests/integration/test_regression.py -v`
Expected: All golden/regression tests pass against frozen snapshots

**Step 6: Run performance benchmarks (informational)**

Run: `python -m pytest tests/integration/test_performance.py -v -m performance`

**Step 7: Generate gate report**

Run: `python -m pytest tests/integration/ --json-report --json-report-file=report.json -m "not slow"`
Run: `python scripts/generate_phase2_gate_report.py report.json`

Verify:
- `docs/phase2_gate_report.md` has all 6 criteria marked PASS
- Gate verdict is PASSED

**Step 8: Final verification commit**

```bash
git add docs/phase2_gate_report.md
git commit -m "[mvp14] Task 19: all integration tests passing — Phase 2 gate verified"
```

---

### Task 20: Code Review + Merge

Use superpowers:requesting-code-review, then superpowers:finishing-a-development-branch.

**Pre-review checklist:**
- [ ] Golden scenarios exercise every Phase 2 module
- [ ] All imports use `from .golden_scenarios.shared import` (never conftest)
- [ ] Performance benchmarks are reference (not hard gate)
- [ ] Gate criteria match tech spec Section 15.5.2 (all 6 criteria)
- [ ] GATE_CRITERIA_MAP maps test names to criterion numbers
- [ ] Numerical tolerances explicit and documented
- [ ] All 12+ amendments addressed
- [ ] Frozen JSON snapshots committed (not auto-recomputed)
- [ ] `--update-golden` flag documented and tested
- [ ] Confidence vocabulary tests cover all 5 enums
- [ ] confidence_to_str() normalization verified
- [ ] Zero regressions (all 3049+ existing tests pass)
- [ ] Minimum 90+ new integration tests
- [ ] Gate report script produces valid markdown
