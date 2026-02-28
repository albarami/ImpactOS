"""Data source registry — tracks external data sources and their status.

Provides a lightweight catalog of all configured external data sources,
their fetch status, and metadata. Used by the engine and UI to know
what data is available.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class SourceStatus(StrEnum):
    """Status of a data source."""

    NOT_FETCHED = "not_fetched"
    FETCHED = "fetched"
    STALE = "stale"
    ERROR = "error"


@dataclass(frozen=True)
class FetchMetadata:
    """Metadata from the most recent fetch of a source."""

    source_id: str
    fetch_timestamp: str
    record_count: int
    sha256: str
    status: str
    error: str | None = None


@dataclass(frozen=True)
class SourceInfo:
    """Information about a configured data source."""

    source_id: str
    label: str
    provider: str
    raw_dir: str
    description: str
    status: SourceStatus
    last_fetch: FetchMetadata | None = None


# Source catalog — all known external data sources
_SOURCE_CATALOG: dict[str, dict] = {
    "kapsarc_io": {
        "label": "KAPSARC IO Table",
        "provider": "KAPSARC Data Portal",
        "raw_dir": "data/raw/kapsarc",
        "metadata_key": "io_current_prices",
        "description": "Saudi IO table at current prices (division-level)",
    },
    "kapsarc_multipliers": {
        "label": "KAPSARC Type I Multipliers",
        "provider": "KAPSARC Data Portal",
        "raw_dir": "data/raw/kapsarc",
        "metadata_key": "type1_multipliers",
        "description": "Published Type I output multipliers",
    },
    "kapsarc_gdp": {
        "label": "KAPSARC GDP by Activity",
        "provider": "KAPSARC Data Portal",
        "raw_dir": "data/raw/kapsarc",
        "metadata_key": "gdp_by_activity",
        "description": "GDP by economic activity (current prices)",
    },
    "wdi_gdp": {
        "label": "WDI GDP (current US$)",
        "provider": "World Bank",
        "raw_dir": "data/raw/worldbank",
        "metadata_key": "sau_gdp_current_usd",
        "description": "Saudi GDP in current US dollars",
    },
    "wdi_deflator": {
        "label": "WDI GDP Deflator",
        "provider": "World Bank",
        "raw_dir": "data/raw/worldbank",
        "metadata_key": "sau_gdp_deflator",
        "description": "GDP deflator for real/nominal conversion",
    },
    "wdi_trade": {
        "label": "WDI Trade (% of GDP)",
        "provider": "World Bank",
        "raw_dir": "data/raw/worldbank",
        "metadata_key": "sau_trade_pct_gdp",
        "description": "Trade as percentage of GDP",
    },
    "ilo_employment": {
        "label": "ILO Employment by Activity",
        "provider": "ILOSTAT",
        "raw_dir": "data/raw/ilo",
        "metadata_key": "sau_employment_by_activity",
        "description": "Employment by ISIC Rev.4 economic activity",
    },
    "sama_cpi": {
        "label": "SAMA CPI / Deflators",
        "provider": "SAMA",
        "raw_dir": "data/raw/sama",
        "metadata_key": None,
        "description": "Consumer price index and sector deflators",
    },
}


class DataSourceRegistry:
    """Registry of external data sources and their availability."""

    def __init__(self, base_dir: str | Path = ".") -> None:
        self._base = Path(base_dir)

    def get_source_status(self, source_id: str) -> SourceStatus:
        """Check if a source has been fetched and is current."""
        fetch = self.get_latest_fetch(source_id)
        if fetch is None:
            return SourceStatus.NOT_FETCHED
        if fetch.status != "success":
            return SourceStatus.ERROR
        return SourceStatus.FETCHED

    def get_latest_fetch(self, source_id: str) -> FetchMetadata | None:
        """Get metadata from most recent fetch of a source."""
        if source_id not in _SOURCE_CATALOG:
            return None

        config = _SOURCE_CATALOG[source_id]
        raw_dir = self._base / config["raw_dir"]
        meta_path = raw_dir / "_metadata.json"

        if not meta_path.exists():
            return None

        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

        # Look up the specific dataset in the metadata
        datasets = meta.get("datasets", {})
        key = config.get("metadata_key")

        if key and key in datasets:
            ds = datasets[key]
            return FetchMetadata(
                source_id=source_id,
                fetch_timestamp=meta.get("fetch_timestamp", ""),
                record_count=ds.get("record_count", 0),
                sha256=ds.get("sha256", ""),
                status=ds.get("status", "unknown"),
                error=ds.get("error"),
            )

        # No specific dataset match — check top-level
        return FetchMetadata(
            source_id=source_id,
            fetch_timestamp=meta.get("fetch_timestamp", ""),
            record_count=0,
            sha256="",
            status=meta.get("api_status", "unknown"),
            error=None,
        )

    def list_available_sources(self) -> list[SourceInfo]:
        """List all configured sources and their status."""
        sources: list[SourceInfo] = []

        for source_id, config in _SOURCE_CATALOG.items():
            status = self.get_source_status(source_id)
            fetch = self.get_latest_fetch(source_id)

            sources.append(SourceInfo(
                source_id=source_id,
                label=config["label"],
                provider=config["provider"],
                raw_dir=config["raw_dir"],
                description=config["description"],
                status=status,
                last_fetch=fetch,
            ))

        return sources

    def get_fetched_sources(self) -> list[SourceInfo]:
        """List only sources that have been successfully fetched."""
        return [
            s for s in self.list_available_sources()
            if s.status == SourceStatus.FETCHED
        ]

    def summary(self) -> str:
        """Return a human-readable summary of all sources."""
        lines: list[str] = ["Data Source Registry:"]
        for info in self.list_available_sources():
            icon = {
                SourceStatus.FETCHED: "\u2705",
                SourceStatus.NOT_FETCHED: "\u23f3",
                SourceStatus.STALE: "\u26a0\ufe0f",
                SourceStatus.ERROR: "\u274c",
            }.get(info.status, "?")
            lines.append(f"  {icon} {info.label}: {info.status.value}")
        return "\n".join(lines)
