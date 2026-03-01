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
