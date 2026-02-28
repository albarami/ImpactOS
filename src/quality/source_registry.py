"""Source freshness registry (MVP-13, Task 6).

Tracks data sources used by the I-O engine, their update cadences,
and staleness status.  Provides seed defaults for standard Saudi
economic data sources.

Deterministic -- no LLM calls.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import Field

from src.models.common import (
    ImpactOSBase,
    UTCTimestamp,
    UUIDv7,
    new_uuid7,
    utc_now,
)
from src.quality.models import SourceAge, SourceUpdateFrequency

# ---------------------------------------------------------------------------
# Frequency -> expected days mapping
# ---------------------------------------------------------------------------

_FREQUENCY_DAYS: dict[SourceUpdateFrequency, int] = {
    SourceUpdateFrequency.QUARTERLY: 90,
    SourceUpdateFrequency.ANNUAL: 365,
    SourceUpdateFrequency.BIENNIAL: 730,
    SourceUpdateFrequency.TRIENNIAL: 1095,
    SourceUpdateFrequency.QUINQUENNIAL: 1825,
}

# ---------------------------------------------------------------------------
# DataSource model
# ---------------------------------------------------------------------------


class DataSource(ImpactOSBase):
    """A registered data source with provenance and freshness metadata."""

    source_id: UUIDv7 = Field(default_factory=new_uuid7)
    name: str
    source_type: str  # "io_table", "benchmark", "employment", "inflation", etc.
    provider: str
    last_updated: UTCTimestamp
    last_checked: UTCTimestamp
    expected_update_frequency: SourceUpdateFrequency
    url: str | None = None
    notes: str | None = None


# ---------------------------------------------------------------------------
# SourceFreshnessRegistry
# ---------------------------------------------------------------------------


class SourceFreshnessRegistry:
    """In-memory registry of data sources and their freshness status."""

    def __init__(self) -> None:
        self._sources: dict[str, DataSource] = {}

    # -- CRUD ---------------------------------------------------------------

    def register(self, source: DataSource) -> None:
        """Add a data source to the registry, keyed by name."""
        self._sources[source.name] = source

    def get(self, name: str) -> DataSource | None:
        """Look up a source by name; returns *None* if not found."""
        return self._sources.get(name)

    def get_all(self) -> list[DataSource]:
        """Return all registered data sources."""
        return list(self._sources.values())

    # -- Mutation ------------------------------------------------------------

    def update_timestamp(self, name: str, last_updated: datetime) -> None:
        """Update *last_updated* and set *last_checked* to now.

        Raises:
            KeyError: if *name* is not in the registry.
        """
        if name not in self._sources:
            raise KeyError(name)
        old = self._sources[name]
        self._sources[name] = old.model_copy(
            update={
                "last_updated": last_updated,
                "last_checked": utc_now(),
            },
        )

    # -- Staleness -----------------------------------------------------------

    def get_stale_sources(self, as_of: datetime) -> list[DataSource]:
        """Return sources whose age exceeds ``expected_cadence * 1.5``.

        ``PER_ENGAGEMENT`` sources are never considered stale.
        """
        stale: list[DataSource] = []
        for source in self._sources.values():
            if source.expected_update_frequency == SourceUpdateFrequency.PER_ENGAGEMENT:
                continue
            expected_days = _FREQUENCY_DAYS.get(source.expected_update_frequency)
            if expected_days is None:
                continue
            age_days = (as_of - source.last_updated).days
            if age_days > expected_days * 1.5:
                stale.append(source)
        return stale

    # -- Conversion ----------------------------------------------------------

    def to_source_ages(self, as_of: datetime) -> list[SourceAge]:
        """Convert all registered sources to :class:`SourceAge` instances."""
        ages: list[SourceAge] = []
        for source in self._sources.values():
            age_days = (as_of - source.last_updated).total_seconds() / 86400
            ages.append(
                SourceAge(
                    source_name=source.name,
                    age_days=age_days,
                    expected_frequency=source.expected_update_frequency,
                )
            )
        return ages

    # -- Factory -------------------------------------------------------------

    @classmethod
    def with_seed_defaults(cls) -> SourceFreshnessRegistry:
        """Create a registry pre-populated with standard Saudi data sources."""
        registry = cls()

        def _utc(year: int, month: int = 1, day: int = 1) -> datetime:
            return datetime(year, month, day, tzinfo=timezone.utc)

        seeds: list[DataSource] = [
            DataSource(
                name="Saudi IO Table",
                source_type="io_table",
                provider="GASTAT",
                last_updated=_utc(2021, 1, 1),
                last_checked=_utc(2021, 1, 1),
                expected_update_frequency=SourceUpdateFrequency.QUINQUENNIAL,
            ),
            DataSource(
                name="KAPSARC Multiplier Benchmarks",
                source_type="benchmark",
                provider="KAPSARC",
                last_updated=_utc(2025, 1, 1),
                last_checked=_utc(2025, 1, 1),
                expected_update_frequency=SourceUpdateFrequency.ANNUAL,
            ),
            DataSource(
                name="World Development Indicators",
                source_type="benchmark",
                provider="World Bank",
                last_updated=_utc(2025, 6, 1),
                last_checked=_utc(2025, 6, 1),
                expected_update_frequency=SourceUpdateFrequency.ANNUAL,
            ),
            DataSource(
                name="ILOSTAT Employment Data",
                source_type="employment",
                provider="ILO",
                last_updated=_utc(2025, 3, 1),
                last_checked=_utc(2025, 3, 1),
                expected_update_frequency=SourceUpdateFrequency.ANNUAL,
            ),
            DataSource(
                name="SAMA Inflation Data",
                source_type="inflation",
                provider="SAMA",
                last_updated=_utc(2025, 10, 1),
                last_checked=_utc(2025, 10, 1),
                expected_update_frequency=SourceUpdateFrequency.QUARTERLY,
            ),
            DataSource(
                name="Employment Coefficients (D-4)",
                source_type="employment_coefficients",
                provider="GOSI/D-4",
                last_updated=_utc(2025, 1, 1),
                last_checked=_utc(2025, 1, 1),
                expected_update_frequency=SourceUpdateFrequency.ANNUAL,
            ),
            DataSource(
                name="Occupation Bridge",
                source_type="occupation_bridge",
                provider="Expert/D-4",
                last_updated=_utc(2025, 6, 1),
                last_checked=_utc(2025, 6, 1),
                expected_update_frequency=SourceUpdateFrequency.PER_ENGAGEMENT,
            ),
            DataSource(
                name="Nationality Classifications",
                source_type="nationality_classification",
                provider="Expert/D-4",
                last_updated=_utc(2025, 6, 1),
                last_checked=_utc(2025, 6, 1),
                expected_update_frequency=SourceUpdateFrequency.PER_ENGAGEMENT,
            ),
        ]

        for seed in seeds:
            registry.register(seed)

        return registry
