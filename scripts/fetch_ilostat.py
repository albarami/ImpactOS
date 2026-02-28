"""Fetch ILO employment data for Saudi Arabia via SDMX REST API.

Pulls employment by economic activity (ISIC Rev.4) and occupation (ISCO-08).
Falls back to simpler queries if complex SDMX requests fail.
Writes to data/raw/ilo/ with _metadata.json.

Usage:
    python -m scripts.fetch_ilostat
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

BASE_URL = "https://www.ilo.org/sdmx/rest"
OUT_DIR = Path("data/raw/ilo")
TIMEOUT = 90.0  # SDMX can be slow
DELAY = 3.0  # Be respectful to ILO servers

# ISIC Rev.4 activity codes we need
ISIC4_ACTIVITIES = [
    "ECO_ISIC4_TOTAL",
    "ECO_ISIC4_A",
    "ECO_ISIC4_B",
    "ECO_ISIC4_C",
    "ECO_ISIC4_D",
    "ECO_ISIC4_E",
    "ECO_ISIC4_F",
    "ECO_ISIC4_G",
    "ECO_ISIC4_H",
    "ECO_ISIC4_I",
    "ECO_ISIC4_J",
    "ECO_ISIC4_K",
    "ECO_ISIC4_L",
    "ECO_ISIC4_M",
    "ECO_ISIC4_N",
    "ECO_ISIC4_O",
    "ECO_ISIC4_P",
    "ECO_ISIC4_Q",
    "ECO_ISIC4_R",
    "ECO_ISIC4_S",
    "ECO_ISIC4_T",
    "ECO_ISIC4_U",
    "ECO_ISIC4_X",
]


def sha256_of_json(data: object) -> str:
    """Compute SHA-256 hash of JSON-serialized data."""
    raw = json.dumps(data, sort_keys=True, default=str).encode()
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


def _count_observations(data: dict) -> int:
    """Count total observations in an SDMX-JSON response."""
    datasets = data.get("dataSets", [])
    count = 0
    for ds in datasets:
        for s_val in ds.get("series", {}).values():
            count += len(s_val.get("observations", {}))
    return count


def fetch_employment_by_activity(client: httpx.Client) -> dict:
    """Fetch Saudi employment by ISIC Rev.4 economic activity."""
    print("  Fetching employment by activity (ISIC4)...", end=" ", flush=True)

    result: dict = {
        "name": "sau_employment_by_activity",
        "status": "unknown",
        "observation_count": 0,
        "sha256": "",
        "error": None,
    }

    # Try fetching all activities in one request
    activities_str = "+".join(ISIC4_ACTIVITIES)
    key = f"SAU..SEX_T.{activities_str}"
    url = f"{BASE_URL}/data/ILO,DF_EMP_TEMP_SEX_ECO_NB,1.0/{key}"
    params = {"format": "jsondata"}

    try:
        resp = client.get(
            url,
            params=params,
            headers={"Accept": "application/json"},
            timeout=TIMEOUT,
        )

        if resp.status_code == 200:
            data = resp.json()
            obs_count = _count_observations(data)
            result["observation_count"] = obs_count
            result["status"] = "success"
            result["sha256"] = sha256_of_json(data)

            out_path = OUT_DIR / "sau_employment_by_activity.json"
            out_path.write_text(json.dumps(data, indent=2, default=str))
            print(f"OK | {obs_count} observations")
        elif resp.status_code == 413:
            # Too large — try smaller batches
            print("too large, trying batches...", end=" ", flush=True)
            all_data: dict = {}

            # Batch in groups of 5
            for i in range(0, len(ISIC4_ACTIVITIES), 5):
                batch = ISIC4_ACTIVITIES[i : i + 5]
                batch_str = "+".join(batch)
                batch_key = f"SAU..SEX_T.{batch_str}"
                batch_url = (
                    f"{BASE_URL}/data/"
                    f"ILO,DF_EMP_TEMP_SEX_ECO_NB,1.0/{batch_key}"
                )

                r = client.get(
                    batch_url,
                    params=params,
                    headers={"Accept": "application/json"},
                    timeout=TIMEOUT,
                )
                if r.status_code == 200:
                    batch_data = r.json()
                    all_data[f"batch_{i}"] = batch_data
                time.sleep(DELAY)

            if all_data:
                result["status"] = "success"
                result["observation_count"] = sum(
                    _count_observations(d) for d in all_data.values()
                )
                result["sha256"] = sha256_of_json(all_data)
                out_path = OUT_DIR / "sau_employment_by_activity.json"
                out_path.write_text(
                    json.dumps(all_data, indent=2, default=str)
                )
                print(
                    f"OK (batched) | "
                    f"{result['observation_count']} observations"
                )
            else:
                result["status"] = "no_data"
                result["error"] = "All batches returned empty"
                print("FAIL | no data from batches")
        else:
            result["status"] = "http_error"
            result["error"] = f"HTTP {resp.status_code}"
            print(f"FAIL | HTTP {resp.status_code}")

    except httpx.TimeoutException:
        result["status"] = "timeout"
        result["error"] = f"Timed out after {TIMEOUT}s"
        print("FAIL | timeout")
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)[:200]
        print(f"FAIL | {e!s:.60}")

    return result


def fetch_employment_by_occupation(client: httpx.Client) -> dict:
    """Fetch Saudi employment by ISCO-08 occupation."""
    print("  Fetching employment by occupation (ISCO-08)...", end=" ", flush=True)

    result: dict = {
        "name": "sau_employment_by_occupation",
        "status": "unknown",
        "observation_count": 0,
        "sha256": "",
        "error": None,
    }

    key = "SAU..SEX_T.OCU_ISCO08_TOTAL"
    url = f"{BASE_URL}/data/ILO,DF_EMP_TEMP_SEX_OCU_NB,1.0/{key}"
    params = {"format": "jsondata"}

    try:
        resp = client.get(
            url,
            params=params,
            headers={"Accept": "application/json"},
            timeout=TIMEOUT,
        )

        if resp.status_code == 200:
            data = resp.json()
            obs_count = _count_observations(data)
            result["observation_count"] = obs_count
            result["status"] = "success"
            result["sha256"] = sha256_of_json(data)

            out_path = OUT_DIR / "sau_employment_by_occupation.json"
            out_path.write_text(json.dumps(data, indent=2, default=str))
            print(f"OK | {obs_count} observations")
        else:
            result["status"] = "http_error"
            result["error"] = f"HTTP {resp.status_code}"
            print(f"FAIL | HTTP {resp.status_code}")

    except httpx.TimeoutException:
        result["status"] = "timeout"
        result["error"] = f"Timed out after {TIMEOUT}s"
        print("FAIL | timeout")
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)[:200]
        print(f"FAIL | {e!s:.60}")

    return result


def main() -> int:
    """Fetch all ILO datasets."""
    print("=== ILOSTAT — Full Fetch ===\n")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset_results: dict[str, dict] = {}

    with httpx.Client(follow_redirects=True) as client:
        r = fetch_employment_by_activity(client)
        dataset_results["sau_employment_by_activity"] = r
        time.sleep(DELAY)

        r = fetch_employment_by_occupation(client)
        dataset_results["sau_employment_by_occupation"] = r

    # Metadata
    metadata = {
        "source": "ILOSTAT (ILO)",
        "base_url": BASE_URL,
        "country": "SAU",
        "fetch_timestamp": datetime.now(datetime.UTC).isoformat(),
        "datasets": {
            name: {
                "observation_count": r["observation_count"],
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
    return 0 if ok > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
