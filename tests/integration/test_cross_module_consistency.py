"""Cross-module consistency — shared vocabulary, types, and confidence enums.

Amendment 8: Tests concordance contracts and confidence vocabulary.

Confidence Vocabulary (5 enums across the codebase):
  1. ConstraintConfidence:      HARD / ESTIMATED / ASSUMED    (src/models/common.py)
  2. MappingConfidenceBand:     HIGH / MEDIUM / LOW           (src/models/common.py)
  3. WorkforceConfidenceLevel:  HIGH / MEDIUM / LOW           (src/models/workforce.py)
  4. QualityConfidence:         high / medium / low  LOWERCASE (src/data/workforce/unit_registry.py)
  5. ConfidenceBand:            HIGH / MEDIUM / LOW           (src/compiler/confidence.py)

Normalization: workforce pipeline normalizes via confidence_to_str() -> uppercase.
Quality scorer expects uppercase "HIGH"/"MEDIUM"/"LOW".
"""

import pytest

from src.models.common import ConstraintConfidence, ExportMode, MappingConfidenceBand


@pytest.mark.integration
class TestCrossModuleConsistency:
    """Shared enums and types across modules."""

    def test_constraint_confidence_enum_shared(self):
        """MVP-10 and MVP-13 use same ConstraintConfidence enum."""
        assert hasattr(ConstraintConfidence, "HARD")
        assert hasattr(ConstraintConfidence, "ESTIMATED")
        assert hasattr(ConstraintConfidence, "ASSUMED")

    def test_mapping_confidence_band_shared(self):
        """Compiler and quality use same MappingConfidenceBand."""
        assert hasattr(MappingConfidenceBand, "HIGH")
        assert hasattr(MappingConfidenceBand, "MEDIUM")
        assert hasattr(MappingConfidenceBand, "LOW")

    def test_export_mode_shared(self):
        """Export and governance use same ExportMode enum."""
        assert hasattr(ExportMode, "SANDBOX")
        assert hasattr(ExportMode, "GOVERNED")

    def test_uuid7_used_for_new_ids(self):
        """new_uuid7 produces valid UUIDv7."""
        from src.models.common import new_uuid7
        uid = new_uuid7()
        assert uid.version == 7

    def test_run_snapshot_has_expected_version_fields(self):
        """RunSnapshot has all expected version ID fields (Amendment 10)."""
        from src.models.run import RunSnapshot
        fields = RunSnapshot.model_fields
        assert "model_version_id" in fields
        assert "mapping_library_version_id" in fields
        assert "assumption_library_version_id" in fields
        # Optional fields
        assert "constraint_set_version_id" in fields
        assert "occupation_bridge_version_id" in fields
        assert "nationality_classification_version_id" in fields


@pytest.mark.integration
class TestConfidenceVocabulary:
    """Verify all 5 confidence enums and cross-module normalization."""

    def test_constraint_confidence_values_uppercase(self):
        """ConstraintConfidence values are uppercase: HARD, ESTIMATED, ASSUMED."""
        assert ConstraintConfidence.HARD.value == "HARD"
        assert ConstraintConfidence.ESTIMATED.value == "ESTIMATED"
        assert ConstraintConfidence.ASSUMED.value == "ASSUMED"

    def test_mapping_confidence_band_values_uppercase(self):
        """MappingConfidenceBand values are uppercase: HIGH, MEDIUM, LOW."""
        assert MappingConfidenceBand.HIGH.value == "HIGH"
        assert MappingConfidenceBand.MEDIUM.value == "MEDIUM"
        assert MappingConfidenceBand.LOW.value == "LOW"

    def test_workforce_confidence_level_values_uppercase(self):
        """WorkforceConfidenceLevel values are uppercase: HIGH, MEDIUM, LOW."""
        from src.models.workforce import WorkforceConfidenceLevel
        assert WorkforceConfidenceLevel.HIGH.value == "HIGH"
        assert WorkforceConfidenceLevel.MEDIUM.value == "MEDIUM"
        assert WorkforceConfidenceLevel.LOW.value == "LOW"

    def test_quality_confidence_values_lowercase(self):
        """QualityConfidence values are LOWERCASE: high, medium, low."""
        from src.data.workforce.unit_registry import QualityConfidence
        assert QualityConfidence.HIGH.value == "high"
        assert QualityConfidence.MEDIUM.value == "medium"
        assert QualityConfidence.LOW.value == "low"

    def test_compiler_confidence_band_values_uppercase(self):
        """ConfidenceBand (compiler) values are uppercase: HIGH, MEDIUM, LOW."""
        from src.compiler.confidence import ConfidenceBand
        assert ConfidenceBand.HIGH.value == "HIGH"
        assert ConfidenceBand.MEDIUM.value == "MEDIUM"
        assert ConfidenceBand.LOW.value == "LOW"

    def test_confidence_to_str_normalizes_quality_confidence_to_uppercase(self):
        """confidence_to_str() converts QualityConfidence lowercase -> uppercase."""
        from src.data.workforce.unit_registry import QualityConfidence
        from src.engine.workforce_satellite.config import confidence_to_str

        assert confidence_to_str(QualityConfidence.HIGH) == "HIGH"
        assert confidence_to_str(QualityConfidence.MEDIUM) == "MEDIUM"
        assert confidence_to_str(QualityConfidence.LOW) == "LOW"

    def test_confidence_to_str_preserves_constraint_confidence(self):
        """confidence_to_str() preserves ConstraintConfidence uppercase."""
        from src.engine.workforce_satellite.config import confidence_to_str

        assert confidence_to_str(ConstraintConfidence.HARD) == "HARD"
        assert confidence_to_str(ConstraintConfidence.ESTIMATED) == "ESTIMATED"
        assert confidence_to_str(ConstraintConfidence.ASSUMED) == "ASSUMED"

    def test_confidence_to_str_handles_raw_strings(self):
        """confidence_to_str() uppercases raw string inputs."""
        from src.engine.workforce_satellite.config import confidence_to_str

        assert confidence_to_str("high") == "HIGH"
        assert confidence_to_str("Medium") == "MEDIUM"
        assert confidence_to_str("LOW") == "LOW"

    def test_quality_scorer_accepts_uppercase(self):
        """QualityAssessmentService.assess() accepts uppercase confidence strings."""
        from uuid_extensions import uuid7

        from src.quality.service import QualityAssessmentService

        qas = QualityAssessmentService()
        # Should NOT raise when given uppercase confidence strings
        assessment = qas.assess(
            base_year=2024, current_year=2026,
            mapping_coverage_pct=0.90,
            mapping_confidence_dist={"HIGH": 0.6, "MEDIUM": 0.3, "LOW": 0.1},
            mapping_residual_pct=0.05, mapping_unresolved_pct=0.03,
            mapping_unresolved_spend_pct=1.5,
            assumption_ranges_coverage_pct=0.7, assumption_approval_rate=0.8,
            constraint_confidence_summary={"HARD": 3, "ESTIMATED": 3, "ASSUMED": 2},
            workforce_overall_confidence="HIGH",
            plausibility_in_range_pct=85.0, plausibility_flagged_count=2,
            source_ages=[], run_id=uuid7(),
        )
        assert assessment.assessment_id is not None
