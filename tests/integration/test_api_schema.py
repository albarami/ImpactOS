"""API schema compliance — all module outputs serialize cleanly."""

import pytest
from uuid_extensions import uuid7

from src.models.scenario import ScenarioSpec, TimeHorizon
from src.models.run import RunSnapshot, ResultSet


@pytest.mark.integration
class TestAPISchemaCompliance:
    """Pydantic models serialize/deserialize cleanly."""

    def test_scenario_spec_round_trip(self):
        """ScenarioSpec -> JSON -> ScenarioSpec."""
        spec = ScenarioSpec(
            name="Test Scenario",
            workspace_id=uuid7(),
            base_model_version_id=uuid7(),
            base_year=2024,
            time_horizon=TimeHorizon(start_year=2024, end_year=2026),
        )
        json_str = spec.model_dump_json()
        restored = ScenarioSpec.model_validate_json(json_str)
        assert restored.name == spec.name
        assert restored.scenario_spec_id == spec.scenario_spec_id

    def test_run_snapshot_round_trip(self):
        """RunSnapshot -> JSON -> RunSnapshot."""
        snap = RunSnapshot(
            run_id=uuid7(),
            model_version_id=uuid7(),
            taxonomy_version_id=uuid7(),
            concordance_version_id=uuid7(),
            mapping_library_version_id=uuid7(),
            assumption_library_version_id=uuid7(),
            prompt_pack_version_id=uuid7(),
        )
        json_str = snap.model_dump_json()
        restored = RunSnapshot.model_validate_json(json_str)
        assert restored.run_id == snap.run_id

    def test_result_set_round_trip(self):
        """ResultSet -> JSON -> ResultSet."""
        rs = ResultSet(
            run_id=uuid7(),
            metric_type="total_output",
            values={"total": 1234.56},
            sector_breakdowns={"C": {"total": 500.0}},
        )
        json_str = rs.model_dump_json()
        restored = ResultSet.model_validate_json(json_str)
        assert restored.metric_type == "total_output"
