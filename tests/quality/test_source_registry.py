"""Tests for source freshness registry (MVP-13, Task 6).

Covers: DataSource creation, SourceFreshnessRegistry CRUD operations,
staleness detection, SourceAge conversion, and seed defaults.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.quality.models import SourceAge, SourceUpdateFrequency
from src.quality.source_registry import DataSource, SourceFreshnessRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc(year: int, month: int = 1, day: int = 1) -> datetime:
    """Shorthand for timezone-aware UTC datetime."""
    return datetime(year, month, day, tzinfo=timezone.utc)


# ===================================================================
# DataSource creation and field access
# ===================================================================


class TestDataSourceCreation:
    """DataSource can be constructed and fields accessed."""

    def test_create_minimal(self) -> None:
        ds = DataSource(
            name="Test Source",
            source_type="benchmark",
            provider="TestProvider",
            last_updated=_utc(2025, 1, 1),
            last_checked=_utc(2025, 1, 1),
            expected_update_frequency=SourceUpdateFrequency.ANNUAL,
        )
        assert ds.name == "Test Source"
        assert ds.source_type == "benchmark"
        assert ds.provider == "TestProvider"
        assert ds.last_updated == _utc(2025, 1, 1)
        assert ds.last_checked == _utc(2025, 1, 1)
        assert ds.expected_update_frequency == SourceUpdateFrequency.ANNUAL

    def test_source_id_auto_generated(self) -> None:
        ds = DataSource(
            name="Auto ID",
            source_type="io_table",
            provider="GASTAT",
            last_updated=_utc(2024),
            last_checked=_utc(2024),
            expected_update_frequency=SourceUpdateFrequency.QUINQUENNIAL,
        )
        assert ds.source_id is not None

    def test_optional_fields_default_none(self) -> None:
        ds = DataSource(
            name="No URL",
            source_type="inflation",
            provider="SAMA",
            last_updated=_utc(2025),
            last_checked=_utc(2025),
            expected_update_frequency=SourceUpdateFrequency.QUARTERLY,
        )
        assert ds.url is None
        assert ds.notes is None

    def test_optional_fields_set(self) -> None:
        ds = DataSource(
            name="With URL",
            source_type="employment",
            provider="ILO",
            last_updated=_utc(2025),
            last_checked=_utc(2025),
            expected_update_frequency=SourceUpdateFrequency.ANNUAL,
            url="https://ilostat.ilo.org",
            notes="ILO employment stats",
        )
        assert ds.url == "https://ilostat.ilo.org"
        assert ds.notes == "ILO employment stats"


# ===================================================================
# SourceFreshnessRegistry: register + get
# ===================================================================


class TestRegistryRegisterAndGet:
    """Register and get operations on SourceFreshnessRegistry."""

    def test_register_and_get(self) -> None:
        reg = SourceFreshnessRegistry()
        ds = DataSource(
            name="Test",
            source_type="benchmark",
            provider="P",
            last_updated=_utc(2025),
            last_checked=_utc(2025),
            expected_update_frequency=SourceUpdateFrequency.ANNUAL,
        )
        reg.register(ds)
        result = reg.get("Test")
        assert result is not None
        assert result.name == "Test"
        assert result.provider == "P"

    def test_get_returns_none_for_unknown(self) -> None:
        reg = SourceFreshnessRegistry()
        assert reg.get("nonexistent") is None

    def test_get_all_returns_all_registered(self) -> None:
        reg = SourceFreshnessRegistry()
        for i in range(3):
            ds = DataSource(
                name=f"Source {i}",
                source_type="benchmark",
                provider="P",
                last_updated=_utc(2025),
                last_checked=_utc(2025),
                expected_update_frequency=SourceUpdateFrequency.ANNUAL,
            )
            reg.register(ds)
        all_sources = reg.get_all()
        assert len(all_sources) == 3
        names = {s.name for s in all_sources}
        assert names == {"Source 0", "Source 1", "Source 2"}

    def test_get_all_empty_registry(self) -> None:
        reg = SourceFreshnessRegistry()
        assert reg.get_all() == []


# ===================================================================
# SourceFreshnessRegistry: update_timestamp
# ===================================================================


class TestRegistryUpdateTimestamp:
    """update_timestamp updates both last_updated and last_checked."""

    def test_update_timestamp_updates_both_fields(self) -> None:
        reg = SourceFreshnessRegistry()
        ds = DataSource(
            name="Updatable",
            source_type="inflation",
            provider="SAMA",
            last_updated=_utc(2024, 6, 1),
            last_checked=_utc(2024, 6, 1),
            expected_update_frequency=SourceUpdateFrequency.QUARTERLY,
        )
        reg.register(ds)

        new_time = _utc(2025, 3, 15)
        reg.update_timestamp("Updatable", new_time)

        updated = reg.get("Updatable")
        assert updated is not None
        assert updated.last_updated == new_time
        # last_checked should also be updated (to approximately now)
        assert updated.last_checked >= new_time

    def test_update_timestamp_raises_for_unknown(self) -> None:
        reg = SourceFreshnessRegistry()
        with pytest.raises(KeyError):
            reg.update_timestamp("ghost", _utc(2025))


# ===================================================================
# SourceFreshnessRegistry: get_stale_sources
# ===================================================================


class TestRegistryGetStaleSources:
    """get_stale_sources identifies sources exceeding cadence * 1.5."""

    def test_stale_annual_source(self) -> None:
        """Annual source updated 600 days ago is stale (600 > 365 * 1.5 = 547.5)."""
        reg = SourceFreshnessRegistry()
        ds = DataSource(
            name="Old Annual",
            source_type="benchmark",
            provider="P",
            last_updated=_utc(2024, 1, 1),
            last_checked=_utc(2024, 1, 1),
            expected_update_frequency=SourceUpdateFrequency.ANNUAL,
        )
        reg.register(ds)

        # 600 days after 2024-01-01
        as_of = datetime(2025, 8, 24, tzinfo=timezone.utc)
        stale = reg.get_stale_sources(as_of)
        assert len(stale) == 1
        assert stale[0].name == "Old Annual"

    def test_fresh_annual_source_not_stale(self) -> None:
        """Annual source updated 200 days ago is NOT stale (200 < 547.5)."""
        reg = SourceFreshnessRegistry()
        ds = DataSource(
            name="Fresh Annual",
            source_type="benchmark",
            provider="P",
            last_updated=_utc(2025, 1, 1),
            last_checked=_utc(2025, 1, 1),
            expected_update_frequency=SourceUpdateFrequency.ANNUAL,
        )
        reg.register(ds)

        as_of = datetime(2025, 7, 20, tzinfo=timezone.utc)
        stale = reg.get_stale_sources(as_of)
        assert len(stale) == 0

    def test_stale_quarterly_source(self) -> None:
        """Quarterly source updated 150 days ago is stale (150 > 90 * 1.5 = 135)."""
        reg = SourceFreshnessRegistry()
        ds = DataSource(
            name="Old Quarterly",
            source_type="inflation",
            provider="SAMA",
            last_updated=_utc(2025, 1, 1),
            last_checked=_utc(2025, 1, 1),
            expected_update_frequency=SourceUpdateFrequency.QUARTERLY,
        )
        reg.register(ds)

        as_of = datetime(2025, 5, 31, tzinfo=timezone.utc)
        stale = reg.get_stale_sources(as_of)
        assert len(stale) == 1
        assert stale[0].name == "Old Quarterly"

    def test_per_engagement_never_stale(self) -> None:
        """PER_ENGAGEMENT sources are never considered stale."""
        reg = SourceFreshnessRegistry()
        ds = DataSource(
            name="Engagement Only",
            source_type="occupation_bridge",
            provider="Expert",
            last_updated=_utc(2020, 1, 1),
            last_checked=_utc(2020, 1, 1),
            expected_update_frequency=SourceUpdateFrequency.PER_ENGAGEMENT,
        )
        reg.register(ds)

        as_of = _utc(2026, 1, 1)
        stale = reg.get_stale_sources(as_of)
        assert len(stale) == 0

    def test_stale_quinquennial_source(self) -> None:
        """Quinquennial updated 2800 days ago is stale (2800 > 1825 * 1.5 = 2737.5)."""
        reg = SourceFreshnessRegistry()
        ds = DataSource(
            name="Very Old Table",
            source_type="io_table",
            provider="GASTAT",
            last_updated=_utc(2018, 6, 1),
            last_checked=_utc(2018, 6, 1),
            expected_update_frequency=SourceUpdateFrequency.QUINQUENNIAL,
        )
        reg.register(ds)

        as_of = datetime(2026, 2, 15, tzinfo=timezone.utc)
        stale = reg.get_stale_sources(as_of)
        assert len(stale) == 1

    def test_mixed_stale_and_fresh(self) -> None:
        """Only stale sources returned from a mixed registry."""
        reg = SourceFreshnessRegistry()

        # Stale: 600 days old, annual threshold = 547.5
        reg.register(
            DataSource(
                name="Stale",
                source_type="benchmark",
                provider="P",
                last_updated=_utc(2024, 1, 1),
                last_checked=_utc(2024, 1, 1),
                expected_update_frequency=SourceUpdateFrequency.ANNUAL,
            )
        )
        # Fresh: 100 days old, annual threshold = 547.5
        reg.register(
            DataSource(
                name="Fresh",
                source_type="benchmark",
                provider="P",
                last_updated=_utc(2025, 5, 1),
                last_checked=_utc(2025, 5, 1),
                expected_update_frequency=SourceUpdateFrequency.ANNUAL,
            )
        )
        # PER_ENGAGEMENT: never stale
        reg.register(
            DataSource(
                name="Engagement",
                source_type="occupation_bridge",
                provider="Expert",
                last_updated=_utc(2020),
                last_checked=_utc(2020),
                expected_update_frequency=SourceUpdateFrequency.PER_ENGAGEMENT,
            )
        )

        as_of = datetime(2025, 8, 24, tzinfo=timezone.utc)
        stale = reg.get_stale_sources(as_of)
        assert len(stale) == 1
        assert stale[0].name == "Stale"


# ===================================================================
# SourceFreshnessRegistry: to_source_ages
# ===================================================================


class TestRegistryToSourceAges:
    """to_source_ages converts all sources to SourceAge instances."""

    def test_correct_age_days(self) -> None:
        reg = SourceFreshnessRegistry()
        ds = DataSource(
            name="Age Test",
            source_type="benchmark",
            provider="P",
            last_updated=_utc(2025, 1, 1),
            last_checked=_utc(2025, 1, 1),
            expected_update_frequency=SourceUpdateFrequency.ANNUAL,
        )
        reg.register(ds)

        as_of = datetime(2025, 4, 11, tzinfo=timezone.utc)  # 100 days later
        ages = reg.to_source_ages(as_of)
        assert len(ages) == 1
        assert ages[0].source_name == "Age Test"
        assert abs(ages[0].age_days - 100.0) < 0.01
        assert ages[0].expected_frequency == SourceUpdateFrequency.ANNUAL

    def test_includes_all_sources(self) -> None:
        reg = SourceFreshnessRegistry()
        for i in range(5):
            reg.register(
                DataSource(
                    name=f"Src {i}",
                    source_type="benchmark",
                    provider="P",
                    last_updated=_utc(2025),
                    last_checked=_utc(2025),
                    expected_update_frequency=SourceUpdateFrequency.ANNUAL,
                )
            )
        ages = reg.to_source_ages(_utc(2026))
        assert len(ages) == 5
        names = {a.source_name for a in ages}
        assert names == {f"Src {i}" for i in range(5)}

    def test_source_age_is_immutable(self) -> None:
        reg = SourceFreshnessRegistry()
        reg.register(
            DataSource(
                name="Immutable",
                source_type="benchmark",
                provider="P",
                last_updated=_utc(2025),
                last_checked=_utc(2025),
                expected_update_frequency=SourceUpdateFrequency.ANNUAL,
            )
        )
        ages = reg.to_source_ages(_utc(2026))
        assert isinstance(ages[0], SourceAge)


# ===================================================================
# SourceFreshnessRegistry: with_seed_defaults
# ===================================================================


class TestRegistryWithSeedDefaults:
    """with_seed_defaults creates registry pre-populated with seed sources."""

    def test_seed_has_at_least_six_sources(self) -> None:
        reg = SourceFreshnessRegistry.with_seed_defaults()
        assert len(reg.get_all()) >= 6

    def test_seed_has_eight_sources(self) -> None:
        reg = SourceFreshnessRegistry.with_seed_defaults()
        assert len(reg.get_all()) == 8

    def test_seed_has_expected_source_names(self) -> None:
        reg = SourceFreshnessRegistry.with_seed_defaults()
        names = {s.name for s in reg.get_all()}
        expected = {
            "Saudi IO Table",
            "KAPSARC Multiplier Benchmarks",
            "World Development Indicators",
            "ILOSTAT Employment Data",
            "SAMA Inflation Data",
            "Employment Coefficients (D-4)",
            "Occupation Bridge",
            "Nationality Classifications",
        }
        assert expected == names

    def test_seed_saudi_io_table_properties(self) -> None:
        reg = SourceFreshnessRegistry.with_seed_defaults()
        ds = reg.get("Saudi IO Table")
        assert ds is not None
        assert ds.source_type == "io_table"
        assert ds.provider == "GASTAT"
        assert ds.expected_update_frequency == SourceUpdateFrequency.QUINQUENNIAL

    def test_seed_per_engagement_sources(self) -> None:
        reg = SourceFreshnessRegistry.with_seed_defaults()
        occupation = reg.get("Occupation Bridge")
        nationality = reg.get("Nationality Classifications")
        assert occupation is not None
        assert nationality is not None
        assert (
            occupation.expected_update_frequency
            == SourceUpdateFrequency.PER_ENGAGEMENT
        )
        assert (
            nationality.expected_update_frequency
            == SourceUpdateFrequency.PER_ENGAGEMENT
        )

    def test_seed_sources_have_last_checked_equals_last_updated(self) -> None:
        reg = SourceFreshnessRegistry.with_seed_defaults()
        for source in reg.get_all():
            assert source.last_checked == source.last_updated
