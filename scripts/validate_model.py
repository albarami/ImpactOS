"""Standalone IO model validation script.

Loads a model from JSON and prints diagnostic output.

Usage:
    python -m scripts.validate_model data/curated/saudi_io_synthetic_v1.json
    python -m scripts.validate_model --with-satellites \\
        data/curated/saudi_satellites_synthetic_v1.json \\
        data/curated/saudi_io_synthetic_v1.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

from src.data.io_loader import load_from_json, load_satellites_from_json, validate_model


def _print_header(model_source: str, n: int, base_year: int) -> None:
    """Print model header."""
    w = 60
    print("=" * w)
    print("  ImpactOS Model Validation")
    print(f"  {model_source}")
    print("=" * w)
    print(f"  Sectors: {n}")
    print(f"  Base year: {base_year}")


def _print_validation(result: object) -> None:  # noqa: ANN001
    """Print validation summary."""
    print()
    print(f"  Spectral radius: {result.spectral_radius:.6f}", end="")
    if result.spectral_radius < 1.0:
        print("  < 1.0  PASS")
    else:
        print("  >= 1.0  FAIL")

    print(f"  Z non-negative:  {'PASS' if result.all_z_nonnegative else 'FAIL'}")
    print(f"  x positive:      {'PASS' if result.all_x_positive else 'FAIL'}")
    print(f"  VA positive:     {'PASS' if result.all_va_positive else 'FAIL'}")
    print(f"  B non-negative:  {'PASS' if result.b_nonnegative else 'FAIL'}")


def _print_multiplier_table(
    sector_codes: list[str],
    sector_names: dict[str, str],
    x: np.ndarray,
    result: object,  # noqa: ANN001
) -> None:
    """Print per-sector multiplier table."""
    print()
    print(
        f"  {'Sector':<6} {'Name':<35} {'Output (SAR M)':>14}"
        f" {'Multiplier':>11} {'VA Ratio':>9}"
    )
    print(
        f"  {'------':<6} {'-----------------------------------':<35}"
        f" {'--------------':>14} {'-----------':>11} {'---------':>9}"
    )
    for i, code in enumerate(sector_codes):
        name = sector_names.get(code, code)[:35]
        mult = result.output_multipliers.get(code, 0.0)
        va = result.va_ratios.get(code, 0.0)
        print(f"  {code:<6} {name:<35} {x[i]:>14,.0f} {mult:>11.4f} {va:>9.4f}")


def _print_gdp_check(result: object) -> None:  # noqa: ANN001
    """Print GDP vs total output check (Amendment 7)."""
    print()
    # Amendment 7: Explicit x != GDP distinction
    print(f"  Total value added (~ GDP): SAR {result.total_value_added:,.0f}M")
    print("  NOTE: This is VALUE ADDED (~ GDP), not total output")
    print(f"  Total gross output (sum x): SAR {result.total_output:,.0f}M")
    # Sanity check: Saudi GDP ~ SAR 2.5-3.5 trillion
    va_t = result.total_value_added / 1e6
    if 1.5 < va_t < 4.5:
        print(f"  Expected GDP: ~SAR 2.5-3.5T -> value added SAR {va_t:.2f}T")
    else:
        print(f"  WARNING: value added SAR {va_t:.2f}T may be outside expected range")


def _print_satellite_summary(sat_data: object) -> None:  # noqa: ANN001
    """Print satellite coefficient summary."""
    print()
    print("  Satellite Coefficients:")
    print(
        f"  {'Sector':<6} {'Jobs/SAR M':>11} {'Import %':>9}"
        f" {'VA %':>7} {'Emp Conf':>10}"
    )
    print(
        f"  {'------':<6} {'-----------':>11} {'---------':>9}"
        f" {'-------':>7} {'----------':>10}"
    )
    for i, code in enumerate(sat_data.sector_codes):
        jobs = sat_data.jobs_coeff[i]
        imp = sat_data.import_ratio[i]
        va = sat_data.va_ratio[i]
        conf = sat_data.employment_confidence[i] if i < len(sat_data.employment_confidence) else "?"
        print(
            f"  {code:<6} {jobs:>11.1f} {imp:>8.0%} {va:>6.0%} {conf:>10}"
        )


def main() -> None:
    """Run model validation."""
    parser = argparse.ArgumentParser(
        description="Validate an ImpactOS IO model JSON file",
    )
    parser.add_argument("model_path", type=Path, help="Path to IO model JSON")
    parser.add_argument(
        "--with-satellites", type=Path, default=None,
        help="Path to satellite coefficients JSON",
    )
    args = parser.parse_args()

    # Load model
    model_data = load_from_json(args.model_path)
    result = validate_model(model_data.Z, model_data.x, model_data.sector_codes)

    # Print report
    _print_header(model_data.source, len(model_data.sector_codes), model_data.base_year)
    _print_validation(result)
    _print_multiplier_table(
        model_data.sector_codes, model_data.sector_names, model_data.x, result,
    )
    _print_gdp_check(result)

    # Satellites
    if args.with_satellites:
        sat_data = load_satellites_from_json(args.with_satellites)
        _print_satellite_summary(sat_data)

    # Errors and warnings
    if result.warnings:
        print()
        print(f"  Warnings ({len(result.warnings)}):")
        for w in result.warnings:
            print(f"    - {w}")

    if result.errors:
        print()
        print(f"  ERRORS ({len(result.errors)}):")
        for e in result.errors:
            print(f"    ! {e}")

    # Final verdict
    print()
    print("=" * 60)
    if result.is_valid:
        print("  RESULT: PASS")
        print("=" * 60)
        sys.exit(0)
    else:
        print(f"  RESULT: FAIL ({len(result.errors)} errors)")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
