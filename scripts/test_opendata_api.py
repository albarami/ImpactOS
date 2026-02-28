"""Test Saudi Open Data Portal (open.data.gov.sa) API connectivity.

The portal may use CKAN-based API. Previous tests showed 403 blocks.

Usage:
    python -m scripts.test_opendata_api
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

OUT_DIR = Path("data/raw/opendata")
TIMEOUT = 30.0
DELAY = 1.0

# Try both known URL patterns
API_BASES = [
    "https://open.data.gov.sa/api/3",
    "https://od.data.gov.sa/api/3",
]


def test_endpoint(
    client: httpx.Client,
    base: str,
    path: str,
    name: str,
    params: dict | None = None,
) -> dict:
    """Test a single Open Data Portal endpoint."""
    url = f"{base}{path}"
    result: dict = {
        "name": name,
        "url": url,
        "status": "unknown",
        "http_status": None,
        "error": None,
    }

    try:
        resp = client.get(url, params=params, timeout=TIMEOUT)
        result["http_status"] = resp.status_code

        if resp.status_code == 200:
            result["status"] = "ok"
            try:
                data = resp.json()
                result["response_keys"] = list(data.keys())[:10]
                if "result" in data:
                    r = data["result"]
                    if isinstance(r, list):
                        result["result_count"] = len(r)
                    elif isinstance(r, dict):
                        result["result_count"] = r.get("count", "?")
            except Exception:
                result["content_type"] = resp.headers.get("content-type", "")
        elif resp.status_code == 403:
            result["status"] = "blocked"
            result["error"] = "403 Forbidden — automated access blocked"
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
    """Run Open Data Portal connectivity tests."""
    print("=== Saudi Open Data Portal API Test ===\n")

    results: list[dict] = []

    with httpx.Client(follow_redirects=True) as client:
        for base in API_BASES:
            print(f"\nTrying base: {base}")

            tests = [
                ("/action/package_list", "package_list", None),
                (
                    "/action/package_search",
                    "search_gastat",
                    {"q": "GASTAT"},
                ),
                (
                    "/action/package_search",
                    "search_employment",
                    {"q": "employment sector"},
                ),
                (
                    "/action/package_search",
                    "search_gdp",
                    {"q": "GDP economic activity"},
                ),
            ]

            for path, name, params in tests:
                print(f"  Testing {name}...", end=" ", flush=True)
                r = test_endpoint(client, base, path, name, params)
                results.append(r)

                if r["status"] == "ok":
                    count = r.get("result_count", "?")
                    print(f"OK | results: {count}")

                    # Save sample response
                    OUT_DIR.mkdir(parents=True, exist_ok=True)
                    # Re-fetch to save (we already know it works)
                    url = f"{base}{path}"
                    resp = client.get(url, params=params, timeout=TIMEOUT)
                    if resp.status_code == 200:
                        out_path = OUT_DIR / f"test_{name}.json"
                        out_path.write_text(
                            json.dumps(
                                resp.json(), indent=2, default=str
                            )
                        )
                else:
                    print(f"{r['status'].upper()} | {r.get('error', '')}")

                time.sleep(DELAY)

            # If first base works, skip second
            ok_this_base = sum(
                1 for r in results[-len(tests):]
                if r["status"] == "ok"
            )
            if ok_this_base > 0:
                break

    ok = sum(1 for r in results if r["status"] == "ok")
    print(f"\n--- Summary: {ok}/{len(results)} endpoints OK ---")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUT_DIR / "_test_results.json"
    report_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"Results saved to {report_path}")

    return 0 if ok > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
