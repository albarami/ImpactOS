"""Test SAMA (Saudi Central Bank) data access.

SAMA does not have a confirmed public REST API.
This script tests available web endpoints and documents the manual process.

Usage:
    python -m scripts.test_sama_api
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

OUT_DIR = Path("data/raw/sama")
TIMEOUT = 30.0


def test_sama_portal(client: httpx.Client) -> dict:
    """Test SAMA economic database page accessibility."""
    url = (
        "https://www.sama.gov.sa/en-US/EconomicReports/pages/database.aspx"
    )
    result: dict = {
        "name": "sama_portal",
        "url": url,
        "status": "unknown",
        "http_status": None,
        "error": None,
        "notes": "",
    }

    try:
        resp = client.get(url, timeout=TIMEOUT)
        result["http_status"] = resp.status_code

        if resp.status_code == 200:
            result["status"] = "ok"
            result["notes"] = (
                "Portal accessible. No REST API detected. "
                "Data available as Excel/PDF manual downloads."
            )
        else:
            result["status"] = "http_error"
            result["error"] = f"HTTP {resp.status_code}"

    except httpx.TimeoutException:
        result["status"] = "timeout"
        result["error"] = f"Timed out after {TIMEOUT}s"
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)[:200]

    return result


def test_opendata_sama(client: httpx.Client) -> dict:
    """Test SAMA datasets on Saudi Open Data Portal."""
    url = "https://od.data.gov.sa/Data/en/group/saudi-central-bank"
    result: dict = {
        "name": "opendata_sama",
        "url": url,
        "status": "unknown",
        "http_status": None,
        "error": None,
        "notes": "",
    }

    try:
        resp = client.get(url, timeout=TIMEOUT)
        result["http_status"] = resp.status_code

        if resp.status_code == 200:
            result["status"] = "ok"
            result["notes"] = (
                "Open Data Portal SAMA group page accessible."
            )
        elif resp.status_code == 403:
            result["status"] = "blocked"
            result["error"] = "403 Forbidden — automated access blocked"
            result["notes"] = (
                "The Saudi Open Data Portal blocks automated requests. "
                "SAMA data may need manual download."
            )
        else:
            result["status"] = "http_error"
            result["error"] = f"HTTP {resp.status_code}"

    except httpx.TimeoutException:
        result["status"] = "timeout"
        result["error"] = f"Timed out after {TIMEOUT}s"
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)[:200]

    return result


def main() -> int:
    """Run SAMA accessibility tests."""
    print("=== SAMA Data Access Test ===\n")

    results: list[dict] = []

    with httpx.Client(follow_redirects=True) as client:
        print("  Testing SAMA portal...", end=" ", flush=True)
        r = test_sama_portal(client)
        results.append(r)
        if r["status"] == "ok":
            print(f"OK | {r['notes']}")
        else:
            print(f"{r['status'].upper()} | {r.get('error', r.get('notes', ''))}")

        print("  Testing Open Data SAMA group...", end=" ", flush=True)
        r = test_opendata_sama(client)
        results.append(r)
        if r["status"] == "ok":
            print(f"OK | {r['notes']}")
        else:
            print(f"{r['status'].upper()} | {r.get('error', r.get('notes', ''))}")

    ok = sum(1 for r in results if r["status"] == "ok")
    print(f"\n--- Summary: {ok}/{len(results)} endpoints OK ---")
    print(
        "\nNote: SAMA data is primarily available via manual Excel/PDF "
        "download. No confirmed REST API for programmatic access."
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    meta_path = OUT_DIR / "_metadata.json"
    meta_path.write_text(json.dumps({
        "source": "SAMA (Saudi Central Bank)",
        "api_status": "no_rest_api",
        "access_method": "manual_download",
        "portal_url": (
            "https://www.sama.gov.sa/en-US/EconomicReports/"
            "pages/database.aspx"
        ),
        "notes": (
            "SAMA announced API availability via open.data.gov.sa "
            "but no public REST endpoint confirmed. Data available "
            "as Excel/PDF from portal."
        ),
        "test_results": results,
    }, indent=2, default=str))
    print(f"Results saved to {meta_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
