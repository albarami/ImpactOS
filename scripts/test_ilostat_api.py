"""Test ILOSTAT SDMX REST API connectivity.

ILOSTAT uses SDMX REST. No auth required. Response is SDMX-JSON (complex).

Usage:
    python -m scripts.test_ilostat_api
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

BASE_URL = "https://www.ilo.org/sdmx/rest"
OUT_DIR = Path("data/raw/ilo")

TIMEOUT = 60.0  # SDMX can be slow
DELAY = 2.0


def test_dataflow_list(client: httpx.Client) -> dict:
    """Test fetching the ILO dataflow catalog."""
    url = f"{BASE_URL}/dataflow/ILO"
    result: dict = {
        "name": "dataflow_list",
        "url": url,
        "status": "unknown",
        "http_status": None,
        "error": None,
    }

    try:
        resp = client.get(
            url,
            headers={"Accept": "application/json"},
            timeout=TIMEOUT,
        )
        result["http_status"] = resp.status_code

        if resp.status_code == 200:
            data = resp.json()
            result["status"] = "ok"

            # Count dataflows
            structures = data.get("data", {}).get("dataflows", [])
            result["dataflow_count"] = len(structures)

            # Save (truncated — full catalog is large)
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            out_path = OUT_DIR / "test_dataflow_list.json"
            # Only save first 10 dataflows to keep file manageable
            truncated = {
                "total_dataflows": len(structures),
                "sample": structures[:10] if structures else [],
            }
            out_path.write_text(
                json.dumps(truncated, indent=2, default=str)
            )
        else:
            result["status"] = "http_error"
            result["error"] = f"HTTP {resp.status_code}: {resp.text[:200]}"

    except httpx.TimeoutException:
        result["status"] = "timeout"
        result["error"] = f"Timed out after {TIMEOUT}s"
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)[:200]

    return result


def test_employment_by_activity(client: httpx.Client) -> dict:
    """Test Saudi employment by economic activity (ISIC4)."""
    # ISIC sections: A, B, C (test a few)
    activities = "ECO_ISIC4_TOTAL+ECO_ISIC4_A+ECO_ISIC4_B+ECO_ISIC4_C"
    key = f"SAU..SEX_T.{activities}"
    url = (
        f"{BASE_URL}/data/ILO,DF_EMP_TEMP_SEX_ECO_NB,1.0/{key}"
    )
    params = {"format": "jsondata", "lastNObservations": "3"}

    result: dict = {
        "name": "employment_by_activity",
        "url": url,
        "status": "unknown",
        "http_status": None,
        "observation_count": None,
        "error": None,
    }

    try:
        resp = client.get(url, params=params, timeout=TIMEOUT)
        result["http_status"] = resp.status_code

        if resp.status_code == 200:
            data = resp.json()
            result["status"] = "ok"

            # Count observations in SDMX structure
            datasets = data.get("dataSets", [])
            obs_count = 0
            if datasets:
                series = datasets[0].get("series", {})
                for _s_key, s_val in series.items():
                    obs_count += len(s_val.get("observations", {}))
            result["observation_count"] = obs_count

            OUT_DIR.mkdir(parents=True, exist_ok=True)
            out_path = OUT_DIR / "test_employment_by_activity.json"
            out_path.write_text(json.dumps(data, indent=2, default=str))
        else:
            result["status"] = "http_error"
            result["error"] = f"HTTP {resp.status_code}: {resp.text[:300]}"

    except httpx.TimeoutException:
        result["status"] = "timeout"
        result["error"] = f"Timed out after {TIMEOUT}s"
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)[:200]

    return result


def test_employment_by_occupation(client: httpx.Client) -> dict:
    """Test Saudi employment by occupation (ISCO-08)."""
    key = "SAU..SEX_T.OCU_ISCO08_TOTAL"
    url = (
        f"{BASE_URL}/data/ILO,DF_EMP_TEMP_SEX_OCU_NB,1.0/{key}"
    )
    params = {"format": "jsondata", "lastNObservations": "3"}

    result: dict = {
        "name": "employment_by_occupation",
        "url": url,
        "status": "unknown",
        "http_status": None,
        "observation_count": None,
        "error": None,
    }

    try:
        resp = client.get(url, params=params, timeout=TIMEOUT)
        result["http_status"] = resp.status_code

        if resp.status_code == 200:
            data = resp.json()
            result["status"] = "ok"

            datasets = data.get("dataSets", [])
            obs_count = 0
            if datasets:
                series = datasets[0].get("series", {})
                for s_val in series.values():
                    obs_count += len(s_val.get("observations", {}))
            result["observation_count"] = obs_count

            OUT_DIR.mkdir(parents=True, exist_ok=True)
            out_path = OUT_DIR / "test_employment_by_occupation.json"
            out_path.write_text(json.dumps(data, indent=2, default=str))
        else:
            result["status"] = "http_error"
            result["error"] = f"HTTP {resp.status_code}: {resp.text[:300]}"

    except httpx.TimeoutException:
        result["status"] = "timeout"
        result["error"] = f"Timed out after {TIMEOUT}s"
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)[:200]

    return result


def main() -> int:
    """Run all ILOSTAT API connectivity tests."""
    print("=== ILOSTAT SDMX API Test ===\n")
    print(f"Base URL: {BASE_URL}")
    print("Country: SAU\n")

    results: list[dict] = []

    with httpx.Client(follow_redirects=True) as client:
        # Test 1: Dataflow list
        print("  Testing dataflow catalog...", end=" ", flush=True)
        r = test_dataflow_list(client)
        results.append(r)
        if r["status"] == "ok":
            print(f"OK | {r.get('dataflow_count', '?')} dataflows")
        else:
            print(f"FAIL | {r['error']}")
        time.sleep(DELAY)

        # Test 2: Employment by activity
        print("  Testing employment by activity...", end=" ", flush=True)
        r = test_employment_by_activity(client)
        results.append(r)
        if r["status"] == "ok":
            print(f"OK | {r['observation_count']} observations")
        else:
            print(f"FAIL | {r['error']}")
        time.sleep(DELAY)

        # Test 3: Employment by occupation
        print("  Testing employment by occupation...", end=" ", flush=True)
        r = test_employment_by_occupation(client)
        results.append(r)
        if r["status"] == "ok":
            print(f"OK | {r['observation_count']} observations")
        else:
            print(f"FAIL | {r['error']}")

    ok = sum(1 for r in results if r["status"] == "ok")
    print(f"\n--- Summary: {ok}/{len(results)} endpoints OK ---")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUT_DIR / "_test_results.json"
    report_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"Results saved to {report_path}")

    return 0 if ok > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
