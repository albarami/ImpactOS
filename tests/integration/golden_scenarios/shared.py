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
# Type II golden values for household-closed model
# ---------------------------------------------------------------------------

GOLDEN_COMPENSATION = [350.0, 900.0, 825.0]  # compensation of employees per sector
GOLDEN_HOUSEHOLD_SHARES = [0.30, 0.45, 0.20]  # household consumption shares (sum=0.95)

# Pre-computed Type II Leontief inverse B* = (I - A*)^{-1}
_w_golden = np.array(GOLDEN_COMPENSATION) / np.array(GOLDEN_X)
_h_golden = np.array(GOLDEN_HOUSEHOLD_SHARES)
_A_star = np.zeros((4, 4))
_A_star[:3, :3] = _A_SMALL
_A_star[3, :3] = _w_golden
_A_star[:3, 3] = _h_golden
EXPECTED_B_STAR_SMALL = np.linalg.inv(np.eye(4) - _A_star)

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
