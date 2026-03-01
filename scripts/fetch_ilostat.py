"""Fetch ILO employment data for Saudi Arabia via rplumber REST API.

Pulls employment by economic activity (ISIC Rev.4) and occupation (ISCO-08).
Writes to data/raw/ilo/ with _metadata.json.

Usage:
    python -m scripts.fetch_ilostat
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

BASE_URL = "https://rplumber.ilo.org/data/indicator"
OUT_DIR = Path("data/raw/ilo")
TIMEOUT = 90.0  # API can be slow
DELAY = 3.0  # Be respectful to ILO servers


def sha256_of_json(data: object) -> str:
    """Compute SHA-256 hash of JSON-serialized data."""
    raw = json.dumps(data, sort_keys=True, default=str).encode()
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


def _columnar_to_rows(data: dict) -> list[dict]:
    """Convert columnar ILO response to list of row dicts."""
    keys = list(data.keys())
    if not keys:
        return []
    n = len(data[keys[0]])
    rows = []
    for i in range(n):
        row = {k: data[k][i] for k in keys}
        rows.append(row)
    return rows


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

    url = f"{BASE_URL}/"
    params = {
        "id": "EMP_TEMP_SEX_ECO_NB_A",
        "ref_area": "SAU",
        "format": ".json",
    }

    try:
        resp = client.get(url, params=params, timeout=TIMEOUT)

        if resp.status_code == 200:
            raw_data = resp.json()
            # Convert columnar to row-based format
            rows = _columnar_to_rows(raw_data)

            # Filter to SEX_T (total, both sexes) and ISIC4 classifications
            isic4_rows = [
                r for r in rows
                if r.get("sex") == "SEX_T"
                and isinstance(r.get("classif1"), str)
                and r["classif1"].startswith("ECO_ISIC4_")
            ]

            result["observation_count"] = len(isic4_rows)
            result["status"] = "success"

            output = {
                "source": "ILOSTAT (ILO)",
                "indicator": "EMP_TEMP_SEX_ECO_NB_A",
                "country": "SAU",
                "description": "Employment by ISIC Rev.4 economic activity",
                "total_rows": len(rows),
                "isic4_observations": len(isic4_rows),
                "fetch_timestamp": datetime.now(tz=timezone.utc).isoformat(),
                "observations": isic4_rows,
            }
            result["sha256"] = sha256_of_json(isic4_rows)

            out_path = OUT_DIR / "sau_employment_by_activity.json"
            out_path.write_text(json.dumps(output, indent=2, default=str))
            print(f"OK | {len(isic4_rows)} ISIC4 observations ({len(rows)} total)")
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

    url = f"{BASE_URL}/"
    params = {
        "id": "EMP_TEMP_SEX_OCU_NB_A",
        "ref_area": "SAU",
        "format": ".json",
    }

    try:
        resp = client.get(url, params=params, timeout=TIMEOUT)

        if resp.status_code == 200:
            raw_data = resp.json()
            rows = _columnar_to_rows(raw_data)

            # Filter to SEX_T
            filtered = [r for r in rows if r.get("sex") == "SEX_T"]

            result["observation_count"] = len(filtered)
            result["status"] = "success"

            output = {
                "source": "ILOSTAT (ILO)",
                "indicator": "EMP_TEMP_SEX_OCU_NB_A",
                "country": "SAU",
                "description": "Employment by ISCO-08 occupation",
                "total_rows": len(rows),
                "filtered_observations": len(filtered),
                "fetch_timestamp": datetime.now(tz=timezone.utc).isoformat(),
                "observations": filtered,
            }
            result["sha256"] = sha256_of_json(filtered)

            out_path = OUT_DIR / "sau_employment_by_occupation.json"
            out_path.write_text(json.dumps(output, indent=2, default=str))
            print(f"OK | {len(filtered)} observations")
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
        "fetch_timestamp": datetime.now(tz=timezone.utc).isoformat(),
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
