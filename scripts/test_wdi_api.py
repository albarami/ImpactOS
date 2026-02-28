"""Test World Bank WDI API connectivity.

No auth required. JSON responses with [metadata, records] structure.

Usage:
    python -m scripts.test_wdi_api
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

BASE_URL = "https://api.worldbank.org/v2"
OUT_DIR = Path("data/raw/worldbank")

INDICATORS = {
    "NY.GDP.MKTP.CD": "GDP (current US$)",
    "NY.GDP.DEFL.ZS.AD": "GDP deflator",
    "SL.IND.EMPL.ZS": "Employment in industry (%)",
    "SL.SRV.EMPL.ZS": "Employment in services (%)",
    "NE.TRD.GNFS.ZS": "Trade (% of GDP)",
    "BX.KLT.DINV.WD.GD.ZS": "FDI net inflows (% of GDP)",
}

TIMEOUT = 30.0
DELAY = 0.5


def test_indicator(
    client: httpx.Client,
    code: str,
    description: str,
) -> dict:
    """Test a single WDI indicator for Saudi Arabia."""
    url = f"{BASE_URL}/country/SAU/indicator/{code}"
    params = {"format": "json", "per_page": 10}

    result: dict = {
        "indicator": code,
        "description": description,
        "url": url,
        "status": "unknown",
        "http_status": None,
        "record_count": None,
        "latest_year": None,
        "latest_value": None,
        "error": None,
    }

    try:
        resp = client.get(url, params=params, timeout=TIMEOUT)
        result["http_status"] = resp.status_code

        if resp.status_code == 200:
            data = resp.json()
            # WDI returns [metadata, records]
            if isinstance(data, list) and len(data) >= 2:
                metadata = data[0]
                records = data[1] or []
                result["record_count"] = len(records)
                result["total_pages"] = metadata.get("pages", 0)

                # Find latest non-null value
                for rec in records:
                    if rec.get("value") is not None:
                        result["latest_year"] = rec.get("date")
                        result["latest_value"] = rec["value"]
                        break

                result["status"] = "ok"

                # Save sample response
                OUT_DIR.mkdir(parents=True, exist_ok=True)
                safe_code = code.replace(".", "_")
                out_path = OUT_DIR / f"test_{safe_code}.json"
                out_path.write_text(
                    json.dumps(data, indent=2, default=str)
                )
            else:
                result["status"] = "unexpected_format"
                result["error"] = f"Expected [meta, data], got {type(data)}"
        else:
            result["status"] = "http_error"
            result["error"] = f"HTTP {resp.status_code}"

    except httpx.TimeoutException:
        result["status"] = "timeout"
        result["error"] = f"Timed out after {TIMEOUT}s"
    except httpx.ConnectError as e:
        result["status"] = "connection_error"
        result["error"] = str(e)[:200]
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)[:200]

    return result


def main() -> int:
    """Run all WDI API connectivity tests."""
    print("=== World Bank WDI API Test ===\n")
    print(f"Base URL: {BASE_URL}")
    print("Country: SAU (Saudi Arabia)")
    print(f"Indicators: {len(INDICATORS)}\n")

    results: list[dict] = []

    with httpx.Client(follow_redirects=True) as client:
        for code, desc in INDICATORS.items():
            print(f"  Testing {code}...", end=" ", flush=True)
            result = test_indicator(client, code, desc)
            results.append(result)

            if result["status"] == "ok":
                print(
                    f"OK | {result['record_count']} records | "
                    f"latest: {result['latest_year']}="
                    f"{result['latest_value']}"
                )
            else:
                print(f"FAIL | {result['error']}")

            time.sleep(DELAY)

    ok = sum(1 for r in results if r["status"] == "ok")
    print(f"\n--- Summary: {ok}/{len(results)} indicators OK ---")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUT_DIR / "_test_results.json"
    report_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"Results saved to {report_path}")

    return 0 if ok > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
