"""Benchmark validation — compare engine outputs against published data.

Validates our engine's computed multipliers against KAPSARC published
Type I multipliers. This is a critical quality gate: if our model's
multipliers diverge significantly from published values, something
is wrong.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SectorComparison:
    """Comparison of a single sector's multiplier."""

    sector_code: str
    sector_name: str
    computed: float
    benchmark: float
    absolute_diff: float
    pct_diff: float  # percentage difference
    within_tolerance: bool


@dataclass(frozen=True)
class ValidationReport:
    """Result of comparing computed vs benchmark multipliers."""

    sector_comparisons: list[SectorComparison]
    sectors_within_tolerance: int
    sectors_outside_tolerance: int
    total_sectors: int
    rmse: float
    mae: float
    max_pct_diff: float
    tolerance_used: float
    overall_pass: bool
    warnings: list[str]


class BenchmarkValidator:
    """Validates engine outputs against published benchmarks."""

    def validate_multipliers(
        self,
        computed: dict[str, float],
        benchmark: dict[str, float],
        tolerance: float = 0.05,
    ) -> ValidationReport:
        """Compare computed vs published Type I multipliers.

        Args:
            computed: {sector_code: multiplier} from our engine.
            benchmark: {sector_code: multiplier} from KAPSARC.
            tolerance: Maximum acceptable percentage difference (0.05 = 5%).

        Returns:
            ValidationReport with per-sector comparisons and summary stats.
        """
        warnings: list[str] = []

        # Find common sectors
        common = set(computed.keys()) & set(benchmark.keys())
        only_computed = set(computed.keys()) - set(benchmark.keys())
        only_benchmark = set(benchmark.keys()) - set(computed.keys())

        if only_computed:
            warnings.append(
                f"Sectors in computed but not benchmark: "
                f"{sorted(only_computed)}"
            )
        if only_benchmark:
            warnings.append(
                f"Sectors in benchmark but not computed: "
                f"{sorted(only_benchmark)}"
            )

        comparisons: list[SectorComparison] = []
        squared_diffs: list[float] = []
        abs_diffs: list[float] = []

        for sector in sorted(common):
            comp_val = computed[sector]
            bench_val = benchmark[sector]

            abs_diff = comp_val - bench_val
            pct_diff = (
                abs_diff / bench_val if abs(bench_val) > 1e-12 else 0.0
            )
            within = abs(pct_diff) <= tolerance

            comparisons.append(SectorComparison(
                sector_code=sector,
                sector_name=sector,
                computed=comp_val,
                benchmark=bench_val,
                absolute_diff=abs_diff,
                pct_diff=pct_diff,
                within_tolerance=within,
            ))

            squared_diffs.append(abs_diff ** 2)
            abs_diffs.append(abs(abs_diff))

        n = len(comparisons)
        within_count = sum(1 for c in comparisons if c.within_tolerance)
        outside_count = n - within_count

        rmse = math.sqrt(sum(squared_diffs) / n) if n > 0 else 0.0
        mae = sum(abs_diffs) / n if n > 0 else 0.0
        max_pct = (
            max(abs(c.pct_diff) for c in comparisons) if comparisons else 0.0
        )

        # Overall pass: all sectors within tolerance
        overall_pass = outside_count == 0 and n > 0

        return ValidationReport(
            sector_comparisons=comparisons,
            sectors_within_tolerance=within_count,
            sectors_outside_tolerance=outside_count,
            total_sectors=n,
            rmse=rmse,
            mae=mae,
            max_pct_diff=max_pct,
            tolerance_used=tolerance,
            overall_pass=overall_pass,
            warnings=warnings,
        )

    def load_benchmark_from_file(
        self,
        path: str | Path,
    ) -> dict[str, float]:
        """Load benchmark multipliers from curated JSON.

        Expected format (from kapsarc_multiplier_parser):
        {
            "sectors": [
                {"sector_code": "A", "output_multiplier": 1.23},
                ...
            ]
        }
        """
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        result: dict[str, float] = {}
        for sector in data.get("sectors", []):
            code = sector.get("sector_code", "")
            mult = sector.get("output_multiplier", 0.0)
            if code:
                result[code] = mult
        return result

    def format_report(self, report: ValidationReport) -> str:
        """Format a validation report as human-readable text."""
        lines: list[str] = [
            "=== Multiplier Benchmark Validation ===",
            f"Tolerance: {report.tolerance_used:.1%}",
            f"Sectors: {report.total_sectors}",
            f"Pass: {report.sectors_within_tolerance} | "
            f"Fail: {report.sectors_outside_tolerance}",
            f"RMSE: {report.rmse:.4f} | MAE: {report.mae:.4f}",
            f"Max % diff: {report.max_pct_diff:.2%}",
            f"Overall: {'PASS' if report.overall_pass else 'FAIL'}",
            "",
            "Per-sector details:",
        ]

        # Sort by largest divergence
        sorted_comps = sorted(
            report.sector_comparisons,
            key=lambda c: abs(c.pct_diff),
            reverse=True,
        )

        for c in sorted_comps:
            icon = "\u2705" if c.within_tolerance else "\u274c"
            lines.append(
                f"  {icon} {c.sector_code}: "
                f"computed={c.computed:.3f} "
                f"bench={c.benchmark:.3f} "
                f"diff={c.pct_diff:+.2%}"
            )

        if report.warnings:
            lines.append("")
            lines.append("Warnings:")
            for w in report.warnings:
                lines.append(f"  - {w}")

        return "\n".join(lines)
