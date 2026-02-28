"""Tests for ScenarioPatternService (MVP-12)."""

import pytest
from uuid_extensions import uuid7

from src.models.libraries import ScenarioPattern


def _make_pattern(
    name: str = "Mega construction",
    sectors: list[str] | None = None,
    shocks: list[str] | None = None,
    tags: list[str] | None = None,
    usage: int = 0,
) -> ScenarioPattern:
    return ScenarioPattern(
        workspace_id=uuid7(),
        name=name,
        sector_focus=sectors or ["F"],
        typical_shock_types=shocks or ["FINAL_DEMAND"],
        tags=tags or [],
        usage_count=usage,
    )


class TestScenarioPatternService:
    def test_add_pattern(self) -> None:
        from src.libraries.scenario_patterns import ScenarioPatternService

        svc = ScenarioPatternService([])
        p = _make_pattern()
        result = svc.add_pattern(p)
        assert result.pattern_id == p.pattern_id
        assert len(svc._patterns) == 1

    def test_find_by_sector_codes(self) -> None:
        from src.libraries.scenario_patterns import ScenarioPatternService

        patterns = [
            _make_pattern("Construction", sectors=["F", "C"]),
            _make_pattern("IT project", sectors=["J"]),
        ]
        svc = ScenarioPatternService(patterns)
        results = svc.find_patterns(sector_codes=["F"])
        assert len(results) == 1
        assert results[0].name == "Construction"

    def test_find_by_shock_types(self) -> None:
        from src.libraries.scenario_patterns import ScenarioPatternService

        patterns = [
            _make_pattern("Construction", shocks=["FINAL_DEMAND"]),
            _make_pattern("Policy", shocks=["IMPORT_SUB", "LOCAL_CONTENT"]),
        ]
        svc = ScenarioPatternService(patterns)
        results = svc.find_patterns(shock_types=["IMPORT_SUB"])
        assert len(results) == 1
        assert results[0].name == "Policy"

    def test_find_by_tags(self) -> None:
        from src.libraries.scenario_patterns import ScenarioPatternService

        patterns = [
            _make_pattern("Construction", tags=["infrastructure"]),
            _make_pattern("Mining", tags=["mining", "resources"]),
        ]
        svc = ScenarioPatternService(patterns)
        results = svc.find_patterns(tags=["mining"])
        assert len(results) == 1

    def test_find_combined_filters(self) -> None:
        from src.libraries.scenario_patterns import ScenarioPatternService

        patterns = [
            _make_pattern("Infra", sectors=["F"], shocks=["FINAL_DEMAND"]),
            _make_pattern("IT", sectors=["J"], shocks=["FINAL_DEMAND"]),
        ]
        svc = ScenarioPatternService(patterns)
        results = svc.find_patterns(
            sector_codes=["F"], shock_types=["FINAL_DEMAND"],
        )
        # Both have FINAL_DEMAND but only one has sector F
        # Should rank Infra higher
        assert results[0].name == "Infra"

    def test_find_no_match(self) -> None:
        from src.libraries.scenario_patterns import ScenarioPatternService

        patterns = [_make_pattern(sectors=["F"])]
        svc = ScenarioPatternService(patterns)
        results = svc.find_patterns(sector_codes=["Z"])
        assert len(results) == 0

    def test_find_top_k(self) -> None:
        from src.libraries.scenario_patterns import ScenarioPatternService

        patterns = [_make_pattern(f"P{i}", sectors=["F"]) for i in range(20)]
        svc = ScenarioPatternService(patterns)
        results = svc.find_patterns(sector_codes=["F"], top_k=5)
        assert len(results) <= 5

    def test_get_stats_empty(self) -> None:
        from src.libraries.scenario_patterns import ScenarioPatternService

        svc = ScenarioPatternService([])
        stats = svc.get_stats()
        assert stats.total_entries == 0

    def test_get_stats_populated(self) -> None:
        from src.libraries.scenario_patterns import ScenarioPatternService

        patterns = [
            _make_pattern("P1", sectors=["F"], usage=5),
            _make_pattern("P2", sectors=["F", "C"], usage=10),
        ]
        svc = ScenarioPatternService(patterns)
        stats = svc.get_stats()
        assert stats.total_entries == 2
        assert stats.total_usage == 15

    def test_find_returns_all_when_no_filters(self) -> None:
        from src.libraries.scenario_patterns import ScenarioPatternService

        patterns = [_make_pattern("P1"), _make_pattern("P2")]
        svc = ScenarioPatternService(patterns)
        results = svc.find_patterns()
        assert len(results) == 2

    def test_source_engagement_ids_tracked(self) -> None:
        from src.libraries.scenario_patterns import ScenarioPatternService

        eng_id = uuid7()
        p = ScenarioPattern(
            workspace_id=uuid7(),
            name="Test",
            source_engagement_ids=[eng_id],
        )
        svc = ScenarioPatternService([])
        result = svc.add_pattern(p)
        assert eng_id in result.source_engagement_ids

    def test_usage_count_increment(self) -> None:
        from src.libraries.scenario_patterns import ScenarioPatternService

        p = _make_pattern(usage=3)
        svc = ScenarioPatternService([p])
        result = svc.increment_usage(p.pattern_id)
        assert result is not None
        assert result.usage_count == 4
