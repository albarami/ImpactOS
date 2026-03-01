"""Generate synthetic IO model fixtures for testing and fallback (D-5 Task 3).

Generates synthetic test fixtures in data/synthetic/:
  1. saudi_io_synthetic_v1.json    -- Synthetic 20-sector Saudi IO model
  2. saudi_type1_multipliers_synthetic.json -- Synthetic Type I output multipliers
  3. saudi_employment_coefficients_synthetic.json -- Synthetic employment coefficients

IMPORTANT: These are SYNTHETIC artifacts for testing/fallback ONLY.
  - Constructed from hardcoded proportions, NOT real upstream data
  - Validated for economic consistency (spectral radius, positive VA, etc.)
  - Written to data/synthetic/ — NEVER to data/curated/

The data/curated/ directory is reserved for real upstream data (KAPSARC, ILO, WDI).
This script must NEVER write to data/curated/.

Usage:
    python -m scripts.generate_synthetic_fixtures

Idempotent: safe to re-run.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from scipy import linalg as scipy_linalg

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.data.io_loader import validate_model

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SYNTHETIC_DIR = PROJECT_ROOT / "data" / "synthetic"

# ISIC Rev 4 sections A-T (20 sectors)
ISIC_SECTIONS = [
    "A", "B", "C", "D", "E", "F", "G", "H", "I", "J",
    "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T",
]

SECTOR_NAMES = {
    "A": "Agriculture, forestry and fishing",
    "B": "Mining and quarrying (incl. oil/gas)",
    "C": "Manufacturing",
    "D": "Electricity, gas, steam and air conditioning",
    "E": "Water supply, sewerage, waste management",
    "F": "Construction",
    "G": "Wholesale and retail trade",
    "H": "Transportation and storage",
    "I": "Accommodation and food service",
    "J": "Information and communication",
    "K": "Financial and insurance activities",
    "L": "Real estate activities",
    "M": "Professional, scientific and technical",
    "N": "Administrative and support services",
    "O": "Public administration and defence",
    "P": "Education",
    "Q": "Human health and social work",
    "R": "Arts, entertainment and recreation",
    "S": "Other service activities",
    "T": "Activities of households as employers",
}


# ---------------------------------------------------------------------------
# Phase A-1: Build the IO model
# ---------------------------------------------------------------------------


def _build_gross_output_vector() -> np.ndarray:
    """Build a realistic Saudi gross output vector (SAR millions, 2018).

    Total gross output ~ 2.5 trillion SAR.
    Sector B (Mining/Oil) is dominant at ~700B.
    """
    # SAR millions — approximate 2018 Saudi gross output by ISIC section
    x_dict = {
        "A": 45_000.0,      # Agriculture
        "B": 700_000.0,     # Mining/Oil — dominant
        "C": 400_000.0,     # Manufacturing (refining, petrochem)
        "D": 35_000.0,      # Electricity/gas
        "E": 20_000.0,      # Water/waste
        "F": 200_000.0,     # Construction — large
        "G": 180_000.0,     # Wholesale/retail
        "H": 120_000.0,     # Transport
        "I": 50_000.0,      # Accommodation/food
        "J": 80_000.0,      # ICT
        "K": 95_000.0,      # Finance
        "L": 110_000.0,     # Real estate
        "M": 55_000.0,      # Professional services
        "N": 40_000.0,      # Admin/support
        "O": 150_000.0,     # Public admin
        "P": 85_000.0,      # Education
        "Q": 60_000.0,      # Health
        "R": 15_000.0,      # Arts/recreation
        "S": 25_000.0,      # Other services
        "T": 10_000.0,      # Households as employers
    }
    return np.array([x_dict[s] for s in ISIC_SECTIONS], dtype=np.float64)


def _build_technical_coefficient_matrix(x: np.ndarray) -> np.ndarray:
    """Build a realistic 20x20 technical coefficient matrix A.

    A[i][j] = proportion of sector j's gross output purchased from sector i.
    Each column sums to 0.30-0.65 (intermediate input ratio), ensuring
    positive value-added for every sector.

    The row constraint (total intermediate sales <= gross output) is enforced
    by scaling down coefficients for small sectors that sell to large ones.

    Key economic relationships for Saudi Arabia:
    - Oil (B) feeds heavily into Manufacturing (C) and Transport (H)
    - Construction (F) purchases from Manufacturing (C) and Mining (B)
    - Services sectors have lower intermediate input ratios
    """
    n = 20
    A = np.zeros((n, n), dtype=np.float64)

    # Helper: map sector code to index
    idx = {s: i for i, s in enumerate(ISIC_SECTIONS)}

    # --- Define column profiles (what each sector buys) ---
    # Format: {buying_sector: {selling_sector: coefficient, ...}}
    # Each column should sum to 0.30 - 0.65

    profiles: dict[str, dict[str, float]] = {
        "A": {  # Agriculture buys from:
            "A": 0.08, "B": 0.02, "C": 0.10, "D": 0.02, "E": 0.02,
            "G": 0.05, "H": 0.03, "K": 0.02, "N": 0.02,
        },  # sum ~ 0.36
        "B": {  # Mining/Oil buys from:
            "B": 0.05, "C": 0.04, "D": 0.01, "F": 0.03, "G": 0.02,
            "H": 0.02, "J": 0.01, "K": 0.02, "M": 0.02, "N": 0.01,
        },  # sum ~ 0.23
        "C": {  # Manufacturing buys from:
            "A": 0.02, "B": 0.15, "C": 0.12, "D": 0.01, "E": 0.01,
            "F": 0.02, "G": 0.04, "H": 0.04, "J": 0.01, "K": 0.02,
            "M": 0.02, "N": 0.01,
        },  # sum ~ 0.47
        "D": {  # Electricity/gas buys from:
            "B": 0.20, "C": 0.05, "D": 0.05, "F": 0.03, "H": 0.02,
            "K": 0.02, "M": 0.02, "N": 0.02,
        },  # sum ~ 0.41
        "E": {  # Water/waste buys from:
            "C": 0.08, "D": 0.06, "E": 0.05, "F": 0.05, "G": 0.03,
            "H": 0.02, "K": 0.02, "M": 0.02, "N": 0.03,
        },  # sum ~ 0.36
        "F": {  # Construction buys from:
            "B": 0.03, "C": 0.18, "D": 0.01, "E": 0.005, "F": 0.08,
            "G": 0.05, "H": 0.04, "K": 0.02, "L": 0.02, "M": 0.02,
            "N": 0.03,
        },  # sum ~ 0.485
        "G": {  # Wholesale/retail buys from:
            "C": 0.04, "D": 0.01, "G": 0.06, "H": 0.05, "I": 0.01,
            "J": 0.02, "K": 0.03, "L": 0.04, "M": 0.02, "N": 0.02,
        },  # sum ~ 0.30
        "H": {  # Transport buys from:
            "B": 0.08, "C": 0.04, "D": 0.01, "F": 0.02, "G": 0.02,
            "H": 0.05, "J": 0.02, "K": 0.02, "M": 0.02, "N": 0.02,
        },  # sum ~ 0.30
        "I": {  # Accommodation/food buys from:
            "A": 0.08, "C": 0.06, "D": 0.02, "E": 0.01, "G": 0.06,
            "H": 0.02, "I": 0.03, "J": 0.02, "K": 0.02, "L": 0.04,
            "N": 0.03, "S": 0.02,
        },  # sum ~ 0.41
        "J": {  # ICT buys from:
            "C": 0.03, "D": 0.01, "G": 0.02, "H": 0.02, "J": 0.08,
            "K": 0.03, "L": 0.03, "M": 0.05, "N": 0.03,
        },  # sum ~ 0.30
        "K": {  # Finance buys from:
            "D": 0.01, "G": 0.02, "H": 0.01, "J": 0.04, "K": 0.05,
            "L": 0.05, "M": 0.04, "N": 0.03, "S": 0.01,
        },  # sum ~ 0.26
        "L": {  # Real estate buys from:
            "D": 0.01, "E": 0.01, "F": 0.06, "G": 0.02, "K": 0.03,
            "L": 0.05, "M": 0.02, "N": 0.03,
        },  # sum ~ 0.23
        "M": {  # Professional services buys from:
            "C": 0.02, "D": 0.01, "G": 0.02, "H": 0.02, "J": 0.06,
            "K": 0.03, "L": 0.03, "M": 0.06, "N": 0.04, "S": 0.01,
        },  # sum ~ 0.30
        "N": {  # Admin/support buys from:
            "C": 0.02, "D": 0.01, "G": 0.03, "H": 0.03, "J": 0.03,
            "K": 0.03, "L": 0.03, "M": 0.03, "N": 0.06, "S": 0.02,
        },  # sum ~ 0.29
        "O": {  # Public admin buys from:
            "C": 0.02, "D": 0.01, "F": 0.04, "G": 0.02, "H": 0.02,
            "J": 0.03, "K": 0.02, "L": 0.02, "M": 0.02, "N": 0.02,
            "P": 0.01, "Q": 0.01,
        },  # sum ~ 0.24
        "P": {  # Education buys from:
            "C": 0.02, "D": 0.01, "G": 0.02, "H": 0.01, "J": 0.03,
            "K": 0.02, "L": 0.03, "M": 0.02, "N": 0.02, "S": 0.01,
        },  # sum ~ 0.19 (education is labor-intensive)
        "Q": {  # Health buys from:
            "C": 0.08, "D": 0.02, "G": 0.03, "H": 0.02, "J": 0.02,
            "K": 0.02, "L": 0.02, "M": 0.03, "N": 0.02,
        },  # sum ~ 0.26
        "R": {  # Arts/recreation buys from:
            "C": 0.03, "D": 0.01, "G": 0.04, "H": 0.03, "I": 0.02,
            "J": 0.03, "K": 0.02, "L": 0.03, "M": 0.02, "N": 0.03,
            "S": 0.02,
        },  # sum ~ 0.28
        "S": {  # Other services buys from:
            "C": 0.03, "D": 0.01, "G": 0.04, "H": 0.02, "J": 0.02,
            "K": 0.02, "L": 0.02, "M": 0.03, "N": 0.04, "S": 0.04,
        },  # sum ~ 0.27
        "T": {  # Households as employers buys from:
            "G": 0.03, "I": 0.02, "S": 0.02,
        },  # sum ~ 0.07 (mostly labor)
    }

    # Fill the A matrix from profiles
    for buyer, purchases in profiles.items():
        j = idx[buyer]
        for seller, coeff in purchases.items():
            i = idx[seller]
            A[i, j] = coeff

    # --- Row constraint enforcement ---
    # For each sector i, total intermediate sales = sum_j A[i,j]*x[j]
    # This must be <= x[i] (leaving room for final demand and value-added).
    # We allow intermediate sales up to 70% of gross output.
    max_intermediate_sales_ratio = 0.70
    for i in range(n):
        row_sales = sum(A[i, j] * x[j] for j in range(n))
        max_sales = max_intermediate_sales_ratio * x[i]
        if row_sales > max_sales:
            # Scale down this row proportionally
            scale = max_sales / row_sales
            for j in range(n):
                A[i, j] *= scale

    return A


def build_io_model() -> dict:
    """Build the complete 20-sector Saudi IO model artifact.

    Returns a dict ready to be serialized to JSON.
    """
    x = _build_gross_output_vector()
    A = _build_technical_coefficient_matrix(x)

    # Compute Z = A * diag(x)
    Z = A * x[np.newaxis, :]

    # Validate: every sector's gross output must cover intermediate deliveries
    row_sums = Z.sum(axis=1)
    for i, code in enumerate(ISIC_SECTIONS):
        if row_sums[i] > x[i]:
            raise ValueError(
                f"Sector {code}: intermediate deliveries ({row_sums[i]:.0f}) "
                f"exceed gross output ({x[i]:.0f})"
            )

    # Validate using the engine's own validator
    result = validate_model(Z, x, ISIC_SECTIONS)
    if not result.is_valid:
        raise ValueError(
            f"IO model validation failed:\n" +
            "\n".join(f"  - {e}" for e in result.errors)
        )

    print(f"  Spectral radius: {result.spectral_radius:.6f}")
    print(f"  All VA positive: {result.all_va_positive}")
    print(f"  Total output: {result.total_output:,.0f} SAR M")
    print(f"  Total value added: {result.total_value_added:,.0f} SAR M")

    return {
        "model_id": "saudi-io-synthetic-2018",
        "base_year": 2018,
        "source": "synthetic_generated",
        "denomination": "SAR_MILLIONS",
        "classification": "ISIC_REV4_SECTION",
        "sector_count": 20,
        "sector_codes": ISIC_SECTIONS,
        "sector_names": SECTOR_NAMES,
        "Z": Z.tolist(),
        "x": x.tolist(),
    }


# ---------------------------------------------------------------------------
# Phase A-2: Build benchmark multipliers
# ---------------------------------------------------------------------------


def build_benchmark_multipliers(io_data: dict) -> dict:
    """Compute Type I output multipliers from the IO model.

    multiplier_j = sum(B[:, j]) where B = (I - A)^{-1}

    Returns dict in the format expected by BenchmarkValidator.load_benchmark_from_file():
    {"sectors": [{"sector_code": "A", "output_multiplier": 1.85}, ...]}
    """
    Z = np.array(io_data["Z"], dtype=np.float64)
    x = np.array(io_data["x"], dtype=np.float64)
    sector_codes = io_data["sector_codes"]
    n = len(x)

    # A = Z * diag(1/x)
    A = Z / x[np.newaxis, :]

    # Leontief inverse B = (I - A)^{-1}
    I_minus_A = np.eye(n) - A
    B = scipy_linalg.solve(I_minus_A, np.eye(n))

    # Type I output multiplier = column sum of B
    multipliers = B.sum(axis=0)

    sectors = []
    for i, code in enumerate(sector_codes):
        m = round(float(multipliers[i]), 4)
        sectors.append({
            "sector_code": code,
            "output_multiplier": m,
        })
        print(f"    {code}: {m:.4f}")

    # Sanity check: all multipliers must be >= 1.0
    if any(s["output_multiplier"] < 1.0 for s in sectors):
        bad = [s for s in sectors if s["output_multiplier"] < 1.0]
        raise ValueError(f"Multipliers < 1.0 found: {bad}")

    return {
        "source": "synthetic_generated",
        "base_year": 2018,
        "method": "Type I output multiplier = column sum of Leontief inverse (I-A)^{-1}",
        "sectors": sectors,
    }


# ---------------------------------------------------------------------------
# Phase A-3: Build employment coefficients
# ---------------------------------------------------------------------------


def build_employment_artifact(io_model_path: Path, output_dir: Path) -> Path:
    """Build synthetic employment coefficients.

    Uses build_employment_coefficients() from src.data.workforce —
    does NOT hand-roll the JSON (Correction 6).
    """
    from src.data.workforce.build_employment_coefficients import (
        build_employment_coefficients,
        save_employment_coefficients,
    )

    coeff_set = build_employment_coefficients(
        io_model_path=str(io_model_path),
        year=2019,
    )

    output_path = save_employment_coefficients(
        coeff_set,
        output_dir=str(output_dir),
    )

    print(f"  Employment coefficients: {len(coeff_set.coefficients)} sectors")
    return output_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Generate synthetic fixtures in data/synthetic/.

    SAFETY: This script NEVER writes to data/curated/.
    All output goes to data/synthetic/ with clearly synthetic filenames.
    """
    SYNTHETIC_DIR.mkdir(parents=True, exist_ok=True)

    # Phase 1: IO Model
    print("Phase 1: Building synthetic IO model...")
    io_data = build_io_model()
    io_path = SYNTHETIC_DIR / "saudi_io_synthetic_v1.json"
    io_path.write_text(
        json.dumps(io_data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"  Written: {io_path}")

    # Phase 2: Benchmark multipliers
    print("\nPhase 2: Computing synthetic benchmark multipliers...")
    benchmark = build_benchmark_multipliers(io_data)
    benchmark_path = SYNTHETIC_DIR / "saudi_type1_multipliers_synthetic.json"
    benchmark_path.write_text(
        json.dumps(benchmark, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"  Written: {benchmark_path}")

    # Phase 3: Employment coefficients
    print("\nPhase 3: Building synthetic employment coefficients...")
    emp_path = build_employment_artifact(io_path, output_dir=SYNTHETIC_DIR)
    print(f"  Written: {emp_path}")

    print("\nAll synthetic fixtures generated successfully.")
    print(f"Output directory: {SYNTHETIC_DIR}")


if __name__ == "__main__":
    main()
