"""Deterministic data quality scoring engine — MVP-13.

CRITICAL: This is deterministic engine code — NO LLM calls.
All outputs are reproducible pure functions of their inputs.

Scores data inputs on standardized dimensions, produces run-level
quality summaries, monitors source freshness. All 7 amendments applied.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID

import numpy as np

from src.models.data_quality import (
    DEFAULT_FRESHNESS_THRESHOLDS,
    DimensionScore,
    FreshnessCheck,
    FreshnessReport,
    FreshnessThresholds,
    GradeThresholds,
    InputQualityScore,
    PublicationGateMode,
    QualityDimension,
    QualityGrade,
    RunQualitySummary,
    StalenessLevel,
)

DATA_QUALITY_ENGINE_VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Amendment 2: Default dimension weights per input type
# ---------------------------------------------------------------------------

DEFAULT_DIMENSION_WEIGHTS: dict[str, dict[str, float]] = {
    "io_table": {
        "FRESHNESS": 0.15, "COMPLETENESS": 0.10, "CONFIDENCE": 0.10,
        "PROVENANCE": 0.25, "CONSISTENCY": 0.30, "STRUCTURAL_VALIDITY": 0.10,
    },
    "mapping": {
        "FRESHNESS": 0.00, "COMPLETENESS": 0.40, "CONFIDENCE": 0.20,
        "PROVENANCE": 0.30, "CONSISTENCY": 0.10, "STRUCTURAL_VALIDITY": 0.00,
    },
    "employment_coefficients": {
        "FRESHNESS": 0.20, "COMPLETENESS": 0.25, "CONFIDENCE": 0.30,
        "PROVENANCE": 0.15, "CONSISTENCY": 0.10, "STRUCTURAL_VALIDITY": 0.00,
    },
    "occupation_bridge": {
        "FRESHNESS": 0.10, "COMPLETENESS": 0.35, "CONFIDENCE": 0.30,
        "PROVENANCE": 0.15, "CONSISTENCY": 0.10, "STRUCTURAL_VALIDITY": 0.00,
    },
    "constraint_set": {
        "FRESHNESS": 0.15, "COMPLETENESS": 0.15, "CONFIDENCE": 0.30,
        "PROVENANCE": 0.30, "CONSISTENCY": 0.10, "STRUCTURAL_VALIDITY": 0.00,
    },
    "default": {
        "FRESHNESS": 0.20, "COMPLETENESS": 0.20, "CONFIDENCE": 0.20,
        "PROVENANCE": 0.20, "CONSISTENCY": 0.20, "STRUCTURAL_VALIDITY": 0.00,
    },
}

# ---------------------------------------------------------------------------
# Confidence band weights
# ---------------------------------------------------------------------------

_CONFIDENCE_WEIGHTS: dict[str, float] = {
    "hard": 1.0,
    "estimated": 0.6,
    "assumed": 0.2,
}

# ---------------------------------------------------------------------------
# Staleness severity ordering (for worst-of comparisons)
# ---------------------------------------------------------------------------

_STALENESS_SEVERITY: dict[StalenessLevel, int] = {
    StalenessLevel.CURRENT: 0,
    StalenessLevel.AGING: 1,
    StalenessLevel.STALE: 2,
    StalenessLevel.EXPIRED: 3,
}

# ---------------------------------------------------------------------------
# Core scoring functions
# ---------------------------------------------------------------------------


def score_to_grade(
    score: float,
    thresholds: GradeThresholds | None = None,
) -> QualityGrade:
    """Convert a 0-1 score to a letter grade."""
    t = thresholds or GradeThresholds()
    if score >= t.a_min:
        return QualityGrade.A
    if score >= t.b_min:
        return QualityGrade.B
    if score >= t.c_min:
        return QualityGrade.C
    if score >= t.d_min:
        return QualityGrade.D
    return QualityGrade.F


def score_freshness(
    last_updated: datetime,
    source_type: str,
    thresholds: dict[str, FreshnessThresholds] | None = None,
    reference_date: datetime | None = None,
) -> DimensionScore:
    """Score data freshness with smooth decay within bands (Amendment 4).

    Within each band, linearly interpolates between band boundaries.
    Labels (CURRENT/AGING/STALE/EXPIRED) remain discrete.
    """
    ref = reference_date or datetime.now(tz=UTC)
    if last_updated.tzinfo is None:
        last_updated = last_updated.replace(tzinfo=UTC)
    days = (ref - last_updated).days

    thresh_map = thresholds or DEFAULT_FRESHNESS_THRESHOLDS
    fallback = thresh_map.get("default", DEFAULT_FRESHNESS_THRESHOLDS["default"])
    thresh = thresh_map.get(source_type, fallback)

    # Determine band and compute smooth score (Amendment 4)
    penalties: list[str] = []
    if days < thresh.aging_days:
        band = StalenessLevel.CURRENT
        # 1.0 → 0.85 as days approach aging
        progress = days / thresh.aging_days if thresh.aging_days > 0 else 0.0
        score = 1.0 - progress * 0.15
    elif days < thresh.stale_days:
        band = StalenessLevel.AGING
        progress = (days - thresh.aging_days) / max(thresh.stale_days - thresh.aging_days, 1)
        score = 0.75 - progress * 0.20  # 0.75 → 0.55
        penalties.append(
            f"Data is {days} days old — in AGING band "
            f"({thresh.aging_days}-{thresh.stale_days} days for {source_type})",
        )
    elif days < thresh.expired_days:
        band = StalenessLevel.STALE
        progress = (days - thresh.stale_days) / max(thresh.expired_days - thresh.stale_days, 1)
        score = 0.4 - progress * 0.20  # 0.4 → 0.2
        penalties.append(
            f"Data is {days} days old — STALE "
            f"({thresh.stale_days}-{thresh.expired_days} days for {source_type})",
        )
    else:
        band = StalenessLevel.EXPIRED
        score = 0.1
        penalties.append(
            f"Data is {days} days old — EXPIRED "
            f"(>{thresh.expired_days} days for {source_type})",
        )

    details = f"Source type '{source_type}': {days} days old, staleness={band.value}"

    return DimensionScore(
        dimension=QualityDimension.FRESHNESS,
        score=max(0.0, min(1.0, score)),
        grade=score_to_grade(max(0.0, min(1.0, score))),
        details=details,
        penalties=penalties,
    )


def score_completeness(
    available_sectors: list[str],
    required_sectors: list[str],
    available_fields: dict[str, list[str]] | None = None,
) -> DimensionScore:
    """Score sector/field completeness."""
    if not required_sectors:
        return DimensionScore(
            dimension=QualityDimension.COMPLETENESS,
            score=1.0, grade=QualityGrade.A,
            details="No required sectors specified",
            penalties=[],
        )

    available_set = set(available_sectors)
    required_set = set(required_sectors)
    covered = available_set & required_set
    missing = required_set - available_set
    base_score = len(covered) / len(required_set)

    penalties: list[str] = []
    if missing:
        penalties.append(
            f"Missing {len(missing)} of {len(required_set)} required sectors: "
            f"{', '.join(sorted(missing))}",
        )

    # Optional field-level penalty
    if available_fields and covered:
        max_fields = max(len(f) for f in available_fields.values()) if available_fields else 1
        if max_fields > 0:
            field_scores = []
            for sector in covered:
                sector_fields = available_fields.get(sector, [])
                field_scores.append(len(sector_fields) / max_fields)
            field_avg = sum(field_scores) / len(field_scores) if field_scores else 1.0
            if field_avg < 1.0:
                field_penalty = (1.0 - field_avg) * 0.2
                base_score = max(0.0, base_score - field_penalty)
                penalties.append(
                    f"Field completeness: {field_avg:.0%} average across sectors",
                )

    score = max(0.0, min(1.0, base_score))
    return DimensionScore(
        dimension=QualityDimension.COMPLETENESS,
        score=score,
        grade=score_to_grade(score),
        details=f"{len(covered)}/{len(required_set)} sectors covered ({score:.0%})",
        penalties=penalties,
    )


def score_confidence(
    confidence_distribution: dict[str, float],
) -> DimensionScore:
    """Score based on confidence band distribution.

    Weights: hard=1.0, estimated=0.6, assumed=0.2.
    """
    if not confidence_distribution:
        return DimensionScore(
            dimension=QualityDimension.CONFIDENCE,
            score=0.0, grade=QualityGrade.F,
            details="No confidence data available",
            penalties=["No confidence distribution provided"],
        )

    total_weight = sum(confidence_distribution.values())
    if total_weight == 0:
        return DimensionScore(
            dimension=QualityDimension.CONFIDENCE,
            score=0.0, grade=QualityGrade.F,
            details="Empty confidence distribution",
            penalties=["Confidence distribution sums to 0"],
        )

    score = 0.0
    penalties: list[str] = []
    for band, share in confidence_distribution.items():
        weight = _CONFIDENCE_WEIGHTS.get(band.lower(), 0.2)
        contribution = share * weight
        score += contribution
        if weight < 1.0 and share > 0:
            penalties.append(
                f"{band}: {share:.0%} of data (weight {weight})",
            )

    score = max(0.0, min(1.0, score))
    return DimensionScore(
        dimension=QualityDimension.CONFIDENCE,
        score=score,
        grade=score_to_grade(score),
        details=f"Weighted confidence score: {score:.2f}",
        penalties=penalties,
    )


def score_provenance(
    has_evidence_refs: bool,
    source_description: str,
    is_assumption: bool,
) -> DimensionScore:
    """Score data provenance/traceability.

    Full evidence chain=1.0, missing evidence=-0.3,
    missing source description=-0.2, is assumption=-0.2.
    """
    score = 1.0
    penalties: list[str] = []

    if not has_evidence_refs:
        score -= 0.3
        penalties.append("No evidence references linked (-0.3)")

    if not source_description.strip():
        score -= 0.2
        penalties.append("No source description provided (-0.2)")

    if is_assumption:
        score -= 0.2
        penalties.append("Data is an assumption, not observed (-0.2)")

    score = max(0.0, min(1.0, score))
    return DimensionScore(
        dimension=QualityDimension.PROVENANCE,
        score=score,
        grade=score_to_grade(score),
        details=f"Provenance score: {score:.2f}",
        penalties=penalties,
    )


def score_consistency(
    values: list[float],
    reference_values: list[float] | None = None,
    tolerance: float = 0.1,
) -> DimensionScore:
    """Score internal consistency or agreement with reference values.

    With reference: fraction of values within tolerance.
    Without reference: based on coefficient of variation.
    """
    if not values or len(values) <= 1:
        return DimensionScore(
            dimension=QualityDimension.CONSISTENCY,
            score=1.0, grade=QualityGrade.A,
            details="Insufficient data for consistency check",
            penalties=[],
        )

    penalties: list[str] = []

    if reference_values is not None and len(reference_values) == len(values):
        within = 0
        for i, (v, r) in enumerate(zip(values, reference_values, strict=True)):
            if r == 0:
                if v == 0:
                    within += 1
                else:
                    penalties.append(
                        f"Index {i}: value={v:.2f}, reference=0.0 (undefined ratio)",
                    )
            elif abs(v - r) / abs(r) <= tolerance:
                within += 1
            else:
                pct_diff = abs(v - r) / abs(r) * 100
                penalties.append(
                    f"Index {i}: value={v:.2f} vs reference={r:.2f} "
                    f"({pct_diff:.1f}% off, tolerance={tolerance:.0%})",
                )
        score = within / len(values)
    else:
        # CV-based scoring
        arr = np.array(values, dtype=float)
        mean = np.mean(arr)
        if mean == 0:
            score = 1.0
        else:
            cv = float(np.std(arr) / abs(mean))
            if cv <= 0.1:
                score = 1.0
            elif cv <= 0.3:
                score = 0.75
            else:
                score = max(0.0, 1.0 - cv)
            if cv > 0.1:
                penalties.append(f"Coefficient of variation: {cv:.3f}")

    score = max(0.0, min(1.0, score))
    return DimensionScore(
        dimension=QualityDimension.CONSISTENCY,
        score=score,
        grade=score_to_grade(score),
        details=f"Consistency score: {score:.2f}",
        penalties=penalties,
    )


def score_structural_validity(
    a_matrix: np.ndarray,
    sector_codes: list[str],
    taxonomy_sector_count: int,
) -> DimensionScore:
    """Score structural validity of the A (technical coefficients) matrix.

    Amendment 1: Checks spectral radius, non-negativity, column sums,
    and sector count. Reports actual values for audit trail.
    """
    penalties: list[str] = []
    score = 1.0

    # 1. Spectral radius < 1 (Hawkins-Simon condition)
    eigenvalues = np.linalg.eigvals(a_matrix)
    spectral_radius = float(np.max(np.abs(eigenvalues)))

    if spectral_radius >= 1.0:
        score = 0.0
        penalties.append(
            f"Spectral radius = {spectral_radius:.4f} (>= 1.0) — "
            "Leontief inverse does not exist",
        )
    elif spectral_radius >= 0.95:
        score = min(score, 0.5)
        penalties.append(
            f"Spectral radius = {spectral_radius:.4f} (>= 0.95) — "
            "near-singular matrix, results may be unstable",
        )
    elif spectral_radius >= 0.9:
        score = min(score, 0.7)
        penalties.append(
            f"Spectral radius = {spectral_radius:.4f} (>= 0.90) — "
            "elevated but acceptable",
        )

    # 2. No negative technical coefficients
    neg_count = int(np.sum(a_matrix < 0))
    if neg_count > 0:
        score = min(score, 0.5)
        penalties.append(
            f"{neg_count} negative coefficient(s) in A matrix",
        )

    # 3. Column sums < 1
    col_sums = a_matrix.sum(axis=0)
    bad_cols = [
        i for i, s in enumerate(col_sums) if s >= 1.0
    ]
    if bad_cols:
        score = min(score, 0.5)
        for i in bad_cols:
            code = sector_codes[i] if i < len(sector_codes) else f"col_{i}"
            penalties.append(
                f"Column sum for {code} = {col_sums[i]:.4f} (>= 1.0)",
            )

    # 4. Sector count matches taxonomy
    actual = a_matrix.shape[0]
    if actual != taxonomy_sector_count:
        score = min(score, 0.7)
        penalties.append(
            f"Matrix has {actual} sectors but taxonomy expects "
            f"{taxonomy_sector_count}",
        )

    score = max(0.0, min(1.0, score))
    details = (
        f"Spectral radius = {spectral_radius:.4f}, "
        f"{a_matrix.shape[0]}x{a_matrix.shape[1]} matrix, "
        f"{neg_count} negative coefficients"
    )

    return DimensionScore(
        dimension=QualityDimension.STRUCTURAL_VALIDITY,
        score=score,
        grade=score_to_grade(score),
        details=details,
        penalties=penalties,
    )


# ---------------------------------------------------------------------------
# Orchestrator: compute_input_quality (Amendment 2)
# ---------------------------------------------------------------------------


def compute_input_quality(
    input_type: str,
    input_data: dict,
    reference_data: dict | None = None,
    dimension_weights: dict[str, float] | None = None,
    reference_date: datetime | None = None,
) -> InputQualityScore:
    """Compute quality score for a single data input.

    Amendment 2: Uses DEFAULT_DIMENSION_WEIGHTS[input_type] when no
    explicit weights provided. Only scores dimensions with weight > 0.
    Stores weights in result for auditability.
    """
    weights = dimension_weights or DEFAULT_DIMENSION_WEIGHTS.get(
        input_type, DEFAULT_DIMENSION_WEIGHTS["default"],
    )

    dimension_scores: list[DimensionScore] = []
    weighted_sum = 0.0
    total_weight = 0.0

    for dim_name, weight in weights.items():
        if weight <= 0:
            continue

        dim = QualityDimension(dim_name)
        ds: DimensionScore | None = None

        if dim == QualityDimension.FRESHNESS:
            last_updated = input_data.get("last_updated")
            if last_updated:
                ds = score_freshness(
                    last_updated, input_type, reference_date=reference_date,
                )

        elif dim == QualityDimension.COMPLETENESS:
            available = input_data.get("available_sectors", [])
            required = input_data.get("required_sectors", [])
            fields = input_data.get("available_fields")
            ds = score_completeness(available, required, fields)

        elif dim == QualityDimension.CONFIDENCE:
            dist = input_data.get("confidence_distribution", {})
            ds = score_confidence(dist)

        elif dim == QualityDimension.PROVENANCE:
            ds = score_provenance(
                has_evidence_refs=input_data.get("has_evidence_refs", False),
                source_description=input_data.get("source_description", ""),
                is_assumption=input_data.get("is_assumption", False),
            )

        elif dim == QualityDimension.CONSISTENCY:
            values = input_data.get("values", [])
            ref_values = (reference_data or {}).get("values")
            ds = score_consistency(values, ref_values)

        elif dim == QualityDimension.STRUCTURAL_VALIDITY:
            a_matrix = input_data.get("a_matrix")
            sector_codes = input_data.get("sector_codes", [])
            taxonomy_count = input_data.get("taxonomy_sector_count", 0)
            if a_matrix is not None:
                ds = score_structural_validity(
                    a_matrix, sector_codes, taxonomy_count,
                )

        if ds is not None:
            dimension_scores.append(ds)
            weighted_sum += ds.score * weight
            total_weight += weight

    overall = weighted_sum / total_weight if total_weight > 0 else 0.0
    overall = max(0.0, min(1.0, overall))

    return InputQualityScore(
        input_type=input_type,
        input_version_id=input_data.get("version_id"),
        dimension_scores=dimension_scores,
        overall_score=overall,
        overall_grade=score_to_grade(overall),
        dimension_weights=weights,
    )


# ---------------------------------------------------------------------------
# Freshness monitoring
# ---------------------------------------------------------------------------


def check_freshness(
    source_name: str,
    source_type: str,
    last_updated: datetime,
    reference_date: datetime | None = None,
    thresholds: dict[str, FreshnessThresholds] | None = None,
) -> FreshnessCheck:
    """Produce a FreshnessCheck for a single data source."""
    ref = reference_date or datetime.now(tz=UTC)
    if last_updated.tzinfo is None:
        last_updated = last_updated.replace(tzinfo=UTC)
    days = (ref - last_updated).days

    thresh_map = thresholds or DEFAULT_FRESHNESS_THRESHOLDS
    thresh = thresh_map.get(
        source_type, thresh_map.get("default", DEFAULT_FRESHNESS_THRESHOLDS["default"]),
    )

    if days < thresh.aging_days:
        staleness = StalenessLevel.CURRENT
        action = "No action needed"
    elif days < thresh.stale_days:
        staleness = StalenessLevel.AGING
        action = f"Consider refreshing '{source_name}' — {days} days old"
    elif days < thresh.expired_days:
        staleness = StalenessLevel.STALE
        action = f"'{source_name}' is stale ({days} days) — update recommended"
    else:
        staleness = StalenessLevel.EXPIRED
        action = (
            f"'{source_name}' is expired ({days} days) — "
            "immediate update or nowcasting required"
        )

    return FreshnessCheck(
        source_name=source_name,
        source_type=source_type,
        last_updated=last_updated,
        checked_at=ref,
        staleness=staleness,
        days_since_update=days,
        recommended_action=action,
    )


def generate_freshness_report(
    sources: list[dict],
    thresholds: dict[str, FreshnessThresholds] | None = None,
    reference_date: datetime | None = None,
) -> FreshnessReport:
    """Generate aggregate freshness report for all data sources."""
    if not sources:
        return FreshnessReport(
            checks=[],
            stale_count=0,
            expired_count=0,
            overall_freshness=StalenessLevel.CURRENT,
        )

    checks: list[FreshnessCheck] = []
    for src in sources:
        fc = check_freshness(
            source_name=src["name"],
            source_type=src["type"],
            last_updated=src["last_updated"],
            reference_date=reference_date,
            thresholds=thresholds,
        )
        checks.append(fc)

    stale_count = sum(
        1 for c in checks
        if c.staleness in (StalenessLevel.STALE, StalenessLevel.EXPIRED)
    )
    expired_count = sum(
        1 for c in checks if c.staleness == StalenessLevel.EXPIRED
    )
    overall = max(
        checks, key=lambda c: _STALENESS_SEVERITY[c.staleness],
    ).staleness

    return FreshnessReport(
        checks=checks,
        stale_count=stale_count,
        expired_count=expired_count,
        overall_freshness=overall,
    )


# ---------------------------------------------------------------------------
# Run-level summary (Amendments 3, 5, 7)
# ---------------------------------------------------------------------------


def compute_run_quality_summary(
    run_id: UUID,
    workspace_id: UUID,
    base_table_year: int,
    current_year: int,
    input_scores: list[InputQualityScore],
    freshness_report: FreshnessReport,
    coverage_pct: float,
    key_gaps: list[str] | None = None,
    key_strengths: list[str] | None = None,
    grade_thresholds: GradeThresholds | None = None,
    mapping_coverage_pct: float | None = None,
    base_table_vintage: str = "",
) -> RunQualitySummary:
    """Compute the run-level data quality summary.

    Publication gate (Amendment 7):
      PASS: grade >= B AND no STALE/EXPIRED AND coverage >= 0.7
      PASS_WITH_WARNINGS: grade >= C AND no EXPIRED AND coverage >= 0.5
      FAIL_REQUIRES_WAIVER: anything below

    Amendment 3: mapping_coverage_pct < 0.5 forces FAIL.
    Amendment 5: summary_version + summary_hash for audit.
    """
    years_since = current_year - base_table_year

    # Overall score = mean of input scores
    if input_scores:
        overall = sum(s.overall_score for s in input_scores) / len(input_scores)
    else:
        overall = 0.0
    overall = max(0.0, min(1.0, overall))
    grade = score_to_grade(overall, grade_thresholds)

    # Build gaps and strengths
    gaps = list(key_gaps or [])
    strengths = list(key_strengths or [])

    # Amendment 3: mapping coverage check
    if mapping_coverage_pct is not None and mapping_coverage_pct < 0.5:
        unmapped_pct = (1.0 - mapping_coverage_pct) * 100
        gaps.append(
            f"Only {mapping_coverage_pct:.0%} of budget value is mapped to sectors "
            f"— {unmapped_pct:.0f}% remains unmapped",
        )

    # Amendment 7: Gate mode logic
    has_expired = freshness_report.expired_count > 0
    has_stale = freshness_report.stale_count > 0
    low_mapping = (
        mapping_coverage_pct is not None and mapping_coverage_pct < 0.5
    )

    grade_val = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}
    g = grade_val.get(grade.value, 0)

    if (
        g >= 3
        and not has_stale
        and not has_expired
        and coverage_pct >= 0.7
        and not low_mapping
    ):
        gate_mode = PublicationGateMode.PASS
    elif (
        g >= 2
        and not has_expired
        and coverage_pct >= 0.5
        and not low_mapping
    ):
        gate_mode = PublicationGateMode.PASS_WITH_WARNINGS
    else:
        gate_mode = PublicationGateMode.FAIL_REQUIRES_WAIVER

    gate_pass = gate_mode != PublicationGateMode.FAIL_REQUIRES_WAIVER

    # Recommendation string
    if gate_mode == PublicationGateMode.PASS:
        recommendation = "Suitable for governed publication"
    elif gate_mode == PublicationGateMode.PASS_WITH_WARNINGS:
        warnings = []
        if has_stale:
            warnings.append("stale data sources present")
        if coverage_pct < 0.7:
            warnings.append(f"sector coverage at {coverage_pct:.0%}")
        if g < 3:
            warnings.append(f"overall grade {grade.value}")
        detail = "; ".join(warnings) if warnings else "minor quality concerns"
        recommendation = f"Review recommended before publication — {detail}"
    else:
        issues = []
        if has_expired:
            issues.append(
                f"{freshness_report.expired_count} expired data source(s)",
            )
        if coverage_pct < 0.5:
            issues.append(f"sector coverage only {coverage_pct:.0%}")
        if low_mapping:
            issues.append(
                f"mapping coverage only {mapping_coverage_pct:.0%}",
            )
        if g < 2:
            issues.append(f"overall grade {grade.value}")
        detail = "; ".join(issues) if issues else "significant data gaps"
        recommendation = (
            f"Significant data gaps — internal use only ({detail})"
        )

    if not base_table_vintage:
        base_table_vintage = f"Base year {base_table_year}"

    # Build summary (without hash first)
    summary_data = {
        "run_id": str(run_id),
        "workspace_id": str(workspace_id),
        "base_table_vintage": base_table_vintage,
        "base_table_year": base_table_year,
        "years_since_base": years_since,
        "overall_run_score": round(overall, 4),
        "overall_run_grade": grade.value,
        "coverage_pct": coverage_pct,
        "mapping_coverage_pct": mapping_coverage_pct,
        "gate_mode": gate_mode.value,
        "gate_pass": gate_pass,
    }
    # Amendment 5: compute hash
    summary_hash = hashlib.sha256(
        json.dumps(summary_data, sort_keys=True).encode(),
    ).hexdigest()

    return RunQualitySummary(
        run_id=run_id,
        workspace_id=workspace_id,
        base_table_vintage=base_table_vintage,
        base_table_year=base_table_year,
        years_since_base=years_since,
        input_scores=input_scores,
        overall_run_score=round(overall, 4),
        overall_run_grade=grade,
        freshness_report=freshness_report,
        coverage_pct=coverage_pct,
        mapping_coverage_pct=mapping_coverage_pct,
        key_gaps=gaps,
        key_strengths=strengths,
        recommendation=recommendation,
        publication_gate_pass=gate_pass,
        publication_gate_mode=gate_mode,
        summary_version=DATA_QUALITY_ENGINE_VERSION,
        summary_hash=summary_hash,
    )
