"""Master data fetch script — single entry point for refreshing all external data.

Usage:
    python -m scripts.fetch_all [--sources all|kapsarc|wdi|ilo|sama] [--test-only]

    --test-only  Run connectivity tests without full data fetch
    --sources    Comma-separated list of sources (default: all)
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ALL_SOURCES = {
    "kapsarc": {
        "test_module": "scripts.test_kapsarc_api",
        "fetch_module": "scripts.fetch_kapsarc",
        "label": "KAPSARC Data Portal",
    },
    "wdi": {
        "test_module": "scripts.test_wdi_api",
        "fetch_module": "scripts.fetch_wdi",
        "label": "World Bank WDI",
    },
    "ilo": {
        "test_module": "scripts.test_ilostat_api",
        "fetch_module": "scripts.fetch_ilostat",
        "label": "ILOSTAT (ILO)",
    },
    "sama": {
        "test_module": "scripts.test_sama_api",
        "fetch_module": "scripts.fetch_sama",
        "label": "SAMA (Saudi Central Bank)",
    },
}


def _run_module(module_name: str) -> int:
    """Import and run a module's main() function."""
    try:
        mod = importlib.import_module(module_name)
        return mod.main()
    except Exception as e:
        print(f"  ERROR running {module_name}: {e}")
        return 1


def main() -> int:
    """Master fetch entry point."""
    parser = argparse.ArgumentParser(
        description="Fetch external data for ImpactOS",
    )
    parser.add_argument(
        "--sources",
        default="all",
        help="Comma-separated sources: all, kapsarc, wdi, ilo, sama",
    )
    parser.add_argument(
        "--test-only",
        action="store_true",
        help="Run connectivity tests only (no full fetch)",
    )
    args = parser.parse_args()

    # Determine which sources to run
    if args.sources == "all":
        sources = list(ALL_SOURCES.keys())
    else:
        sources = [s.strip() for s in args.sources.split(",")]
        for s in sources:
            if s not in ALL_SOURCES:
                print(f"Unknown source: {s}")
                print(f"Available: {', '.join(ALL_SOURCES)}")
                return 1

    mode = "TEST ONLY" if args.test_only else "FULL FETCH"
    print(f"\n{'=' * 60}")
    print(f"  ImpactOS Data Fetch — {mode}")
    print(f"  Sources: {', '.join(sources)}")
    print(f"  Time: {datetime.now(datetime.UTC).isoformat()}")
    print(f"{'=' * 60}\n")

    start = time.time()
    results: dict[str, dict] = {}

    for source_id in sources:
        config = ALL_SOURCES[source_id]
        label = config["label"]

        print(f"\n{'=' * 50}")
        print(f"  {label}")
        print(f"{'=' * 50}")

        # Phase 1: Connectivity test
        print("\n  Phase 1: Connectivity test")
        test_code = _run_module(config["test_module"])
        test_ok = test_code == 0

        results[source_id] = {
            "label": label,
            "test_status": "ok" if test_ok else "failed",
            "fetch_status": "skipped",
        }

        # Phase 2: Full fetch (if not test-only and test passed)
        if not args.test_only:
            if test_ok:
                print("\n  Phase 2: Full data fetch")
                fetch_code = _run_module(config["fetch_module"])
                results[source_id]["fetch_status"] = (
                    "ok" if fetch_code == 0 else "failed"
                )
            else:
                print("\n  Phase 2: Skipped (connectivity test failed)")
                results[source_id]["fetch_status"] = "skipped"

    elapsed = time.time() - start

    # Summary
    print(f"\n{'=' * 60}")
    print(f"  SUMMARY ({elapsed:.1f}s)")
    print(f"{'=' * 60}")

    for _source_id, r in results.items():
        test_icon = "\u2705" if r["test_status"] == "ok" else "\u274c"
        fetch_icon = {
            "ok": "\u2705",
            "skipped": "\u23ed\ufe0f",
            "failed": "\u274c",
        }.get(r["fetch_status"], "?")
        print(
            f"  {r['label']}: "
            f"test={test_icon} {r['test_status']}  "
            f"fetch={fetch_icon} {r['fetch_status']}"
        )

    # Save summary
    out_dir = Path("data/raw")
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "fetch_summary.json"
    summary_path.write_text(json.dumps({
        "timestamp": datetime.now(datetime.UTC).isoformat(),
        "mode": mode.lower(),
        "duration_seconds": round(elapsed, 1),
        "results": results,
    }, indent=2))
    print(f"\nSummary saved to {summary_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
