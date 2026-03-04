"""Deterministic slider → annual_shocks transform — Sprint 22.

Location: src/engine/ because this is pure math (Agent-to-Math boundary).
No LLM calls. No side effects.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass


@dataclass(frozen=True)
class SliderInput:
    """Typed slider item for transform input."""

    sector_code: str
    pct_delta: float


class WorkshopTransformError(Exception):
    """Base error for workshop transform validation."""

    def __init__(self, reason_code: str, message: str) -> None:
        self.reason_code = reason_code
        self.message = message
        super().__init__(message)


class WorkshopUnknownSectorError(WorkshopTransformError):
    """Slider references a sector_code not in model.sector_codes."""

    def __init__(self, sector_code: str, valid_codes: list[str]) -> None:
        super().__init__(
            reason_code="WORKSHOP_UNKNOWN_SECTOR",
            message=(
                f"Sector code '{sector_code}' not found in model sector_codes. "
                f"Valid codes: {sorted(valid_codes)}"
            ),
        )


class WorkshopDuplicateSectorError(WorkshopTransformError):
    """Duplicate sector_code in slider_items list."""

    def __init__(self, sector_code: str) -> None:
        super().__init__(
            reason_code="WORKSHOP_DUPLICATE_SECTOR",
            message=f"Duplicate sector_code '{sector_code}' in slider_items.",
        )


class WorkshopInvalidConfigError(WorkshopTransformError):
    """General config validation failure."""

    def __init__(self, message: str) -> None:
        super().__init__(
            reason_code="WORKSHOP_INVALID_CONFIG",
            message=message,
        )


WORKSHOP_VERSION = "workshop_v1"


def validate_sliders(
    slider_items: list[SliderInput],
    sector_codes: list[str],
) -> None:
    """Validate slider items against model sector_codes.

    Raises:
        WorkshopDuplicateSectorError: duplicate sector_code in slider_items
        WorkshopUnknownSectorError: sector_code not in model.sector_codes
    """
    seen: set[str] = set()
    for item in slider_items:
        if item.sector_code in seen:
            raise WorkshopDuplicateSectorError(item.sector_code)
        seen.add(item.sector_code)

    for item in slider_items:
        if item.sector_code not in sector_codes:
            raise WorkshopUnknownSectorError(item.sector_code, sector_codes)


def validate_base_shocks(
    base_shocks: dict[str, list[float]],
    sector_codes: list[str],
) -> None:
    """Validate base_shocks shape matches sector_codes length.

    Raises:
        WorkshopInvalidConfigError: on mismatch
    """
    if not base_shocks:
        raise WorkshopInvalidConfigError("base_shocks must not be empty.")
    n = len(sector_codes)
    for year, values in base_shocks.items():
        if len(values) != n:
            raise WorkshopInvalidConfigError(
                f"base_shocks['{year}'] has {len(values)} values, expected {n} (one per sector)."
            )


def transform_sliders(
    base_shocks: dict[str, list[float]],
    slider_items: list[SliderInput],
    sector_codes: list[str],
) -> dict[str, list[float]]:
    """Deterministic: annual_shocks[year][i] = base[year][i] * (1 + pct/100).

    Sectors not in slider_items keep baseline values unchanged (pct_delta=0).

    Args:
        base_shocks: Canonical baseline shocks {year_str: [values per sector]}.
        slider_items: Typed list of sector adjustments.
        sector_codes: Model's sector_codes for strict ordering.

    Returns:
        Transformed annual_shocks ready for engine.
    """
    pct_map: dict[str, float] = {item.sector_code: item.pct_delta for item in slider_items}

    result: dict[str, list[float]] = {}
    for year, values in base_shocks.items():
        adjusted: list[float] = []
        for i, code in enumerate(sector_codes):
            pct = pct_map.get(code, 0.0)
            adjusted.append(values[i] * (1.0 + pct / 100.0))
        result[year] = adjusted
    return result


def workshop_config_hash(
    baseline_run_id: str,
    base_shocks: dict[str, list[float]],
    slider_items: list[SliderInput],
) -> str:
    """SHA-256 of canonical JSON config with sorted keys.

    Includes workshop_version for forward compatibility.
    """
    payload = json.dumps(
        {
            "baseline_run_id": baseline_run_id,
            "base_shocks": {k: v for k, v in sorted(base_shocks.items())},
            "sliders": sorted(
                [{"sector_code": s.sector_code, "pct_delta": s.pct_delta} for s in slider_items],
                key=lambda s: s["sector_code"],
            ),
            "workshop_version": WORKSHOP_VERSION,
        },
        sort_keys=True,
    )
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()
