"""Fetch full datasets from KAPSARC Data Portal.

Pulls all records (paginated) for IO tables, multipliers, GDP, and labor data.
Writes to data/raw/kapsarc/ with _metadata.json.

Usage:
    python -m scripts.fetch_kapsarc
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

BASE_URL = "https://datasource.kapsarc.org/api/v2"
OUT_DIR = Path("data/raw/kapsarc")
PAGE_SIZE = 100
TIMEOUT = 60.0
DELAY = 1.0  # seconds between pages

DATASETS = {
    "io_current_prices": {
        "id": "input-output-table-at-current-prices",
        "description": "Saudi IO table at current prices",
    },
    "type1_multipliers": {
        "id": "input-output-table-type-i-multiplier",
        "description": "Type I output multipliers",
    },
    "gdp_by_activity": {
        "id": (
            "gross-domestic-product-by-kind-of-economic-activity"
            "-at-current-prices-2018-100"
        ),
        "description": "GDP by economic activity (current prices, 2018=100)",
    },
    "labor_market_indicators": {
        "id": "main-labor-market-indicators",
        "description": "Main labor market indicators",
    },
    "gosi_beneficiaries": {
        "id": "gosi-beneficiaries",
        "description": "GOSI beneficiary counts",
    },
    "labor_force_indicators": {
        "id": "labor-force-indicators",
        "description": "Labor force indicators by nationality/gender",
    },
}


def fetch_all_records(
    client: httpx.Client,
    dataset_id: str,
) -> tuple[list[dict], int]:
    """Fetch all records from a KAPSARC dataset using pagination.

    Returns (records, total_count).
    """
    all_records: list[dict] = []
    offset = 0
    total_count = 0

    while True:
        url = f"{BASE_URL}/catalog/datasets/{dataset_id}/records"
        params = {"limit": PAGE_SIZE, "offset": offset}

        resp = client.get(url, params=params, timeout=TIMEOUT)
        resp.raise_for_status()

        data = resp.json()
        total_count = data.get("total_count", 0)
        records = data.get("results", [])

        if not records:
            break

        all_records.extend(records)
        offset += len(records)

        if offset >= total_count:
            break

        time.sleep(DELAY)

    return all_records, total_count


def sha256_of_json(data: object) -> str:
    """Compute SHA-256 hash of JSON-serialized data."""
    raw = json.dumps(data, sort_keys=True, default=str).encode()
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


def fetch_dataset(
    client: httpx.Client,
    name: str,
    config: dict,
) -> dict:
    """Fetch a single dataset and save to disk."""
    dataset_id = config["id"]
    print(f"  Fetching {name} ({dataset_id})...", end=" ", flush=True)

    result: dict = {
        "name": name,
        "dataset_id": dataset_id,
        "url": f"{BASE_URL}/catalog/datasets/{dataset_id}/records",
        "status": "unknown",
        "record_count": 0,
        "total_count": 0,
        "sha256": "",
        "date_range": "",
        "error": None,
    }

    try:
        records, total_count = fetch_all_records(client, dataset_id)
        result["record_count"] = len(records)
        result["total_count"] = total_count
        result["status"] = "success"

        # Try to detect date range from common year fields
        years = set()
        for rec in records:
            for key in ("year", "date", "period", "time_period"):
                if key in rec:
                    try:
                        yr = int(str(rec[key])[:4])
                        if 1900 < yr < 2100:
                            years.add(yr)
                    except (ValueError, TypeError):
                        pass
        if years:
            result["date_range"] = f"{min(years)}-{max(years)}"

        # Save full dataset
        output = {
            "dataset_id": dataset_id,
            "description": config["description"],
            "total_count": total_count,
            "record_count": len(records),
            "fetch_timestamp": datetime.now(datetime.UTC).isoformat(),
            "records": records,
        }
        result["sha256"] = sha256_of_json(records)

        out_path = OUT_DIR / f"{name}.json"
        out_path.write_text(json.dumps(output, indent=2, default=str))

        print(f"OK | {len(records)} records")

    except httpx.HTTPStatusError as e:
        result["status"] = "http_error"
        result["error"] = f"HTTP {e.response.status_code}"
        print(f"FAIL | HTTP {e.response.status_code}")
    except httpx.TimeoutException:
        result["status"] = "timeout"
        result["error"] = "Timed out"
        print("FAIL | Timeout")
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)[:200]
        print(f"FAIL | {e!s:.60}")

    return result


def main() -> int:
    """Fetch all KAPSARC datasets."""
    print("=== KAPSARC Data Portal — Full Fetch ===\n")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset_results: dict[str, dict] = {}

    with httpx.Client() as client:
        for name, config in DATASETS.items():
            result = fetch_dataset(client, name, config)
            dataset_results[name] = result

    # Write metadata
    metadata = {
        "source": "KAPSARC Data Portal",
        "base_url": BASE_URL,
        "fetch_timestamp": datetime.now(datetime.UTC).isoformat(),
        "datasets": {
            name: {
                "url": r["url"],
                "record_count": r["record_count"],
                "date_range": r["date_range"],
                "sha256": r["sha256"],
                "status": r["status"],
                "error": r.get("error"),
            }
            for name, r in dataset_results.items()
        },
    }
    meta_path = OUT_DIR / "_metadata.json"
    meta_path.write_text(json.dumps(metadata, indent=2, default=str))

    ok = sum(
        1 for r in dataset_results.values() if r["status"] == "success"
    )
    print(f"\n--- {ok}/{len(dataset_results)} datasets fetched ---")
    print(f"Metadata: {meta_path}")

    return 0 if ok > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
