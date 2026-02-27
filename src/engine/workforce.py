"""Workforce/Saudization Satellite Engine — MVP-11.

Deterministic engine code: NumPy only, NO LLM calls.

7 pure functions computing:
1. Employment per sector from delta_x + coefficients
2. Occupation bridge (sector → occupation mapping)
3. Nationality split (three-tier + unclassified)
4. Saudization gap (min/max range vs policy targets)
5. Sensitivity envelope (confidence-driven bands)
6. Confidence summary (output-weighted quality assessment)
7. Full workforce impact (orchestrator)

All 9 amendments enforced:
- [1] delta_x_source field on result
- [2] Unit normalization via normalize_delta_x()
- [3] abs-based sensitivity bands for negatives
- [4] UNMAPPED residual bucket in bridge
- [5] Unclassified nationality bucket
- [6] Saudization gap as min/max range
- [7] Training fields (default None)
- [8] evidence_refs (schema-level)
- [9] Hash reproducibility
"""

import hashlib
import json
import logging
from collections import defaultdict

import numpy as np

from src.models.common import ConstraintConfidence
from src.models.workforce import (
    BridgeEntry,
    EmploymentCoefficients,
    NationalitySplit,
    NationalityTier,
    OccupationBreakdown,
    SaudizationGap,
    SaudizationRules,
    SectorEmployment,
    SectorEmploymentCoefficient,
    SectorOccupationBridge,
    SectorSaudizationTarget,
    SensitivityEnvelope,
    TierAssignment,
    WorkforceConfidenceLevel,
    WorkforceConfidenceSummary,
    WorkforceResult,
)

logger = logging.getLogger(__name__)

WORKFORCE_SATELLITE_VERSION = "1.0.0"

# Confidence-driven sensitivity bands (Amendment 3)
_CONFIDENCE_BANDS: dict[str, float] = {
    "HARD": 0.05,
    "ESTIMATED": 0.15,
    "ASSUMED": 0.30,
}

# Confidence weights for output-weighted summary
_CONFIDENCE_WEIGHTS: dict[str, float] = {
    "HARD": 1.0,
    "ESTIMATED": 0.5,
    "ASSUMED": 0.2,
}


# ---------------------------------------------------------------------------
# Unit normalization (Amendment 2)
# ---------------------------------------------------------------------------


def normalize_delta_x(
    delta_x: np.ndarray,
    delta_x_unit: str,
    coefficient_unit: str,
) -> np.ndarray:
    """Normalize delta_x to match the unit expected by coefficients.

    Amendment 2: Explicit unit conversion prevents off-by-10^6 errors.

    Args:
        delta_x: Input delta_x array.
        delta_x_unit: Unit of the input ("SAR" or "MILLION_SAR").
        coefficient_unit: Unit expected by coefficients ("SAR" or "MILLION_SAR").

    Returns:
        Normalized delta_x array.
    """
    if delta_x_unit == coefficient_unit:
        return delta_x.copy()
    if delta_x_unit == "SAR" and coefficient_unit == "MILLION_SAR":
        return delta_x / 1_000_000.0
    if delta_x_unit == "MILLION_SAR" and coefficient_unit == "SAR":
        return delta_x * 1_000_000.0
    raise ValueError(
        f"Unknown unit conversion: {delta_x_unit} → {coefficient_unit}"
    )


# ---------------------------------------------------------------------------
# 1. compute_employment
# ---------------------------------------------------------------------------


def compute_employment(
    delta_x_total: np.ndarray,
    delta_x_direct: np.ndarray,
    delta_x_indirect: np.ndarray,
    coefficients: EmploymentCoefficients,
    sector_codes: list[str],
) -> dict[str, SectorEmployment]:
    """Compute per-sector employment from delta_x and coefficients.

    Formula: Δjobs_i = jobs_per_million_sar_i × (Δx_i / 1_000_000)
    (after unit normalization).

    Args:
        delta_x_total: Total output changes (n-vector, in SAR).
        delta_x_direct: Direct output changes (n-vector).
        delta_x_indirect: Indirect output changes (n-vector).
        coefficients: Versioned employment coefficients.
        sector_codes: Ordered sector code list.

    Returns:
        Dict of sector_code → SectorEmployment.
    """
    n = len(sector_codes)
    if delta_x_total.shape != (n,):
        raise ValueError(
            f"delta_x_total dimension {delta_x_total.shape} "
            f"does not match sector_codes length {n}"
        )

    # Build coefficient map
    coeff_map: dict[str, SectorEmploymentCoefficient] = {
        c.sector_code: c for c in coefficients.coefficients
    }

    # Normalize delta_x to match coefficient unit (Amendment 2)
    # We assume input delta_x is in SAR (from ResultSet)
    norm_total = normalize_delta_x(delta_x_total, "SAR", coefficients.output_unit)
    norm_direct = normalize_delta_x(delta_x_direct, "SAR", coefficients.output_unit)
    norm_indirect = normalize_delta_x(delta_x_indirect, "SAR", coefficients.output_unit)

    result: dict[str, SectorEmployment] = {}
    for i, sc in enumerate(sector_codes):
        coeff = coeff_map.get(sc)
        if coeff is None:
            # No coefficient for this sector → zero jobs
            result[sc] = SectorEmployment(
                sector_code=sc,
                total_jobs=0.0,
                direct_jobs=0.0,
                indirect_jobs=0.0,
                confidence=ConstraintConfidence.ASSUMED,
            )
            continue

        jobs_per_m = coeff.jobs_per_million_sar
        if coefficients.output_unit == "MILLION_SAR":
            total_jobs = jobs_per_m * norm_total[i]
            direct_jobs = jobs_per_m * norm_direct[i]
            indirect_jobs = jobs_per_m * norm_indirect[i]
        else:
            # output_unit == "SAR" → coefficients expect SAR
            total_jobs = jobs_per_m * (norm_total[i] / 1_000_000.0)
            direct_jobs = jobs_per_m * (norm_direct[i] / 1_000_000.0)
            indirect_jobs = jobs_per_m * (norm_indirect[i] / 1_000_000.0)

        result[sc] = SectorEmployment(
            sector_code=sc,
            total_jobs=float(total_jobs),
            direct_jobs=float(direct_jobs),
            indirect_jobs=float(indirect_jobs),
            confidence=coeff.confidence,
        )

    return result


# ---------------------------------------------------------------------------
# 2. apply_occupation_bridge
# ---------------------------------------------------------------------------


def apply_occupation_bridge(
    sector_employment: dict[str, SectorEmployment],
    bridge_entries: list[BridgeEntry],
) -> tuple[dict[str, list[OccupationBreakdown]], list[str]]:
    """Map sector jobs to occupation-level breakdowns via bridge.

    Amendment 4: Creates UNMAPPED entry when shares < 1.0.

    Args:
        sector_employment: Employment per sector.
        bridge_entries: Bridge entries mapping sectors to occupations.

    Returns:
        Tuple of (breakdowns dict, data_quality_notes list).
    """
    notes: list[str] = []

    if not bridge_entries:
        return {}, notes

    # Group entries by sector
    sector_entries: dict[str, list[BridgeEntry]] = defaultdict(list)
    for entry in bridge_entries:
        sector_entries[entry.sector_code].append(entry)

    breakdowns: dict[str, list[OccupationBreakdown]] = {}

    for sc, se in sector_employment.items():
        entries = sector_entries.get(sc)
        if not entries:
            notes.append(
                f"Sector {sc}: no bridge entries — "
                f"occupation breakdown not available."
            )
            continue

        occ_list: list[OccupationBreakdown] = []
        share_sum = 0.0

        for entry in entries:
            jobs = se.total_jobs * entry.share
            occ_list.append(OccupationBreakdown(
                occupation_code=entry.occupation_code,
                jobs=float(jobs),
                share_of_sector=entry.share,
                confidence=entry.confidence,
            ))
            share_sum += entry.share

        # Amendment 4: UNMAPPED residual
        residual = 1.0 - share_sum
        if residual > 1e-6:
            unmapped_jobs = se.total_jobs * residual
            occ_list.append(OccupationBreakdown(
                occupation_code="UNMAPPED",
                jobs=float(unmapped_jobs),
                share_of_sector=float(residual),
                confidence=ConstraintConfidence.ASSUMED,
            ))
            pct = residual * 100
            notes.append(
                f"Sector {sc}: {pct:.1f}% of jobs not covered by "
                f"occupation bridge, classified as UNMAPPED."
            )

        breakdowns[sc] = occ_list

    return breakdowns, notes


# ---------------------------------------------------------------------------
# 3. compute_nationality_split
# ---------------------------------------------------------------------------


def compute_nationality_split(
    sector_employment: dict[str, SectorEmployment],
    tier_assignments: list[TierAssignment],
    occupation_breakdowns: dict[str, list[OccupationBreakdown]],
) -> tuple[dict[str, NationalitySplit], list[str]]:
    """Compute nationality-tier split per sector.

    Amendment 5: Missing tier assignments → unclassified (NOT expat_reliant).

    Args:
        sector_employment: Employment per sector.
        tier_assignments: Tier assignments by occupation.
        occupation_breakdowns: Occupation breakdowns per sector (may be empty).

    Returns:
        Tuple of (splits dict, data_quality_notes list).
    """
    notes: list[str] = []

    # Build tier lookup
    tier_map: dict[str, NationalityTier] = {
        ta.occupation_code: ta.nationality_tier
        for ta in tier_assignments
    }

    splits: dict[str, NationalitySplit] = {}

    for sc, se in sector_employment.items():
        occ_list = occupation_breakdowns.get(sc)

        if not occ_list:
            # No occupation data → all unclassified
            splits[sc] = NationalitySplit(
                sector_code=sc,
                total_jobs=se.total_jobs,
                saudi_ready=0.0,
                saudi_trainable=0.0,
                expat_reliant=0.0,
                unclassified=se.total_jobs,
            )
            if se.total_jobs > 0:
                notes.append(
                    f"Sector {sc}: {se.total_jobs:.0f} jobs (100%) unclassified "
                    f"due to missing occupation bridge."
                )
            continue

        saudi_ready = 0.0
        saudi_trainable = 0.0
        expat_reliant = 0.0
        unclassified = 0.0

        for ob in occ_list:
            tier = tier_map.get(ob.occupation_code)
            if tier is None:
                unclassified += ob.jobs
            elif tier == NationalityTier.SAUDI_READY:
                saudi_ready += ob.jobs
            elif tier == NationalityTier.SAUDI_TRAINABLE:
                saudi_trainable += ob.jobs
            elif tier == NationalityTier.EXPAT_RELIANT:
                expat_reliant += ob.jobs

        if unclassified > 0 and se.total_jobs > 0:
            pct = (unclassified / se.total_jobs) * 100
            notes.append(
                f"Sector {sc}: {unclassified:.0f} jobs ({pct:.1f}%) "
                f"unclassified due to missing tier assignments."
            )

        splits[sc] = NationalitySplit(
            sector_code=sc,
            total_jobs=se.total_jobs,
            saudi_ready=float(saudi_ready),
            saudi_trainable=float(saudi_trainable),
            expat_reliant=float(expat_reliant),
            unclassified=float(unclassified),
        )

    return splits, notes


# ---------------------------------------------------------------------------
# 4. compute_saudization_gap
# ---------------------------------------------------------------------------


def compute_saudization_gap(
    nationality_splits: dict[str, NationalitySplit],
    sector_targets: list[SectorSaudizationTarget],
) -> dict[str, SaudizationGap]:
    """Compute saudization gap with min/max range.

    Amendment 6: Conservative (saudi_ready only) vs optimistic
    (saudi_ready + saudi_trainable) projected Saudi percentages.

    Assessments:
    - ON_TRACK: target ≤ projected_min
    - ACHIEVABLE_WITH_TRAINING: target ≤ projected_max
    - MODERATE_GAP: gap_pct_min ≤ 0.10
    - SIGNIFICANT_GAP: gap_pct_min ≤ 0.25
    - CRITICAL_GAP: gap_pct_min > 0.25
    """
    gaps: dict[str, SaudizationGap] = {}

    for target in sector_targets:
        sc = target.sector_code
        ns = nationality_splits.get(sc)
        if ns is None:
            continue

        total = ns.total_jobs
        if total == 0:
            projected_min = 0.0
            projected_max = 0.0
        else:
            projected_min = ns.saudi_ready / total
            projected_max = (ns.saudi_ready + ns.saudi_trainable) / total

        gap_pct_min = target.target_saudi_pct - projected_max
        gap_pct_max = target.target_saudi_pct - projected_min

        gap_jobs_min = int(round(gap_pct_min * total))
        gap_jobs_max = int(round(gap_pct_max * total))

        # Determine assessment
        if target.target_saudi_pct <= projected_min:
            assessment = "ON_TRACK"
        elif target.target_saudi_pct <= projected_max:
            assessment = "ACHIEVABLE_WITH_TRAINING"
        elif gap_pct_min <= 0.10:
            assessment = "MODERATE_GAP"
        elif gap_pct_min <= 0.25:
            assessment = "SIGNIFICANT_GAP"
        else:
            assessment = "CRITICAL_GAP"

        gaps[sc] = SaudizationGap(
            sector_code=sc,
            projected_saudi_pct_min=float(projected_min),
            projected_saudi_pct_max=float(projected_max),
            target_saudi_pct=target.target_saudi_pct,
            gap_pct_min=float(gap_pct_min),
            gap_pct_max=float(gap_pct_max),
            gap_jobs_min=gap_jobs_min,
            gap_jobs_max=gap_jobs_max,
            achievability_assessment=assessment,
        )

    return gaps


# ---------------------------------------------------------------------------
# 5. compute_sensitivity
# ---------------------------------------------------------------------------


def compute_sensitivity(
    sector_employment: dict[str, SectorEmployment],
    confidence_per_sector: dict[str, ConstraintConfidence],
) -> dict[str, SensitivityEnvelope]:
    """Compute confidence-driven sensitivity envelopes.

    Amendment 3: Uses abs(base) * band for correct ordering with negatives.
    HARD=±5%, ESTIMATED=±15%, ASSUMED=±30%.
    """
    envelopes: dict[str, SensitivityEnvelope] = {}

    for sc, se in sector_employment.items():
        confidence = confidence_per_sector.get(sc, ConstraintConfidence.ASSUMED)
        band = _CONFIDENCE_BANDS.get(confidence.value, 0.30)

        base = se.total_jobs
        abs_base = abs(base)
        low = base - abs_base * band
        high = base + abs_base * band

        envelopes[sc] = SensitivityEnvelope(
            sector_code=sc,
            base_jobs=float(base),
            low_jobs=float(low),
            high_jobs=float(high),
            confidence_band_pct=band,
        )

    return envelopes


# ---------------------------------------------------------------------------
# 6. compute_confidence_summary
# ---------------------------------------------------------------------------


def compute_confidence_summary(
    coefficients: list[SectorEmploymentCoefficient],
    bridge_entries: list[BridgeEntry],
    tier_assignments: list[TierAssignment],
    sector_employment: dict[str, SectorEmployment],
    sector_codes: list[str],
    *,
    unclassified_pct: float | None = None,
) -> WorkforceConfidenceSummary:
    """Compute output-weighted confidence summary.

    Amendment 5: If unclassified > 50% → force LOW.

    Args:
        coefficients: Employment coefficients list.
        bridge_entries: Bridge entries.
        tier_assignments: Tier assignments.
        sector_employment: Employment per sector.
        sector_codes: All sector codes.
        unclassified_pct: Override for unclassified percentage (for testing).

    Returns:
        WorkforceConfidenceSummary with quality assessment.
    """
    notes: list[str] = []

    # Output-weighted coefficient confidence
    total_jobs = sum(abs(se.total_jobs) for se in sector_employment.values())
    coeff_map = {c.sector_code: c for c in coefficients}

    if total_jobs > 0 and coefficients:
        weighted_sum = 0.0
        for sc, se in sector_employment.items():
            coeff = coeff_map.get(sc)
            if coeff:
                weight = _CONFIDENCE_WEIGHTS.get(coeff.confidence.value, 0.2)
                weighted_sum += weight * abs(se.total_jobs)
        weighted_confidence = weighted_sum / total_jobs
    else:
        weighted_confidence = 0.0

    # Bridge coverage: sectors with at least one bridge entry / total sectors
    bridged_sectors = {e.sector_code for e in bridge_entries}
    bridge_coverage = (
        len(bridged_sectors) / len(sector_codes)
        if sector_codes else 0.0
    )

    # Rule coverage: occupations with tier assignments / total occupations
    assigned_occs = {ta.occupation_code for ta in tier_assignments}
    all_occs = {e.occupation_code for e in bridge_entries}
    rule_coverage = (
        len(assigned_occs & all_occs) / len(all_occs)
        if all_occs else 0.0
    )

    # Amendment 5: Check unclassified percentage
    effective_unclassified = unclassified_pct if unclassified_pct is not None else 0.0

    # Determine overall confidence
    if effective_unclassified > 0.50:
        overall = WorkforceConfidenceLevel.LOW
        notes.append(
            f"Overall confidence forced to LOW: "
            f"{effective_unclassified * 100:.0f}% of jobs unclassified."
        )
    elif (
        weighted_confidence >= 0.7
        and bridge_coverage >= 0.8
        and rule_coverage >= 0.8
    ):
        overall = WorkforceConfidenceLevel.HIGH
    elif (
        weighted_confidence < 0.4
        or bridge_coverage < 0.5
        or rule_coverage < 0.5
    ):
        overall = WorkforceConfidenceLevel.LOW
    else:
        overall = WorkforceConfidenceLevel.MEDIUM

    if bridge_coverage < 1.0 and sector_codes:
        missing = set(sector_codes) - bridged_sectors
        if missing:
            notes.append(
                f"Bridge missing for sectors: {', '.join(sorted(missing))}."
            )

    return WorkforceConfidenceSummary(
        output_weighted_coefficient_confidence=round(weighted_confidence, 4),
        bridge_coverage_pct=round(bridge_coverage, 4),
        rule_coverage_pct=round(rule_coverage, 4),
        overall_confidence=overall,
        data_quality_notes=notes,
    )


# ---------------------------------------------------------------------------
# 7. compute_workforce_impact (orchestrator)
# ---------------------------------------------------------------------------


def compute_workforce_impact(
    delta_x_total: np.ndarray,
    delta_x_direct: np.ndarray,
    delta_x_indirect: np.ndarray,
    sector_codes: list[str],
    coefficients: EmploymentCoefficients,
    bridge: SectorOccupationBridge | None = None,
    rules: SaudizationRules | None = None,
    *,
    delta_x_source: str = "unconstrained",
    feasibility_result_id=None,
    delta_x_unit: str = "SAR",
) -> WorkforceResult:
    """Compute full workforce impact — orchestrator function.

    Calls all 6 sub-functions and assembles the final WorkforceResult.
    Bridge and rules are OPTIONAL (graceful degradation).

    Args:
        delta_x_total: Total output changes (n-vector).
        delta_x_direct: Direct output changes (n-vector).
        delta_x_indirect: Indirect output changes (n-vector).
        sector_codes: Ordered sector code list.
        coefficients: Versioned employment coefficients.
        bridge: Optional sector-occupation bridge.
        rules: Optional saudization rules.
        delta_x_source: "unconstrained" or "feasible".
        feasibility_result_id: UUID if using feasible delta_x.
        delta_x_unit: Unit of the input delta_x vectors.

    Returns:
        WorkforceResult with all analysis.
    """
    all_notes: list[str] = []

    # 1. Compute employment
    employment = compute_employment(
        delta_x_total, delta_x_direct, delta_x_indirect,
        coefficients, sector_codes,
    )

    # 2. Apply occupation bridge (optional)
    occupation_breakdowns: dict[str, list[OccupationBreakdown]] = {}
    if bridge is not None:
        occupation_breakdowns, bridge_notes = apply_occupation_bridge(
            employment, bridge.entries,
        )
        all_notes.extend(bridge_notes)
    else:
        all_notes.append(
            "No occupation bridge provided — occupation breakdowns, "
            "nationality splits, and saudization gaps not available."
        )

    # 3. Compute nationality split (requires bridge or falls back)
    nationality_splits: dict[str, NationalitySplit] = {}
    if rules is not None:
        nationality_splits, split_notes = compute_nationality_split(
            employment, rules.tier_assignments, occupation_breakdowns,
        )
        all_notes.extend(split_notes)
    elif bridge is not None:
        # Bridge but no rules → all unclassified
        nationality_splits, split_notes = compute_nationality_split(
            employment, [], occupation_breakdowns,
        )
        all_notes.extend(split_notes)
        all_notes.append(
            "No saudization rules provided — "
            "all jobs classified as unclassified."
        )

    # 4. Compute saudization gap (requires rules + splits)
    saudization_gaps: dict[str, SaudizationGap] = {}
    if rules is not None and nationality_splits:
        saudization_gaps = compute_saudization_gap(
            nationality_splits, rules.sector_targets,
        )

    # 5. Compute sensitivity envelopes
    confidence_per_sector = {
        sc: se.confidence for sc, se in employment.items()
    }
    sensitivity_envelopes = compute_sensitivity(employment, confidence_per_sector)

    # 6. Compute confidence summary
    bridge_entries = bridge.entries if bridge else []
    tier_assignments = rules.tier_assignments if rules else []

    # Calculate unclassified percentage
    total_jobs = sum(abs(se.total_jobs) for se in employment.values())
    total_unclassified = sum(
        ns.unclassified for ns in nationality_splits.values()
    )
    unclassified_pct = (
        total_unclassified / total_jobs if total_jobs > 0 else 0.0
    )

    confidence_summary = compute_confidence_summary(
        coefficients.coefficients,
        bridge_entries,
        tier_assignments,
        employment,
        sector_codes,
        unclassified_pct=unclassified_pct,
    )

    # 7. Compute coefficient hash for reproducibility
    coeff_snapshot = {
        c.sector_code: c.jobs_per_million_sar
        for c in coefficients.coefficients
    }
    sat_hash = hashlib.sha256(
        json.dumps(coeff_snapshot, sort_keys=True).encode(),
    ).hexdigest()

    return WorkforceResult(
        run_id=coefficients.model_version_id,  # placeholder — API sets real run_id
        workspace_id=coefficients.workspace_id,
        sector_employment={
            sc: se.model_dump() if hasattr(se, "model_dump") else se
            for sc, se in employment.items()
        },
        occupation_breakdowns={
            sc: [ob.model_dump() if hasattr(ob, "model_dump") else ob for ob in obs]
            for sc, obs in occupation_breakdowns.items()
        },
        nationality_splits={
            sc: ns.model_dump() if hasattr(ns, "model_dump") else ns
            for sc, ns in nationality_splits.items()
        },
        saudization_gaps={
            sc: sg.model_dump() if hasattr(sg, "model_dump") else sg
            for sc, sg in saudization_gaps.items()
        },
        sensitivity_envelopes={
            sc: se.model_dump() if hasattr(se, "model_dump") else se
            for sc, se in sensitivity_envelopes.items()
        },
        confidence_summary=confidence_summary,
        employment_coefficients_id=coefficients.employment_coefficients_id,
        employment_coefficients_version=coefficients.version,
        bridge_id=bridge.bridge_id if bridge else None,
        bridge_version=bridge.version if bridge else None,
        rules_id=rules.rules_id if rules else None,
        rules_version=rules.version if rules else None,
        satellite_coefficients_hash=sat_hash,
        data_quality_notes=all_notes,
        delta_x_source=delta_x_source,
        feasibility_result_id=feasibility_result_id,
        delta_x_unit=delta_x_unit,
        coefficient_unit=coefficients.output_unit,
    )
