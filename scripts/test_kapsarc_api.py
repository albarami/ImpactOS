"""Test KAPSARC Data Portal API connectivity.

KAPSARC uses OpenDataSoft platform — anonymous read access, rate-limited.

Usage:
    python -m scripts.test_kapsarc_api
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

BASE_URL = "https://datasource.kapsarc.org/api/v2"
OUT_DIR = Path("data/raw/kapsarc")

DATASETS = {
    "io_current_prices": "input-output-table-at-current-prices",
    "type1_multipliers": "input-output-table-type-i-multiplier",
    "gdp_by_activity": (
        "gross-domestic-product-by-kind-of-economic-activity"
        "-at-current-prices-2018-100"
    ),
    "labor_market_indicators": "main-labor-market-indicators",
    "gosi_beneficiaries": "gosi-beneficiaries",
    "labor_force_indicators": "labor-force-indicators",
}

TIMEOUT = 30.0
DELAY = 1.0  # seconds between requests


def test_dataset(
    client: httpx.Client,
    name: str,
    dataset_id: str,
) -> dict:
    """Test a single KAPSARC dataset endpoint.

    Returns a result dict with status, record count, fields, etc.
    """
    url = f"{BASE_URL}/catalog/datasets/{dataset_id}/records"
    params = {"limit": 5}

    result: dict = {
        "name": name,
        "dataset_id": dataset_id,
        "url": url,
        "status": "unknown",
        "http_status": None,
        "record_count": None,
        "total_count": None,
        "fields": [],
        "sample_record": None,
        "error": None,
    }

    try:
        resp = client.get(url, params=params, timeout=TIMEOUT)
        result["http_status"] = resp.status_code

        if resp.status_code == 200:
            data = resp.json()
            result["total_count"] = data.get("total_count", 0)
            records = data.get("results", [])
            result["record_count"] = len(records)

            if records:
                first = records[0]
                result["fields"] = sorted(first.keys())
                result["sample_record"] = first

            result["status"] = "ok"

            # Save sample response
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            out_path = OUT_DIR / f"test_{name}.json"
            out_path.write_text(json.dumps(data, indent=2, default=str))
        else:
            result["status"] = "http_error"
            result["error"] = f"HTTP {resp.status_code}: {resp.text[:200]}"

    except httpx.TimeoutException:
        result["status"] = "timeout"
        result["error"] = f"Request timed out after {TIMEOUT}s"
    except httpx.ConnectError as e:
        result["status"] = "connection_error"
        result["error"] = str(e)[:200]
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)[:200]

    return result


def main() -> int:
    """Run all KAPSARC API connectivity tests."""
    print("=== KAPSARC Data Portal API Test ===\n")
    print(f"Base URL: {BASE_URL}")
    print(f"Datasets: {len(DATASETS)}\n")

    results: list[dict] = []

    with httpx.Client() as client:
        for name, dataset_id in DATASETS.items():
            print(f"  Testing {name}...", end=" ", flush=True)
            result = test_dataset(client, name, dataset_id)
            results.append(result)

            if result["status"] == "ok":
                print(
                    f"OK | {result['total_count']} total records | "
                    f"{len(result['fields'])} fields"
                )
            else:
                print(f"FAIL | {result['error']}")

            time.sleep(DELAY)

    # Summary
    ok = sum(1 for r in results if r["status"] == "ok")
    print(f"\n--- Summary: {ok}/{len(results)} endpoints OK ---")

    # Save full results
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUT_DIR / "_test_results.json"
    report_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"Results saved to {report_path}")

    return 0 if ok > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
