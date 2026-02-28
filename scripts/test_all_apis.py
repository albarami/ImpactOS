"""Run all API connectivity tests and produce a summary report.

Usage:
    python -m scripts.test_all_apis
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

OUT_DIR = Path("data/raw")


def _run_module(module_name: str) -> tuple[int, str]:
    """Run a test module and capture its exit code."""
    import importlib

    print(f"\n{'=' * 60}")
    print(f"  Running: {module_name}")
    print("=" * 60)

    try:
        mod = importlib.import_module(module_name)
        code = mod.main()
        return code, "ok" if code == 0 else "partial"
    except Exception as e:
        print(f"  ERROR: {e}")
        return 1, f"error: {e!s:.100}"


def main() -> int:
    """Run all API tests and produce summary."""
    start = time.time()

    modules = [
        ("scripts.test_kapsarc_api", "KAPSARC Data Portal"),
        ("scripts.test_wdi_api", "World Bank WDI"),
        ("scripts.test_ilostat_api", "ILOSTAT (ILO)"),
        ("scripts.test_sama_api", "SAMA (Saudi Central Bank)"),
        ("scripts.test_opendata_api", "Saudi Open Data Portal"),
    ]

    results: dict[str, str] = {}
    for mod_name, label in modules:
        code, status = _run_module(mod_name)
        results[label] = status

    elapsed = time.time() - start

    # Build summary report
    print("\n" + "=" * 60)
    print("  API CONNECTIVITY REPORT")
    print("=" * 60)

    report_lines = [
        "=== API Connectivity Report ===",
        f"Date: {datetime.now(datetime.UTC).isoformat()}",
        f"Duration: {elapsed:.1f}s",
        "",
    ]

    for label, status in results.items():
        icon = {
            "ok": "\u2705",
            "partial": "\u26a0\ufe0f",
        }.get(status, "\u274c")
        line = f"{icon} {label}: {status}"
        report_lines.append(line)
        print(f"  {line}")

    report_lines.append("")
    report_lines.append(
        "Note: 'ok' = all endpoints reachable, "
        "'partial' = some endpoints work, "
        "'error' = test script failed"
    )

    report_text = "\n".join(report_lines)

    # Save report
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUT_DIR / "api_connectivity_report.txt"
    report_path.write_text(report_text)
    print(f"\nReport saved to {report_path}")

    # Also save as JSON
    json_path = OUT_DIR / "api_connectivity_report.json"
    json_path.write_text(json.dumps({
        "timestamp": datetime.now(datetime.UTC).isoformat(),
        "duration_seconds": round(elapsed, 1),
        "results": results,
    }, indent=2))

    ok_count = sum(1 for s in results.values() if s == "ok")
    partial = sum(1 for s in results.values() if s == "partial")
    print(f"\nTotal: {ok_count} ok, {partial} partial, "
          f"{len(results) - ok_count - partial} failed")

    return 0


if __name__ == "__main__":
    sys.exit(main())
