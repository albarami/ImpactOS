"""Fetch World Bank WDI indicators for Saudi Arabia.

Pulls full time series (1990-2025) for macro indicators.
Writes to data/raw/worldbank/ with _metadata.json.

Usage:
    python -m scripts.fetch_wdi
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

BASE_URL = "https://api.worldbank.org/v2"
OUT_DIR = Path("data/raw/worldbank")
TIMEOUT = 30.0
DELAY = 0.5
DATE_RANGE = "1990:2025"
PER_PAGE = 100

INDICATORS = {
    "sau_gdp_current_usd": {
        "code": "NY.GDP.MKTP.CD",
        "description": "GDP (current US$)",
    },
    "sau_gdp_deflator": {
        "code": "NY.GDP.DEFL.ZS.AD",
        "description": "GDP deflator (base year varies)",
    },
    "sau_employment_industry": {
        "code": "SL.IND.EMPL.ZS",
        "description": "Employment in industry (% of total)",
    },
    "sau_employment_services": {
        "code": "SL.SRV.EMPL.ZS",
        "description": "Employment in services (% of total)",
    },
    "sau_trade_pct_gdp": {
        "code": "NE.TRD.GNFS.ZS",
        "description": "Trade (% of GDP)",
    },
    "sau_fdi_net_inflows": {
        "code": "BX.KLT.DINV.WD.GD.ZS",
        "description": "FDI net inflows (% of GDP)",
    },
}


def sha256_of_json(data: object) -> str:
    """Compute SHA-256 hash of JSON-serialized data."""
    raw = json.dumps(data, sort_keys=True, default=str).encode()
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


def fetch_indicator(
    client: httpx.Client,
    name: str,
    config: dict,
) -> dict:
    """Fetch a single WDI indicator with pagination."""
    code = config["code"]
    print(f"  Fetching {code}...", end=" ", flush=True)

    result: dict = {
        "name": name,
        "indicator": code,
        "description": config["description"],
        "status": "unknown",
        "record_count": 0,
        "date_range": "",
        "sha256": "",
        "error": None,
    }

    all_records: list[dict] = []
    page = 1

    try:
        while True:
            url = f"{BASE_URL}/country/SAU/indicator/{code}"
            params = {
                "format": "json",
                "per_page": PER_PAGE,
                "page": page,
                "date": DATE_RANGE,
            }
            resp = client.get(url, params=params, timeout=TIMEOUT)
            resp.raise_for_status()

            data = resp.json()

            if not isinstance(data, list) or len(data) < 2:
                result["status"] = "unexpected_format"
                result["error"] = "Response not [meta, records]"
                print("FAIL | bad format")
                return result

            metadata = data[0]
            records = data[1] or []
            all_records.extend(records)

            total_pages = metadata.get("pages", 1)
            if page >= total_pages:
                break
            page += 1
            time.sleep(DELAY)

        result["record_count"] = len(all_records)
        result["status"] = "success"

        # Date range from records
        years = [
            int(r["date"])
            for r in all_records
            if r.get("date") and r["date"].isdigit()
        ]
        if years:
            result["date_range"] = f"{min(years)}-{max(years)}"

        # Save
        output = {
            "indicator": code,
            "country": "SAU",
            "description": config["description"],
            "record_count": len(all_records),
            "fetch_timestamp": datetime.now(datetime.UTC).isoformat(),
            "records": all_records,
        }
        result["sha256"] = sha256_of_json(all_records)

        out_path = OUT_DIR / f"{name}.json"
        out_path.write_text(json.dumps(output, indent=2, default=str))

        # Find latest non-null value
        latest_year = None
        latest_val = None
        for r in all_records:
            if r.get("value") is not None:
                latest_year = r.get("date")
                latest_val = r["value"]
                break

        print(
            f"OK | {len(all_records)} records | "
            f"latest: {latest_year}={latest_val}"
        )

    except httpx.HTTPStatusError as e:
        result["status"] = "http_error"
        result["error"] = f"HTTP {e.response.status_code}"
        print(f"FAIL | HTTP {e.response.status_code}")
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)[:200]
        print(f"FAIL | {e!s:.60}")

    return result


def main() -> int:
    """Fetch all WDI indicators."""
    print("=== World Bank WDI — Full Fetch ===\n")
    print(f"Country: SAU | Date range: {DATE_RANGE}\n")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    dataset_results: dict[str, dict] = {}

    with httpx.Client(follow_redirects=True) as client:
        for name, config in INDICATORS.items():
            r = fetch_indicator(client, name, config)
            dataset_results[name] = r
            time.sleep(DELAY)

    # Metadata
    metadata = {
        "source": "World Bank WDI",
        "base_url": BASE_URL,
        "country": "SAU",
        "fetch_timestamp": datetime.now(datetime.UTC).isoformat(),
        "datasets": {
            name: {
                "indicator": r.get("indicator"),
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
    print(f"\n--- {ok}/{len(dataset_results)} indicators fetched ---")
    return 0 if ok > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
