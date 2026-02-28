"""Workforce Satellite Service — MVP-11.

Runtime 4-step pipeline consuming D-4 curated data + engine results.

Pipeline:
1. delta_jobs (from SatelliteAccounts — already computed)
2. Occupation decomposition (OccupationBridge)
3. Nationality feasibility split (NationalityClassificationSet)
4. Nitaqat compliance check (MacroSaudizationTargets)

DETERMINISTIC — no LLM calls.

Amendments applied:
1. Baseline workforce required for compliance
2. Nitaqat target ranges preserved
3. Negative jobs handled (min/mid/max numeric order)
4. Provenance from __init__ D-4 objects
5. Typed models for training_gap and overrides
6. Normalized confidence vocabulary
7. Tier ranges from config (overridable)
8. result_granularity metadata
9. Formal missing-data defaults
10. Dynamic caveats from inputs
"""

from __future__ import annotations

from dataclasses import asdict

import numpy as np

from src.data.workforce.nationality_classification import (
    ClassificationOverride,
    NationalityClassificationSet,
    NationalityTier,
)
from src.data.workforce.nitaqat_macro_targets import MacroSaudizationTargets
from src.data.workforce.occupation_bridge import OccupationBridge
from src.data.workforce.satellite_coeff_loader import CoefficientProvenance
from src.engine.satellites import SatelliteResult
from src.engine.workforce_satellite.config import (
    DEFAULT_TIER_RANGES,
    KNOWN_PCT_SENSITIVITY,
    confidence_to_str,
    worst_confidence,
)
from src.engine.workforce_satellite.schemas import (
    AppliedOverride,
    BaselineSectorWorkforce,
    NationalitySplit,
    OccupationImpact,
    SectorWorkforceSummary,
    TrainingGapEntry,
    WorkforceResult,
)

# ISCO-08 major group labels
_ISCO_LABELS: dict[str, str] = {
    "0": "Armed Forces",
    "1": "Managers",
    "2": "Professionals",
    "3": "Technicians",
    "4": "Clerical Support",
    "5": "Service and Sales",
    "6": "Agricultural Workers",
    "7": "Craft Workers",
    "8": "Plant/Machine Operators",
    "9": "Elementary Occupations",
}


class WorkforceSatellite:
    """Runtime workforce analysis service.

    Consumes D-4 curated data + engine results to produce
    the full workforce picture.

    DETERMINISTIC — no LLM calls.
    """

    def __init__(
        self,
        occupation_bridge: OccupationBridge,
        nationality_classifications: NationalityClassificationSet,
        nitaqat_targets: MacroSaudizationTargets | None = None,
        concordance_service: object | None = None,
        coefficient_provenance: CoefficientProvenance | None = None,
        tier_ranges: (
            dict[NationalityTier, tuple[float, float, float]] | None
        ) = None,
    ) -> None:
        """Initialize with D-4 curated data objects.

        Args:
            occupation_bridge: D-4 sector-to-occupation bridge.
            nationality_classifications: D-4 three-tier classification set.
            nitaqat_targets: D-4 macro Saudization targets (optional).
            concordance_service: D-2 ConcordanceService for division→section
                aggregation (optional, needed if sector_codes are divisions).
            coefficient_provenance: D-4 coefficient provenance metadata.
            tier_ranges: Override default tier→Saudi share ranges (Amendment 7).
        """
        self._bridge = occupation_bridge
        self._classifications = nationality_classifications
        self._nitaqat = nitaqat_targets
        self._concordance = concordance_service
        self._coeff_provenance = coefficient_provenance
        self._tier_ranges = tier_ranges or DEFAULT_TIER_RANGES

        # Amendment 4: store metadata for result population
        self._bridge_version = str(occupation_bridge.year)
        self._classification_version = str(
            nationality_classifications.year,
        )

    def analyze(
        self,
        *,
        satellite_result: SatelliteResult,
        sector_codes: list[str],
        baseline_workforce: list[BaselineSectorWorkforce] | None = None,
        overrides: list[ClassificationOverride] | None = None,
    ) -> WorkforceResult:
        """Run the full 4-step workforce analysis pipeline.

        Step 1: Extract delta_jobs from satellite_result (already computed)
        Step 2: Decompose jobs by occupation using bridge
        Step 3: Split by nationality tier using classifications
        Step 4: Check Nitaqat compliance using macro targets

        All steps propagate confidence labels.

        Args:
            satellite_result: From SatelliteAccounts.compute().
            sector_codes: Sector codes matching delta_jobs vector.
            baseline_workforce: Current employment stock per sector
                (Amendment 1). Required for meaningful compliance checks.
            overrides: Analyst overrides for nationality classification
                (Knowledge Flywheel hook).
        """
        delta_jobs = np.asarray(
            satellite_result.delta_jobs, dtype=np.float64,
        )

        # Apply overrides if provided (produces new classification set)
        classifications = self._classifications
        applied_overrides: list[AppliedOverride] = []
        if overrides:
            classifications = classifications.apply_overrides(overrides)
            applied_overrides = [
                AppliedOverride(
                    sector_code=o.sector_code,
                    occupation_code=o.occupation_code,
                    original_tier=o.original_tier,
                    override_tier=o.override_tier,
                    overridden_by=o.overridden_by,
                    engagement_id=o.engagement_id,
                    rationale=o.rationale,
                )
                for o in overrides
            ]

        # Build baseline lookup
        baseline_map: dict[str, BaselineSectorWorkforce] = {}
        if baseline_workforce:
            baseline_map = {b.sector_code: b for b in baseline_workforce}

        # Step 2: occupation decomposition
        occ_impacts = self._decompose_occupations(delta_jobs, sector_codes)

        # Step 3: nationality split
        nat_splits = self._split_nationality(
            occ_impacts, classifications,
        )

        # Build sector summaries
        sector_summaries = self._build_sector_summaries(
            delta_jobs=delta_jobs,
            sector_codes=sector_codes,
            occ_impacts=occ_impacts,
            nat_splits=nat_splits,
            baseline_map=baseline_map,
        )

        # Step 4: compliance check (updates summaries in place)
        self._check_compliance(sector_summaries, baseline_map)

        # Build training gap
        training_gap = self._build_training_gap(sector_summaries, nat_splits)

        # Build caveats (Amendment 10: dynamic + fixed)
        caveats = self._build_caveats(
            sector_codes, baseline_map, applied_overrides,
        )

        # Compute economy-wide aggregates
        result = self._build_result(
            sector_summaries=sector_summaries,
            training_gap=training_gap,
            applied_overrides=applied_overrides,
            caveats=caveats,
        )

        return result

    # ------------------------------------------------------------------
    # Step 2: Occupation decomposition
    # ------------------------------------------------------------------

    def _decompose_occupations(
        self,
        delta_jobs: np.ndarray,
        sector_codes: list[str],
    ) -> dict[str, list[OccupationImpact]]:
        """Decompose sector-level jobs into occupation groups.

        Uses D-4 OccupationBridge (section-level, 20 sectors × 10 groups).
        Bridge shares sum to ~1.0 per sector (validated in D-4).
        """
        result: dict[str, list[OccupationImpact]] = {}

        for i, code in enumerate(sector_codes):
            sector_jobs = float(delta_jobs[i])
            shares = self._bridge.get_occupation_shares(code)

            if not shares:
                # Amendment 9: missing bridge → default with ASSUMED
                result[code] = [
                    OccupationImpact(
                        sector_code=code,
                        occupation_code="9",
                        occupation_label="Elementary Occupations",
                        jobs=sector_jobs,
                        share_of_sector=1.0,
                        bridge_confidence="ASSUMED",
                    ),
                ]
                continue

            impacts: list[OccupationImpact] = []
            for occ_code, share in shares.items():
                # Find bridge entry confidence
                bridge_conf = "ASSUMED"
                for entry in self._bridge.entries:
                    if (
                        entry.sector_code == code
                        and entry.occupation_code == occ_code
                    ):
                        bridge_conf = confidence_to_str(
                            entry.quality_confidence,
                        )
                        break

                impacts.append(OccupationImpact(
                    sector_code=code,
                    occupation_code=occ_code,
                    occupation_label=_ISCO_LABELS.get(
                        occ_code, f"ISCO {occ_code}",
                    ),
                    jobs=sector_jobs * share,
                    share_of_sector=share,
                    bridge_confidence=bridge_conf,
                ))
            result[code] = impacts

        return result

    # ------------------------------------------------------------------
    # Step 3: Nationality feasibility split
    # ------------------------------------------------------------------

    def _split_nationality(
        self,
        occupation_impacts: dict[str, list[OccupationImpact]],
        classifications: NationalityClassificationSet,
    ) -> dict[tuple[str, str], NationalitySplit]:
        """Apply three-tier nationality classification.

        Uses D-4 NationalityClassificationSet.
        Output is RANGES (min/mid/max), not point estimates.

        Amendment 3: min/mid/max in numeric order for negative jobs.
        Amendment 7: Tier ranges from config.
        Amendment 9: Missing classification → EXPAT_RELIANT + ASSUMED.
        """
        result: dict[tuple[str, str], NationalitySplit] = {}

        for sector_code, impacts in occupation_impacts.items():
            for impact in impacts:
                occ_code = impact.occupation_code
                classification = classifications.get_tier(
                    sector_code, occ_code,
                )

                if classification is None:
                    # Amendment 9: default to most conservative
                    tier = NationalityTier.EXPAT_RELIANT
                    current_pct = None
                    rationale = (
                        f"No classification for {sector_code}/{occ_code}"
                        " — defaulting to expat_reliant"
                    )
                    class_conf = "ASSUMED"
                else:
                    tier = classification.tier
                    current_pct = classification.current_saudi_pct
                    rationale = classification.rationale
                    class_conf = confidence_to_str(
                        classification.quality_confidence,
                    )

                # Compute range
                saudi_min, saudi_mid, saudi_max = (
                    self._compute_saudi_range(
                        total_jobs=impact.jobs,
                        tier=tier,
                        current_saudi_pct=current_pct,
                    )
                )

                result[(sector_code, occ_code)] = NationalitySplit(
                    sector_code=sector_code,
                    occupation_code=occ_code,
                    tier=tier,
                    total_jobs=impact.jobs,
                    saudi_jobs_min=saudi_min,
                    saudi_jobs_mid=saudi_mid,
                    saudi_jobs_max=saudi_max,
                    classification_confidence=class_conf,
                    current_saudi_pct=current_pct,
                    rationale=rationale,
                )

        return result

    def _compute_saudi_range(
        self,
        *,
        total_jobs: float,
        tier: NationalityTier,
        current_saudi_pct: float | None,
    ) -> tuple[float, float, float]:
        """Compute (min, mid, max) Saudi job range.

        Amendment 3: Handles negative jobs by flipping multiplication
        so min <= mid <= max numerically.
        Amendment 7: Uses tier ranges from config.
        """
        if current_saudi_pct is not None:
            # Use real data as mid-point with ±10% sensitivity
            mid_pct = current_saudi_pct
            low_pct = max(0.0, mid_pct - KNOWN_PCT_SENSITIVITY)
            high_pct = min(1.0, mid_pct + KNOWN_PCT_SENSITIVITY)
        else:
            # Use tier-based ranges from config
            low_pct, mid_pct, high_pct = self._tier_ranges[tier]

        mid = total_jobs * mid_pct

        if total_jobs >= 0:
            saudi_min = total_jobs * low_pct
            saudi_max = total_jobs * high_pct
        else:
            # Amendment 3: flip for negative jobs
            saudi_min = total_jobs * high_pct
            saudi_max = total_jobs * low_pct

        return (saudi_min, mid, saudi_max)

    # ------------------------------------------------------------------
    # Build sector summaries
    # ------------------------------------------------------------------

    def _build_sector_summaries(
        self,
        *,
        delta_jobs: np.ndarray,
        sector_codes: list[str],
        occ_impacts: dict[str, list[OccupationImpact]],
        nat_splits: dict[tuple[str, str], NationalitySplit],
        baseline_map: dict[str, BaselineSectorWorkforce],
    ) -> list[SectorWorkforceSummary]:
        """Build per-sector workforce summaries."""
        summaries: list[SectorWorkforceSummary] = []

        for i, code in enumerate(sector_codes):
            sector_jobs = float(delta_jobs[i])
            impacts = occ_impacts.get(code, [])

            # Aggregate nationality splits for this sector
            saudi_ready = 0.0
            saudi_trainable = 0.0
            expat_reliant = 0.0
            saudi_min_total = 0.0
            saudi_mid_total = 0.0
            saudi_max_total = 0.0
            training_occ_codes: list[str] = []
            conf_breakdown: dict[str, int] = {}

            for impact in impacts:
                key = (code, impact.occupation_code)
                split = nat_splits.get(key)
                if split is None:
                    continue

                # Tier aggregates
                if split.tier == NationalityTier.SAUDI_READY:
                    saudi_ready += split.total_jobs
                elif split.tier == NationalityTier.SAUDI_TRAINABLE:
                    saudi_trainable += split.total_jobs
                    training_occ_codes.append(split.occupation_code)
                else:
                    expat_reliant += split.total_jobs

                saudi_min_total += split.saudi_jobs_min
                saudi_mid_total += split.saudi_jobs_mid
                saudi_max_total += split.saudi_jobs_max

                # Track confidence breakdown
                conf_key = split.classification_confidence.upper()
                conf_breakdown[conf_key] = (
                    conf_breakdown.get(conf_key, 0) + 1
                )

            # Compute projected Saudi pct range (Amendment 1)
            has_baseline = code in baseline_map
            saudi_pct_range: tuple[float, float] | None = None
            if has_baseline:
                bl = baseline_map[code]
                post_total = bl.total_employment + sector_jobs
                if post_total > 0:
                    bl_saudi = bl.saudi_employment or 0.0
                    pct_min = (bl_saudi + saudi_min_total) / post_total
                    pct_max = (bl_saudi + saudi_max_total) / post_total
                    saudi_pct_range = (
                        max(0.0, min(1.0, pct_min)),
                        max(0.0, min(1.0, pct_max)),
                    )

            # Sector-level confidence
            all_conf: list[str] = []
            for impact in impacts:
                all_conf.append(impact.bridge_confidence)
                key = (code, impact.occupation_code)
                split = nat_splits.get(key)
                if split:
                    all_conf.append(split.classification_confidence)
            sector_conf = (
                worst_confidence(*all_conf) if all_conf else "ASSUMED"
            )

            summaries.append(SectorWorkforceSummary(
                sector_code=code,
                total_jobs=sector_jobs,
                occupation_impacts=impacts,
                saudi_ready_jobs=saudi_ready,
                saudi_trainable_jobs=saudi_trainable,
                expat_reliant_jobs=expat_reliant,
                projected_saudi_jobs_min=saudi_min_total,
                projected_saudi_jobs_mid=saudi_mid_total,
                projected_saudi_jobs_max=saudi_max_total,
                projected_saudi_pct_range=saudi_pct_range,
                overall_confidence=sector_conf,
                confidence_breakdown=conf_breakdown,
                training_gap_occupations=training_occ_codes,
                has_baseline=has_baseline,
            ))

        return summaries

    # ------------------------------------------------------------------
    # Step 4: Nitaqat compliance check
    # ------------------------------------------------------------------

    def _check_compliance(
        self,
        sector_summaries: list[SectorWorkforceSummary],
        baseline_map: dict[str, BaselineSectorWorkforce],
    ) -> None:
        """Check each sector's projected Saudi % against Nitaqat targets.

        Uses D-4 MacroSaudizationTargets.
        Updates sector summaries in place.

        Amendment 1: Requires baseline for meaningful compliance.
        Amendment 2: Uses target ranges and 5-state compliance status.
        """
        if self._nitaqat is None:
            for s in sector_summaries:
                s.nitaqat_compliance_status = "NO_TARGET"
            return

        for summary in sector_summaries:
            target = self._nitaqat.get_target(summary.sector_code)

            if target is None:
                summary.nitaqat_compliance_status = "NO_TARGET"
                continue

            # Amendment 2: preserve target ranges
            summary.nitaqat_target_effective = target.effective_target_pct
            summary.nitaqat_target_range = (
                target.target_range_low, target.target_range_high,
            )

            # Amendment 1: need baseline for compliance assessment
            if not summary.has_baseline:
                summary.nitaqat_compliance_status = "INSUFFICIENT_DATA"
                continue

            bl = baseline_map.get(summary.sector_code)
            if bl is None:
                summary.nitaqat_compliance_status = "INSUFFICIENT_DATA"
                continue

            # Compute projected Saudi share range
            post_total = bl.total_employment + summary.total_jobs
            if post_total <= 0:
                summary.nitaqat_compliance_status = "INSUFFICIENT_DATA"
                continue

            bl_saudi = bl.saudi_employment or 0.0
            low_saudi_pct = (
                (bl_saudi + summary.projected_saudi_jobs_min) / post_total
            )
            high_saudi_pct = (
                (bl_saudi + summary.projected_saudi_jobs_max) / post_total
            )
            mid_saudi_pct = (
                (bl_saudi + summary.projected_saudi_jobs_mid) / post_total
            )

            # Amendment 2: compliance using ranges
            target_low = target.target_range_low
            target_high = target.target_range_high

            if low_saudi_pct >= target_high:
                summary.nitaqat_compliance_status = "COMPLIANT"
            elif high_saudi_pct < target_low:
                summary.nitaqat_compliance_status = "NON_COMPLIANT"
            else:
                summary.nitaqat_compliance_status = "AT_RISK"

            # Gap at mid-point
            gap = (
                target.effective_target_pct - mid_saudi_pct
            ) * post_total
            summary.nitaqat_gap_jobs = max(0.0, gap)

    # ------------------------------------------------------------------
    # Training gap analysis (Task 4e)
    # ------------------------------------------------------------------

    def _build_training_gap(
        self,
        sector_summaries: list[SectorWorkforceSummary],
        nat_splits: dict[tuple[str, str], NationalitySplit],
    ) -> list[TrainingGapEntry]:
        """Build training gap entries for all saudi_trainable pairs.

        Amendment 3: Skip contraction sectors for training gap.
        """
        entries: list[TrainingGapEntry] = []

        for summary in sector_summaries:
            # Amendment 3: no training gap for contraction
            if summary.total_jobs < 0:
                continue

            nitaqat_target = summary.nitaqat_target_effective

            for occ_code in summary.training_gap_occupations:
                key = (summary.sector_code, occ_code)
                split = nat_splits.get(key)
                if split is None or split.total_jobs <= 0:
                    continue

                # Gap = jobs that need Saudi workers but don't have them
                if nitaqat_target is not None:
                    gap = split.total_jobs * (
                        nitaqat_target - (
                            split.saudi_jobs_mid / split.total_jobs
                            if split.total_jobs > 0
                            else 0.0
                        )
                    )
                else:
                    # Without target, gap is the trainable mid
                    gap = split.saudi_jobs_mid

                entries.append(TrainingGapEntry(
                    sector_code=summary.sector_code,
                    occupation_code=occ_code,
                    tier=split.tier,
                    total_jobs=split.total_jobs,
                    gap_jobs=max(0.0, gap),
                    nitaqat_target=nitaqat_target,
                ))

        # Sort by gap_jobs descending
        entries.sort(key=lambda e: e.gap_jobs, reverse=True)
        return entries

    # ------------------------------------------------------------------
    # Caveats (Amendment 10: dynamic + fixed)
    # ------------------------------------------------------------------

    def _build_caveats(
        self,
        sector_codes: list[str],
        baseline_map: dict[str, BaselineSectorWorkforce],
        applied_overrides: list[AppliedOverride],
    ) -> list[str]:
        """Build confidence caveats (fixed + dynamic from inputs)."""
        caveats: list[str] = [
            "Occupation bridge is expert-estimated (v1) "
            "— not based on cross-tabulated microdata",
            "Nationality feasibility split is assumption-based "
            "— all classifications are 'assumed' confidence",
            "Saudi job estimates are presented as ranges, "
            "not predictions",
            "Nitaqat compliance is macro-level "
            "— does not capture firm-size or salary-weighting rules",
        ]

        # Amendment 10: dynamic caveats
        missing_baseline = [
            c for c in sector_codes if c not in baseline_map
        ]
        if missing_baseline:
            codes_str = ", ".join(missing_baseline[:5])
            suffix = (
                f" and {len(missing_baseline) - 5} more"
                if len(missing_baseline) > 5 else ""
            )
            caveats.append(
                f"Baseline Saudi shares unavailable for sectors "
                f"{codes_str}{suffix} "
                "— compliance cannot be assessed"
            )

        for ov in applied_overrides:
            caveats.append(
                f"Classification override applied to "
                f"{ov.sector_code}/{ov.occupation_code}"
            )

        return caveats

    # ------------------------------------------------------------------
    # Build final result
    # ------------------------------------------------------------------

    def _build_result(
        self,
        *,
        sector_summaries: list[SectorWorkforceSummary],
        training_gap: list[TrainingGapEntry],
        applied_overrides: list[AppliedOverride],
        caveats: list[str],
    ) -> WorkforceResult:
        """Aggregate sector summaries into final WorkforceResult."""
        total_jobs = sum(s.total_jobs for s in sector_summaries)
        total_min = sum(
            s.projected_saudi_jobs_min for s in sector_summaries
        )
        total_mid = sum(
            s.projected_saudi_jobs_mid for s in sector_summaries
        )
        total_max = sum(
            s.projected_saudi_jobs_max for s in sector_summaries
        )
        total_ready = sum(s.saudi_ready_jobs for s in sector_summaries)
        total_trainable = sum(
            s.saudi_trainable_jobs for s in sector_summaries
        )
        total_expat = sum(s.expat_reliant_jobs for s in sector_summaries)

        # Saudi pct range (economy-wide)
        total_pct_range: tuple[float, float] | None = None
        if total_jobs > 0:
            total_pct_range = (
                total_min / total_jobs,
                total_max / total_jobs,
            )

        # Compliance counts
        compliant = sum(
            1 for s in sector_summaries
            if s.nitaqat_compliance_status == "COMPLIANT"
        )
        non_compliant = sum(
            1 for s in sector_summaries
            if s.nitaqat_compliance_status == "NON_COMPLIANT"
        )
        no_target = sum(
            1 for s in sector_summaries
            if s.nitaqat_compliance_status == "NO_TARGET"
        )
        at_risk = sum(
            1 for s in sector_summaries
            if s.nitaqat_compliance_status == "AT_RISK"
        )
        insuf_data = sum(
            1 for s in sector_summaries
            if s.nitaqat_compliance_status == "INSUFFICIENT_DATA"
        )
        total_gap = sum(
            s.nitaqat_gap_jobs or 0.0 for s in sector_summaries
        )

        # Overall confidence (worst across all sectors)
        all_conf = [s.overall_confidence for s in sector_summaries]
        overall = worst_confidence(*all_conf) if all_conf else "ASSUMED"

        # Provenance (Amendment 4)
        prov_dict: dict = {}
        if self._coeff_provenance is not None:
            prov_dict = asdict(self._coeff_provenance)

        return WorkforceResult(
            sector_summaries=sector_summaries,
            total_jobs=total_jobs,
            total_saudi_jobs_min=total_min,
            total_saudi_jobs_mid=total_mid,
            total_saudi_jobs_max=total_max,
            total_saudi_pct_range=total_pct_range,
            total_saudi_ready=total_ready,
            total_saudi_trainable=total_trainable,
            total_expat_reliant=total_expat,
            sectors_compliant=compliant,
            sectors_non_compliant=non_compliant,
            sectors_no_target=no_target,
            sectors_at_risk=at_risk,
            sectors_insufficient_data=insuf_data,
            total_nitaqat_gap_jobs=total_gap,
            training_gap_summary=training_gap,
            bridge_version=self._bridge_version,
            classification_version=self._classification_version,
            coefficient_provenance=prov_dict,
            overrides_applied=applied_overrides,
            overall_confidence=overall,
            confidence_caveats=caveats,
            known_limitations=[
                "Early deployment: assumption-heavy, "
                "indicative assessment",
                "Occupation bridge at ISIC section level only "
                "(20 sectors)",
                "Nationality split uses tier-based ranges, "
                "not empirical supply curves",
                "Nitaqat compliance is macro-sector level, "
                "not firm-level",
            ],
        )
