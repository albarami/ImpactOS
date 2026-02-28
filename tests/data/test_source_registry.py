"""Tests for DataSourceRegistry (D-3).

Tests registry behavior with and without fetched data.
No live API calls.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.data.source_registry import (
    DataSourceRegistry,
    FetchMetadata,
    SourceInfo,
    SourceStatus,
)


class TestDataSourceRegistry:
    """Registry correctly tracks source availability."""

    def test_empty_registry(self, tmp_path: Path) -> None:
        """No data dir -> all sources NOT_FETCHED."""
        reg = DataSourceRegistry(base_dir=tmp_path)
        status = reg.get_source_status("kapsarc_io")
        assert status == SourceStatus.NOT_FETCHED

    def test_list_all_sources(self, tmp_path: Path) -> None:
        """Lists all configured sources."""
        reg = DataSourceRegistry(base_dir=tmp_path)
        sources = reg.list_available_sources()
        assert len(sources) >= 8
        ids = {s.source_id for s in sources}
        assert "kapsarc_io" in ids
        assert "wdi_gdp" in ids
        assert "ilo_employment" in ids

    def test_source_info_type(self, tmp_path: Path) -> None:
        """Each source is SourceInfo."""
        reg = DataSourceRegistry(base_dir=tmp_path)
        sources = reg.list_available_sources()
        assert isinstance(sources[0], SourceInfo)

    def test_fetched_status_with_metadata(self, tmp_path: Path) -> None:
        """Source with valid metadata -> FETCHED."""
        kapsarc_dir = tmp_path / "data" / "raw" / "kapsarc"
        kapsarc_dir.mkdir(parents=True)
        meta = {
            "source": "KAPSARC",
            "fetch_timestamp": "2026-02-28T12:00:00Z",
            "datasets": {
                "io_current_prices": {
                    "record_count": 47,
                    "sha256": "sha256:abc123",
                    "status": "success",
                },
            },
        }
        (kapsarc_dir / "_metadata.json").write_text(json.dumps(meta))

        reg = DataSourceRegistry(base_dir=tmp_path)
        status = reg.get_source_status("kapsarc_io")
        assert status == SourceStatus.FETCHED

    def test_error_status(self, tmp_path: Path) -> None:
        """Source with error status -> ERROR."""
        kapsarc_dir = tmp_path / "data" / "raw" / "kapsarc"
        kapsarc_dir.mkdir(parents=True)
        meta = {
            "source": "KAPSARC",
            "fetch_timestamp": "2026-02-28T12:00:00Z",
            "datasets": {
                "io_current_prices": {
                    "record_count": 0,
                    "sha256": "",
                    "status": "http_error",
                    "error": "HTTP 500",
                },
            },
        }
        (kapsarc_dir / "_metadata.json").write_text(json.dumps(meta))

        reg = DataSourceRegistry(base_dir=tmp_path)
        status = reg.get_source_status("kapsarc_io")
        assert status == SourceStatus.ERROR

    def test_get_latest_fetch(self, tmp_path: Path) -> None:
        """Fetch metadata extracted correctly."""
        kapsarc_dir = tmp_path / "data" / "raw" / "kapsarc"
        kapsarc_dir.mkdir(parents=True)
        meta = {
            "source": "KAPSARC",
            "fetch_timestamp": "2026-02-28T12:00:00Z",
            "datasets": {
                "io_current_prices": {
                    "record_count": 47,
                    "sha256": "sha256:abc123",
                    "status": "success",
                },
            },
        }
        (kapsarc_dir / "_metadata.json").write_text(json.dumps(meta))

        reg = DataSourceRegistry(base_dir=tmp_path)
        fetch = reg.get_latest_fetch("kapsarc_io")
        assert fetch is not None
        assert isinstance(fetch, FetchMetadata)
        assert fetch.record_count == 47
        assert fetch.status == "success"

    def test_unknown_source_returns_none(self, tmp_path: Path) -> None:
        """Unknown source ID returns None."""
        reg = DataSourceRegistry(base_dir=tmp_path)
        assert reg.get_latest_fetch("nonexistent") is None

    def test_get_fetched_sources(self, tmp_path: Path) -> None:
        """Only fetched sources returned."""
        kapsarc_dir = tmp_path / "data" / "raw" / "kapsarc"
        kapsarc_dir.mkdir(parents=True)
        meta = {
            "source": "KAPSARC",
            "fetch_timestamp": "2026-02-28T12:00:00Z",
            "datasets": {
                "io_current_prices": {
                    "record_count": 47,
                    "sha256": "sha256:abc",
                    "status": "success",
                },
            },
        }
        (kapsarc_dir / "_metadata.json").write_text(json.dumps(meta))

        reg = DataSourceRegistry(base_dir=tmp_path)
        fetched = reg.get_fetched_sources()
        assert len(fetched) >= 1
        assert any(s.source_id == "kapsarc_io" for s in fetched)

    def test_summary_string(self, tmp_path: Path) -> None:
        """Summary produces non-empty string."""
        reg = DataSourceRegistry(base_dir=tmp_path)
        s = reg.summary()
        assert "Data Source Registry" in s
        assert len(s) > 50
