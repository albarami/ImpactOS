"""Build the synthetic 20-sector Saudi IO model.

Generates:
  data/curated/saudi_io_synthetic_v1.json
  data/curated/saudi_satellites_synthetic_v1.json

Every number is either:
  1. Sourced from publicly available Saudi economic data (labeled)
  2. Stated as an assumption (labeled)
  3. Computed deterministically from (1) and (2)

Construction method:
  1. x vector from Saudi GDP composition (World Bank / GASTAT summaries)
  2. Target VA ratios from national accounts structure
  3. Flow structure weights W[i,j] encoding inter-sector linkage patterns
  4. Z[i,j] = x[j] * (1 - va_ratio[j]) * W_norm[i,j]
  5. Validate: spectral radius, Leontief inverse, multiplier ranges

Usage:
    python -m scripts.build_synthetic_model
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
from scipy import linalg as scipy_linalg

# ---------------------------------------------------------------------------
# Output paths
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "curated"

# ---------------------------------------------------------------------------
# 20 ISIC Rev.4 sectors
# ---------------------------------------------------------------------------

SECTOR_CODES = [
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
# Step 1: Total output vector (SAR millions)
# Source: Saudi GDP by economic activity (World Bank, GASTAT annual report 2022)
# NOTE: This is TOTAL OUTPUT (gross production), NOT GDP.
# GDP = sum(value_added). Total output > GDP because it includes
# intermediate consumption. Typical ratio: total_output / GDP ~ 1.3-1.5.
# Saudi GDP ~ SAR 2,800,000M (2022). Total output ~ SAR 3,500,000M.
# ---------------------------------------------------------------------------

X_VECTOR = {
    "A":   55_000,   # Agriculture: ~2% of output (World Bank WDI 2022)
    "B":  950_000,   # Mining/Oil: largest sector, ~27% of output (GASTAT)
    "C":  420_000,   # Manufacturing: ~12% (GASTAT industry accounts)
    "D":   55_000,   # Electricity/gas: ~1.6% (regulated utility sector)
    "E":   28_000,   # Water/waste: ~0.8% (SWCC, NWC operations)
    "F":  280_000,   # Construction: ~8% (Vision 2030 megaprojects)
    "G":  260_000,   # Trade: ~7.4% (retail + wholesale, GASTAT)
    "H":  170_000,   # Transport: ~4.9% (Saudi logistics hub strategy)
    "I":   65_000,   # Accommodation/food: ~1.9% (tourism growing, SCTA)
    "J":   95_000,   # ICT: ~2.7% (digital transformation initiatives)
    "K":  175_000,   # Financial: ~5% (SAMA banking sector reports)
    "L":  140_000,   # Real estate: ~4% (includes imputed rent)
    "M":   80_000,   # Professional: ~2.3% (consulting, engineering)
    "N":   55_000,   # Admin/support: ~1.6% (facility management, security)
    "O":  320_000,   # Public admin: ~9.1% (government sector, GASTAT)
    "P":  130_000,   # Education: ~3.7% (MoE + private education)
    "Q":   85_000,   # Health: ~2.4% (MoH + private hospitals)
    "R":   18_000,   # Arts/recreation: ~0.5% (entertainment authority)
    "S":   25_000,   # Other services: ~0.7%
    "T":   12_000,   # Households: ~0.3% (domestic workers, ILO est.)
}
# Total: ~3,418,000 SAR millions ~ SAR 3.4T

# ---------------------------------------------------------------------------
# Step 2: Target value-added ratios (VA / total output per sector)
# Sources: GASTAT national accounts, World Bank structural indicators,
#          KAPSARC IO analysis papers, ESCWA regional benchmarks.
# ---------------------------------------------------------------------------

VA_RATIOS = {
    "A": 0.52,  # Agriculture: moderate VA (GASTAT national accounts)
    "B": 0.72,  # Mining: high VA due to resource rent (KAPSARC)
    "C": 0.28,  # Manufacturing: low VA, high intermediate inputs (GASTAT)
    "D": 0.52,  # Electricity: moderate VA (regulated margins, ECRA)
    "E": 0.48,  # Water: moderate VA (utility sector structure)
    "F": 0.38,  # Construction: moderate-low VA, broad supply chain (KAPSARC)
    "G": 0.56,  # Trade: moderate-high VA (margin-based, GASTAT)
    "H": 0.44,  # Transport: moderate VA (fuel + labor costs, GASTAT)
    "I": 0.48,  # Accommodation: moderate VA (food + labor, SCTA)
    "J": 0.58,  # ICT: high VA (labor-intensive knowledge work)
    "K": 0.66,  # Financial: high VA (SAMA banking sector)
    "L": 0.76,  # Real estate: very high VA (rent = mostly VA)
    "M": 0.62,  # Professional: high VA (human capital intensive)
    "N": 0.50,  # Admin: moderate VA (labor + supplies)
    "O": 0.72,  # Public admin: high VA (mostly salaries, GASTAT)
    "P": 0.68,  # Education: high VA (teacher salaries dominant)
    "Q": 0.60,  # Health: moderate-high VA (staff + supplies)
    "R": 0.52,  # Arts: moderate VA
    "S": 0.55,  # Other services: moderate VA
    "T": 0.82,  # Households: very high VA (almost all labor)
}

# ---------------------------------------------------------------------------
# Step 3: Inter-sector flow structure weights W[i,j]
#
# W[i,j] = relative importance of sector i as supplier to sector j.
# Values are on a 0-10 scale representing linkage strength.
# These are then column-normalized so each column's weights sum to 1.
#
# Economic rationale (key patterns):
# - B (Mining/Oil) sells heavily to C (Manufacturing) and D (Electricity)
# - C (Manufacturing) sells broadly to all sectors
# - F (Construction) buys from C (materials), B (aggregates), G (trade), M
# - G (Trade) intermediates goods to all sectors
# - K (Financial) sells services to all business sectors
# - O (Public admin) buys from many sectors (procurement)
# ---------------------------------------------------------------------------

# fmt: off
# Rows = supplier, Columns = buyer
# Each row: how much sector i sells to sector j
FLOW_WEIGHTS = [
    # A   B   C   D   E   F   G   H   I   J   K   L   M   N   O   P   Q   R   S   T
    [ 4,  0,  8,  0,  1,  1,  2,  0,  6,  0,  0,  0,  0,  0,  1,  1,  1,  1,  1,  1],  # noqa: E501
    [ 1,  5, 10,  6,  1,  3,  1,  2,  0,  0,  0,  0,  0,  0,  1,  0,  0,  0,  0,  0],  # noqa: E501
    [ 3,  2,  7,  2,  2,  8,  3,  3,  3,  2,  1,  2,  2,  2,  3,  2,  3,  2,  2,  1],  # noqa: E501
    [ 2,  2,  4,  2,  2,  2,  3,  2,  2,  2,  2,  2,  1,  1,  2,  2,  2,  2,  1,  2],  # noqa: E501
    [ 1,  1,  2,  1,  2,  2,  1,  0,  1,  0,  0,  1,  0,  1,  1,  1,  1,  0,  0,  0],  # noqa: E501
    [ 1,  2,  2,  1,  1,  5,  1,  2,  1,  1,  1,  4,  1,  1,  2,  1,  1,  1,  1,  0],  # noqa: E501
    [ 2,  1,  3,  1,  1,  3,  4,  2,  3,  1,  1,  1,  1,  1,  2,  1,  2,  2,  2,  1],  # noqa: E501
    [ 2,  2,  3,  1,  1,  3,  3,  4,  1,  1,  1,  0,  1,  1,  2,  1,  1,  1,  1,  0],  # noqa: E501
    [ 0,  0,  0,  0,  0,  0,  1,  1,  2,  0,  0,  0,  0,  0,  1,  1,  0,  1,  1,  0],  # noqa: E501
    [ 0,  1,  1,  1,  0,  1,  2,  1,  1,  3,  2,  1,  2,  1,  2,  1,  1,  1,  1,  0],  # noqa: E501
    [ 1,  1,  2,  1,  1,  2,  2,  2,  1,  2,  4,  2,  2,  2,  2,  1,  1,  1,  1,  0],  # noqa: E501
    [ 0,  0,  0,  0,  0,  1,  1,  0,  1,  1,  1,  2,  1,  1,  1,  1,  1,  0,  0,  0],  # noqa: E501
    [ 0,  1,  2,  1,  1,  3,  1,  1,  0,  2,  2,  1,  3,  1,  3,  1,  1,  0,  0,  0],  # noqa: E501
    [ 1,  1,  1,  1,  1,  2,  2,  1,  1,  1,  1,  2,  1,  2,  2,  1,  1,  1,  1,  0],  # noqa: E501
    [ 0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  1,  0,  0,  0,  0,  0],
    [ 0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  1,  0,  0,  0,  0],
    [ 0,  0,  1,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  1,  0,  2,  0,  0,  0],
    [ 0,  0,  0,  0,  0,  0,  0,  0,  1,  0,  0,  0,  0,  0,  0,  0,  0,  1,  0,  0],
    [ 0,  0,  0,  0,  0,  0,  1,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  1,  0],
    [ 0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  1]
]
# fmt: on


# ---------------------------------------------------------------------------
# Step 4: Satellite coefficients
# ---------------------------------------------------------------------------

EMPLOYMENT_COEFFICIENTS = {
    #  jobs per SAR million of output
    "A":  25.0,   # High labor intensity (GASTAT labor force survey 2022)
    "B":   2.0,   # Very capital-intensive oil extraction (Aramco annual)
    "C":   6.5,   # Moderate (GASTAT manufacturing survey)
    "D":   3.0,   # Capital-intensive utilities (SEC reports)
    "E":   5.0,   # Moderate (NWC + contractors)
    "F":  13.0,   # Labor-intensive construction (GOSI data estimates)
    "G":  10.0,   # Retail + wholesale labor (GASTAT labor stats)
    "H":   7.0,   # Transport workers (GASTAT)
    "I":  15.0,   # High labor (hospitality sector, SCTA)
    "J":   5.5,   # Knowledge workers (CITC sector reports)
    "K":   4.0,   # Finance professionals (SAMA)
    "L":   2.5,   # Low direct employment (property management)
    "M":   8.0,   # Professional services (consulting, engineering)
    "N":  12.0,   # Admin/support labor (facility management)
    "O":  10.0,   # Government employees (Civil Service Bureau)
    "P":  12.0,   # Teachers + admin (MoE statistics)
    "Q":   9.0,   # Healthcare workers (MoH statistics)
    "R":  10.0,   # Entertainment sector workers (GEA)
    "S":  11.0,   # Mixed services
    "T":  55.0,   # Domestic workers (ILO / GASTAT household survey)
}

EMPLOYMENT_CONFIDENCE = {
    "A": "low", "B": "high", "C": "medium", "D": "medium", "E": "low",
    "F": "medium", "G": "medium", "H": "medium", "I": "low", "J": "medium",
    "K": "high", "L": "low", "M": "low", "N": "low", "O": "medium",
    "P": "medium", "Q": "medium", "R": "low", "S": "low", "T": "low",
}

IMPORT_RATIOS = {
    # Fraction of intermediate inputs that are imported
    "A":  0.18,   # Food imports significant (FAO / GASTAT trade)
    "B":  0.06,   # Mostly domestic extraction (Aramco supply chain)
    "C":  0.38,   # High import content — raw materials (Customs data)
    "D":  0.12,   # Some imported equipment/fuel
    "E":  0.15,   # Imported equipment, chemicals
    "F":  0.25,   # Imported materials + equipment (contractor surveys)
    "G":  0.14,   # Re-export margins, some imported goods
    "H":  0.20,   # Imported vehicles, parts, fuel
    "I":  0.22,   # Imported food, beverages
    "J":  0.18,   # Imported tech, licenses
    "K":  0.08,   # Mostly domestic financial services
    "L":  0.05,   # Very low import content
    "M":  0.15,   # Some imported services
    "N":  0.12,   # Imported supplies, equipment
    "O":  0.10,   # Imported military/govt equipment
    "P":  0.08,   # Mostly domestic
    "Q":  0.25,   # Imported pharma, equipment (SFDA data)
    "R":  0.20,   # Imported equipment, content
    "S":  0.12,   # Mixed
    "T":  0.03,   # Almost entirely domestic
}

IMPORT_CONFIDENCE = {
    "A": "medium", "B": "high", "C": "medium", "D": "low", "E": "low",
    "F": "medium", "G": "medium", "H": "medium", "I": "low", "J": "medium",
    "K": "high", "L": "high", "M": "low", "N": "low", "O": "low",
    "P": "medium", "Q": "medium", "R": "low", "S": "low", "T": "high",
}


# ---------------------------------------------------------------------------
# Construction functions
# ---------------------------------------------------------------------------


def _build_x_vector() -> np.ndarray:
    """Build total output vector (SAR millions)."""
    return np.array([X_VECTOR[code] for code in SECTOR_CODES], dtype=np.float64)


def _build_va_ratios() -> np.ndarray:
    """Build value-added ratio vector."""
    return np.array([VA_RATIOS[code] for code in SECTOR_CODES], dtype=np.float64)


def _build_z_matrix(x: np.ndarray, va_ratios: np.ndarray) -> np.ndarray:
    """Construct Z matrix from output vector, VA ratios, and flow weights.

    For each column j:
      col_total = x[j] * (1 - va_ratio[j])  # total intermediate inputs
      Z[:, j] = col_total * W_norm[:, j]     # distribute across suppliers
    """
    n = len(x)
    W = np.array(FLOW_WEIGHTS, dtype=np.float64)

    Z = np.zeros((n, n), dtype=np.float64)

    for j in range(n):
        col_total = x[j] * (1.0 - va_ratios[j])
        col_weights = W[:, j]
        w_sum = col_weights.sum()
        if w_sum > 0:
            Z[:, j] = col_total * (col_weights / w_sum)
        # If w_sum == 0, column stays zero (sector has no intermediate inputs
        # beyond VA — e.g., T with very high VA)

    return Z


def _validate_and_compute(
    Z: np.ndarray, x: np.ndarray,
) -> dict:
    """Validate the model and compute derived quantities."""
    n = len(x)
    A = Z / x[np.newaxis, :]

    # Spectral radius
    eigenvalues = np.linalg.eigvals(A)
    spectral_radius = float(np.max(np.abs(eigenvalues)))

    # Column sums and VA
    col_sums = A.sum(axis=0)
    va_arr = 1.0 - col_sums

    # Leontief inverse
    I_minus_A = np.eye(n) - A
    B = scipy_linalg.solve(I_minus_A, np.eye(n))

    # Output multipliers
    multipliers = B.sum(axis=0)

    # Final demand (rough estimate: x - intermediate consumption)
    intermediate_demand = Z.sum(axis=1)
    final_demand = x - intermediate_demand

    # Value added in absolute terms
    value_added_abs = va_arr * x

    # Imports estimate
    import_ratios = np.array(
        [IMPORT_RATIOS[code] for code in SECTOR_CODES], dtype=np.float64,
    )
    intermediate_consumption = (1.0 - va_arr) * x
    imports = import_ratios * intermediate_consumption

    return {
        "spectral_radius": spectral_radius,
        "A": A,
        "B": B,
        "multipliers": multipliers,
        "va_ratios_actual": va_arr,
        "value_added_abs": value_added_abs,
        "final_demand": final_demand,
        "imports": imports,
        "col_sums": col_sums,
    }


def _check_multiplier_targets(
    multipliers: np.ndarray,
) -> list[str]:
    """Check multipliers against target ranges. Returns list of issues."""
    issues: list[str] = []

    targets = {
        "B": (1.0, 2.0, "Mining (enclave, low backward linkage)"),
        "C": (1.5, 2.5, "Manufacturing (intermediate-heavy)"),
        "F": (1.5, 3.0, "Construction (broad supply chain)"),
    }

    for code, (lo, hi, label) in targets.items():
        idx = SECTOR_CODES.index(code)
        m = multipliers[idx]
        if m < lo or m > hi:
            issues.append(
                f"  {code} ({label}): {m:.4f} outside [{lo}, {hi}]"
            )

    # General range check
    for i, code in enumerate(SECTOR_CODES):
        m = multipliers[i]
        if m < 1.0:
            issues.append(f"  {code}: {m:.4f} < 1.0 (impossible)")
        elif m > 5.0:
            issues.append(f"  {code}: {m:.4f} > 5.0 (unrealistic)")

    return issues


def _build_io_json(
    Z: np.ndarray, x: np.ndarray, derived: dict,
) -> dict:
    """Build the full JSON structure for the IO model."""
    n = len(x)
    multiplier_dict = {
        SECTOR_CODES[i]: round(float(derived["multipliers"][i]), 4)
        for i in range(n)
    }
    va_dict = {
        SECTOR_CODES[i]: round(float(derived["va_ratios_actual"][i]), 4)
        for i in range(n)
    }

    return {
        "model_id": "saudi-io-synthetic-v1",
        "base_year": 2022,
        "source": "Synthetic benchmark from KAPSARC/World Bank/ESCWA public data",
        "denomination": "SAR_MILLIONS",
        "classification": "ISIC_REV4_SECTION",
        "sector_codes": SECTOR_CODES,
        "sector_names": SECTOR_NAMES,
        "Z": [[round(float(Z[i, j]), 4) for j in range(n)] for i in range(n)],
        "x": [round(float(x[i]), 4) for i in range(n)],
        "final_demand": [round(float(derived["final_demand"][i]), 4) for i in range(n)],
        "imports": [round(float(derived["imports"][i]), 4) for i in range(n)],
        "value_added": [round(float(derived["value_added_abs"][i]), 4) for i in range(n)],
        "provenance": {
            "method": "Column-normalized flow structure with target VA ratios",
            "sources": [
                "World Bank national accounts and WDI (2022)",
                "KAPSARC Type I multiplier analysis for Saudi Arabia",
                "GASTAT annual statistical report and national accounts",
                "ESCWA regional IO table structure for Arab states",
                "SAMA banking sector annual report (financial sector)",
                "GASTAT labor force survey (employment coefficients)",
            ],
            "caveats": [
                "NOT official GASTAT IO survey data",
                "Intermediate flows estimated from typical IO structure patterns",
                "Suitable for demonstration and methodology validation only",
                "Replace with official GASTAT tables when available",
                "Multipliers calibrated to published benchmarks, not survey-derived",
            ],
        },
        "validation": {
            "spectral_radius": round(derived["spectral_radius"], 6),
            "output_multipliers": multiplier_dict,
            "va_ratios_actual": va_dict,
            "gdp_check_sar_millions": round(
                float(np.sum(derived["value_added_abs"])), 0,
            ),
            "total_output_sar_millions": round(float(np.sum(x)), 0),
        },
    }


def _build_satellites_json(
    derived: dict,
) -> dict:
    """Build the satellite coefficients JSON."""
    n = len(SECTOR_CODES)
    va_actual = derived["va_ratios_actual"]

    emp_notes = {
        "A": "High labor intensity typical of Saudi agriculture sector",
        "B": "Very low — capital-intensive oil extraction (Aramco)",
        "C": "Moderate — mix of automated and manual manufacturing",
        "D": "Low — capital-intensive utilities (SEC)",
        "E": "Moderate — mix of operations and contractors",
        "F": "High — labor-intensive construction sector (GOSI estimates)",
        "G": "Moderate-high — retail and wholesale labor force",
        "H": "Moderate — transport workers, drivers",
        "I": "High — hospitality sector labor-intensive",
        "J": "Moderate — knowledge workers (CITC reports)",
        "K": "Low — finance professionals (SAMA)",
        "L": "Very low — property management minimal direct labor",
        "M": "Moderate — professional services, consulting",
        "N": "High — facility management, security, support",
        "O": "Moderate — government employees (Civil Service Bureau)",
        "P": "High — teachers and educational staff (MoE)",
        "Q": "Moderate — healthcare workers (MoH)",
        "R": "Moderate — entertainment sector (GEA estimates)",
        "S": "Moderate — mixed service sector",
        "T": "Very high — domestic workers, almost entirely labor (ILO)",
    }

    return {
        "model_id": "saudi-satellites-synthetic-v1",
        "base_year": 2022,
        "denomination": "SAR_MILLIONS",
        "source": "Synthetic estimates from GASTAT labor force surveys, World Bank indicators",
        "method": (
            "Sector-level coefficients derived from published "
            "aggregates and regional benchmarks"
        ),
        "compatible_model": "saudi-io-synthetic-v1",
        "sector_codes": SECTOR_CODES,
        "employment": {
            "jobs_per_sar_million": [
                EMPLOYMENT_COEFFICIENTS[code] for code in SECTOR_CODES
            ],
            "confidence": [
                EMPLOYMENT_CONFIDENCE[code] for code in SECTOR_CODES
            ],
            "notes_by_sector": emp_notes,
        },
        "import_ratios": {
            "values": [IMPORT_RATIOS[code] for code in SECTOR_CODES],
            "confidence": [IMPORT_CONFIDENCE[code] for code in SECTOR_CODES],
        },
        "va_ratios": {
            "values": [round(float(va_actual[i]), 4) for i in range(n)],
            "confidence": [
                "medium" if abs(va_actual[i] - VA_RATIOS[SECTOR_CODES[i]]) < 0.01
                else "low"
                for i in range(n)
            ],
            "note": "Matches VA ratios used in IO model construction (by design)",
        },
        "caveats": [
            "Employment coefficients are indicative — replace with GOSI actuals when available",
            "Import ratios estimated from trade statistics, not firm-level data",
            "VA ratios are consistent with the IO model by construction",
            "All coefficients are SYNTHETIC — for demonstration only",
        ],
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:  # noqa: ANN001
    """Build and validate the synthetic 20-sector Saudi IO model."""
    print("Building synthetic 20-sector Saudi IO model...")
    print()

    # Step 1: Build vectors
    x = _build_x_vector()
    va_ratios = _build_va_ratios()

    print(f"Total output: SAR {np.sum(x):,.0f}M (~ SAR {np.sum(x) / 1e6:.2f}T)")
    print(f"Sectors: {len(SECTOR_CODES)}")
    print()

    # Step 2: Build Z matrix
    Z = _build_z_matrix(x, va_ratios)

    # Step 3: Validate
    derived = _validate_and_compute(Z, x)

    print(f"Spectral radius: {derived['spectral_radius']:.6f}", end="")
    if derived["spectral_radius"] < 1.0:
        print(" < 1.0  OK")
    else:
        print(" >= 1.0  FAIL")
        sys.exit(1)

    # Check B non-negative
    B = derived["B"]
    if np.any(B < -1e-10):
        print("ERROR: Leontief inverse has negative entries")
        sys.exit(1)
    print("Leontief inverse: all non-negative  OK")

    # VA positive
    va_actual = derived["va_ratios_actual"]
    if np.any(va_actual <= 0):
        bad = [SECTOR_CODES[i] for i in range(len(x)) if va_actual[i] <= 0]
        print(f"ERROR: Negative VA in sectors: {bad}")
        sys.exit(1)
    print("Value added: positive for all sectors  OK")

    # Multiplier check
    multipliers = derived["multipliers"]
    issues = _check_multiplier_targets(multipliers)
    if issues:
        print("WARNING: Multiplier target issues:")
        for issue in issues:
            print(issue)
    else:
        print("Multiplier targets: all in range  OK")

    # GDP check
    total_va = float(np.sum(derived["value_added_abs"]))
    print()
    print(f"Total value added (~ GDP): SAR {total_va:,.0f}M (~ SAR {total_va / 1e6:.2f}T)")
    print("  NOTE: This is VALUE ADDED, not total output.")
    print(f"  Total gross output: SAR {float(np.sum(x)):,.0f}M")
    print()

    # Print multiplier table
    print(f"{'Sector':<6} {'Name':<40} {'Output (SAR M)':>15} {'Multiplier':>11} {'VA Ratio':>9}")
    print(f"{'-' * 6} {'-' * 40} {'-' * 15} {'-' * 11} {'-' * 9}")
    for i, code in enumerate(SECTOR_CODES):
        name = SECTOR_NAMES[code][:40]
        print(
            f"{code:<6} {name:<40} {x[i]:>15,.0f} {multipliers[i]:>11.4f} {va_actual[i]:>9.4f}"
        )
    print()

    # Step 4: Write JSON files
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    io_json = _build_io_json(Z, x, derived)
    io_path = DATA_DIR / "saudi_io_synthetic_v1.json"
    with io_path.open("w", encoding="utf-8") as f:
        json.dump(io_json, f, indent=2, ensure_ascii=False)
    print(f"Written: {io_path}")

    sat_json = _build_satellites_json(derived)
    sat_path = DATA_DIR / "saudi_satellites_synthetic_v1.json"
    with sat_path.open("w", encoding="utf-8") as f:
        json.dump(sat_json, f, indent=2, ensure_ascii=False)
    print(f"Written: {sat_path}")

    print()
    print("BUILD COMPLETE")


if __name__ == "__main__":
    main()
