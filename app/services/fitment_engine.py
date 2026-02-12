"""Fitment scoring engine and vehicle spec lookup.

The knowledge base contains verified specs for common vehicles.
The scoring system rates wheel compatibility from 0.0 to 1.0.
Hub bore hard-rejection: if the wheel bore is smaller than the vehicle's
hub bore the wheel physically cannot mount — no hub ring can fix that.
"""

import logging
import re
from typing import Any

from app.models.fitment import FitmentResult, PokeCalculation, TireRecommendation
from app.models.vehicle import VehicleSpecs
from app.models.wheel import KanseiWheel

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

KANSEI_STANDARD_BORE: float = 73.1  # mm — all Kansei wheels use this bore

# Tire width range (mm) by wheel width (inches)
TIRE_WIDTH_BY_WHEEL_WIDTH: dict[float, tuple[int, int]] = {
    6.0: (165, 185),
    6.5: (185, 205),
    7.0: (195, 225),
    7.5: (205, 235),
    8.0: (225, 245),
    8.5: (235, 255),
    9.0: (245, 265),
    9.5: (255, 275),
    10.0: (265, 295),
    10.5: (275, 305),
    11.0: (285, 315),
    12.0: (305, 335),
}

STANDARD_TIRE_WIDTHS: list[int] = [
    155,
    165,
    175,
    185,
    195,
    205,
    215,
    225,
    235,
    245,
    255,
    265,
    275,
    285,
    295,
    305,
    315,
]

COMMON_ASPECT_RATIOS: dict[int, list[int]] = {
    15: [55, 60, 65],
    16: [45, 50, 55],
    17: [40, 45, 50],
    18: [35, 40, 45],
    19: [30, 35, 40],
    20: [25, 30, 35],
}

# =============================================================================
# Vehicle Spec Lookup — queries Supabase vehicle_specs table
# =============================================================================


def lookup_vehicle_specs(
    make: str, model: str, year: int, trim: str | None = None
) -> dict[str, Any] | None:
    """Look up vehicle specs from the Supabase vehicle_specs table.

    Returns a dict with bolt_pattern, center_bore (as hub_bore), chassis_code,
    OEM front/rear sizes, tire sizes, brake data, and performance flags.
    Falls back to None if no DB match found.
    """
    from app.services.kansei_db import find_vehicle_specs as db_find

    try:
        row = db_find(year=year, make=make, model=model, trim=trim)
    except Exception as e:
        logger.warning("DB lookup_vehicle_specs failed: %s", e)
        return None

    if not row or not row.get("bolt_pattern"):
        return None

    # Normalize keys to match the interface that callers expect
    # (hub_bore instead of center_bore, uppercase bolt_pattern)
    return {
        "bolt_pattern": row["bolt_pattern"].upper(),
        "hub_bore": row.get("center_bore"),
        "chassis_code": row.get("chassis_code"),
        "trim": row.get("trim"),
        "year_start": row.get("year_start"),
        "year_end": row.get("year_end"),
        "oem_diameter_front": row.get("oem_diameter_front"),
        "oem_diameter_rear": row.get("oem_diameter_rear"),
        "oem_width_front": row.get("oem_width_front"),
        "oem_width_rear": row.get("oem_width_rear"),
        "oem_offset_front": row.get("oem_offset_front"),
        "oem_offset_rear": row.get("oem_offset_rear"),
        "oem_tire_front": row.get("oem_tire_front"),
        "oem_tire_rear": row.get("oem_tire_rear"),
        "front_brake_size": row.get("front_brake_size"),
        "min_wheel_diameter": row.get("min_wheel_diameter"),
        "is_staggered_stock": row.get("is_staggered_stock", False),
        "is_performance_trim": row.get("is_performance_trim", False),
        "confidence": row.get("confidence", 0.8),
        # Legacy single-value fields for backward compat
        "oem_diameter": row.get("oem_diameter"),
        "oem_width": row.get("oem_width"),
        "oem_offset": row.get("oem_offset"),
    }


def lookup_bolt_pattern(make: str, model: str, year: int) -> str | None:
    """Look up bolt pattern from the quick-lookup table (backward-compatible wrapper)."""
    specs = lookup_vehicle_specs(make, model, year)
    return specs["bolt_pattern"] if specs else None


# =============================================================================
# Tire, Poke, Brake, and Confidence Calculations
# =============================================================================


def _parse_tire_size(tire_str: str) -> tuple[int, int, int] | None:
    """Parse a tire size string like '225/45R18' → (225, 45, 18)."""
    m = re.match(r"(\d{3})/(\d{2,3})Z?R(\d{2})", tire_str)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def _snap_tire_width(target: int) -> int:
    """Snap a target tire width to the nearest standard width."""
    return min(STANDARD_TIRE_WIDTHS, key=lambda w: abs(w - target))


def calculate_tire_recommendation(
    wheel_diameter: float,
    wheel_width: float,
    oem_tire_str: str | None,
    suspension_type: str = "stock",
) -> TireRecommendation | None:
    """Calculate recommended tire size for a given wheel."""
    if not oem_tire_str:
        return None

    parsed = _parse_tire_size(oem_tire_str)
    if not parsed:
        return None

    oem_width, oem_aspect, oem_dia = parsed
    oem_sidewall = oem_width * (oem_aspect / 100.0)
    oem_overall = (oem_sidewall * 2) + (oem_dia * 25.4)

    # Target tire width from wheel width (range-based)
    width_range = TIRE_WIDTH_BY_WHEEL_WIDTH.get(wheel_width)
    if width_range is None:
        closest = min(
            TIRE_WIDTH_BY_WHEEL_WIDTH.keys(), key=lambda w: abs(w - wheel_width)
        )
        width_range = TIRE_WIDTH_BY_WHEEL_WIDTH[closest]

    # Pick tire width: prefer OEM width if in range, else middle of range
    target_width = oem_width
    if target_width < width_range[0]:
        target_width = width_range[0]
    elif target_width > width_range[1]:
        target_width = width_range[1]
    tire_width = _snap_tire_width(target_width)

    # Width description
    if suspension_type == "lowered":
        width_desc = f"{'Stretched' if tire_width < width_range[0] + 10 else 'Standard'} width ({tire_width}mm) for lowered suspension"
    elif suspension_type == "lifted":
        width_desc = f"{'Wide' if tire_width > width_range[1] - 10 else 'Standard'} width ({tire_width}mm) for lifted suspension"
    else:
        width_desc = f"Standard width ({tire_width}mm) for stock suspension"

    # Find aspect ratio that keeps overall diameter within ±3% of OEM
    dia_int = int(wheel_diameter)
    candidates = COMMON_ASPECT_RATIOS.get(dia_int, [35, 40, 45])
    best_aspect = candidates[0]
    best_diff = float("inf")
    for ar in candidates:
        sw = tire_width * (ar / 100.0)
        od = (sw * 2) + (wheel_diameter * 25.4)
        diff = abs(od - oem_overall) / oem_overall * 100
        if diff < best_diff:
            best_diff = diff
            best_aspect = ar

    sidewall_mm = tire_width * (best_aspect / 100.0)
    overall_mm = (sidewall_mm * 2) + (wheel_diameter * 25.4)
    diff_pct = (overall_mm - oem_overall) / oem_overall * 100

    # Lowered cars benefit from slightly lower profile
    if suspension_type == "lowered" and best_aspect > 30:
        lower_ar = best_aspect - 5
        if lower_ar in [a for ratios in COMMON_ASPECT_RATIOS.values() for a in ratios]:
            sw2 = tire_width * (lower_ar / 100.0)
            od2 = (sw2 * 2) + (wheel_diameter * 25.4)
            diff2 = abs(od2 - oem_overall) / oem_overall * 100
            if diff2 < 5:
                best_aspect = lower_ar
                sidewall_mm = sw2
                overall_mm = od2
                diff_pct = (overall_mm - oem_overall) / oem_overall * 100

    size_str = f"{tire_width}/{best_aspect}R{dia_int}"

    return TireRecommendation(
        size=size_str,
        width_mm=tire_width,
        aspect_ratio=best_aspect,
        sidewall_mm=round(sidewall_mm, 1),
        overall_diameter_mm=round(overall_mm, 1),
        oem_diameter_diff_pct=round(diff_pct, 1),
        width_description=width_desc,
    )


def calculate_poke(
    oem_width: float | None,
    oem_offset: int | None,
    new_width: float,
    new_offset: int,
) -> PokeCalculation | None:
    """Calculate poke/tuck for a wheel relative to OEM specs.

    poke_mm = ((new_width - oem_width) * 25.4 / 2) + (oem_offset - new_offset)
    Positive = poke (wheel sticks out), Negative = tuck (wheel sits in)
    """
    if oem_width is None or oem_offset is None:
        return None

    poke_mm = ((new_width - oem_width) * 25.4 / 2) + (oem_offset - new_offset)
    poke_mm = round(poke_mm, 1)

    abs_poke = abs(poke_mm)

    if abs_poke <= 3:
        stance_label = "flush"
        desc = f"{poke_mm:+.1f}mm (flush)"
    elif poke_mm > 0:
        if abs_poke <= 10:
            stance_label = "mild poke"
            desc = f"+{poke_mm}mm (mild poke — likely fine on stock suspension)"
        elif abs_poke <= 20:
            stance_label = "moderate poke"
            desc = f"+{poke_mm}mm (moderate poke — may need fender rolling)"
        else:
            stance_label = "aggressive"
            desc = (
                f"+{poke_mm}mm (aggressive — requires fender pulling/rolling + camber)"
            )
    else:
        if abs_poke <= 10:
            stance_label = "mild tuck"
            desc = f"{poke_mm}mm (mild tuck)"
        elif abs_poke <= 20:
            stance_label = "moderate tuck"
            desc = f"{poke_mm}mm (moderate tuck)"
        else:
            stance_label = "deep tuck"
            desc = f"{poke_mm}mm (deep tuck — may look recessed)"

    return PokeCalculation(poke_mm=poke_mm, description=desc, stance_label=stance_label)


def check_brake_clearance(
    wheel_diameter: float,
    min_wheel_diameter: float | None,
    is_performance_trim: bool,
    oem_diameter: float | None,
) -> tuple[bool, str | None]:
    """Check if a wheel diameter clears the vehicle's brakes.

    Returns (ok, note). If ok=False, the wheel will NOT clear the calipers.
    """
    if min_wheel_diameter is not None:
        if wheel_diameter < min_wheel_diameter:
            return (
                False,
                f'❌ {wheel_diameter}" wheels will NOT clear the brake calipers '
                f'(minimum {min_wheel_diameter}" required)',
            )

    # General warnings
    if wheel_diameter <= 15.0:
        return (
            False,
            '⚠️ 15" wheels may not clear modern brake calipers — verify before purchase',
        )

    if wheel_diameter <= 17.0 and is_performance_trim:
        return (
            True,
            "⚠️ Brake clearance needed — performance trim has larger calipers",
        )

    if oem_diameter and wheel_diameter < oem_diameter:
        return (
            True,
            f'⚠️ Downsizing from {oem_diameter}" to {wheel_diameter}" — '
            f"verify brake caliper clearance",
        )

    return (True, None)


def vehicle_confidence(vehicle: VehicleSpecs) -> tuple[str, str]:
    """Determine confidence level for a vehicle's specs.

    Returns (level, reason) — level is 'high', 'medium', or 'low'.
    """
    if (
        vehicle.chassis_code
        and vehicle.oem_offset_front is not None
        and vehicle.oem_tire_front
    ):
        return ("high", f"chassis-specific data ({vehicle.chassis_code})")
    if vehicle.oem_offset_front is not None:
        return ("medium", "make/model data — trim-specific details estimated")
    return ("low", "generic data — recommend professional verification")


# =============================================================================
# Full Knowledge Base (preserved from dspy_v2/tools.py)
# =============================================================================


def _resolve_bmw_chassis(
    model_lower: str,
    year: int | None,
    mapping: dict[str, list[tuple[tuple[int, int], str]]],
) -> str | None:
    """Resolve a BMW model + year to a chassis code."""
    entries = mapping.get(model_lower)
    if not entries:
        return None
    if year:
        for (y_start, y_end), chassis in entries:
            if y_start <= year <= y_end:
                return chassis
    return entries[-1][1]


def lookup_known_specs(
    make: str,
    model: str,
    chassis_code: str | None = None,
    year: int | None = None,
) -> dict[str, Any] | None:
    """Lookup specs from the hardcoded vehicle knowledge base.

    This is the primary source of truth for common vehicles.
    Returns a dict with bolt_pattern, center_bore, stud_size,
    oem_diameter, min/max diameter/width/offset, etc.
    """
    make_lower = make.lower()
    model_lower = model.lower()
    chassis_upper = chassis_code.upper() if chassis_code else None

    _bmw_5x120 = {
        "bolt_pattern": "5x120",
        "center_bore": 72.6,
        "stud_size": "M12x1.5",
    }
    _bmw_5x112 = {
        "bolt_pattern": "5x112",
        "center_bore": 66.5,
        "stud_size": "M14x1.25",
    }

    bmw_model_chassis_specs: dict[tuple[str, str], dict[str, Any]] = {
        ("m3", "E30"): {
            **_bmw_5x120,
            "year_start": 1986,
            "year_end": 1991,
            "oem_diameter": 15,
            "min_diameter": 14,
            "max_diameter": 17,
            "oem_width": 7.0,
            "min_width": 7.0,
            "max_width": 9.0,
            "oem_offset": 25,
            "min_offset": 10,
            "max_offset": 35,
        },
    }

    bmw_specs: dict[str, dict[str, Any]] = {
        "E21": {
            "bolt_pattern": "4x100",
            "center_bore": 57.1,
            "stud_size": "M12x1.5",
            "year_start": 1975,
            "year_end": 1983,
            "oem_diameter": 13,
            "min_diameter": 13,
            "max_diameter": 15,
            "oem_width": 5.5,
            "min_width": 5.5,
            "max_width": 7.0,
            "oem_offset": 22,
            "min_offset": 10,
            "max_offset": 35,
        },
        "E30": {
            "bolt_pattern": "4x100",
            "center_bore": 57.1,
            "stud_size": "M12x1.5",
            "year_start": 1982,
            "year_end": 1994,
            "oem_diameter": 14,
            "min_diameter": 13,
            "max_diameter": 17,
            "oem_width": 6.0,
            "min_width": 6.0,
            "max_width": 8.5,
            "oem_offset": 35,
            "min_offset": 10,
            "max_offset": 42,
        },
        "E24": {
            **_bmw_5x120,
            "oem_diameter": 14,
            "min_diameter": 14,
            "max_diameter": 17,
            "oem_width": 6.5,
            "min_width": 6.5,
            "max_width": 9.0,
            "oem_offset": 23,
            "min_offset": 5,
            "max_offset": 35,
        },
        "E28": {
            **_bmw_5x120,
            "oem_diameter": 14,
            "min_diameter": 14,
            "max_diameter": 17,
            "oem_width": 6.5,
            "min_width": 6.5,
            "max_width": 9.0,
            "oem_offset": 23,
            "min_offset": 5,
            "max_offset": 35,
        },
        "E34": {
            **_bmw_5x120,
            "oem_diameter": 15,
            "min_diameter": 15,
            "max_diameter": 18,
            "oem_width": 7.0,
            "min_width": 7.0,
            "max_width": 9.5,
            "oem_offset": 20,
            "min_offset": 5,
            "max_offset": 35,
        },
        "E36": {
            **_bmw_5x120,
            "oem_diameter": 15,
            "min_diameter": 15,
            "max_diameter": 18,
            "oem_width": 7.0,
            "min_width": 7.0,
            "max_width": 9.5,
            "oem_offset": 35,
            "min_offset": 15,
            "max_offset": 45,
        },
        "E38": {
            **_bmw_5x120,
            "oem_diameter": 16,
            "min_diameter": 16,
            "max_diameter": 20,
            "oem_width": 7.5,
            "min_width": 7.0,
            "max_width": 10.0,
            "oem_offset": 24,
            "min_offset": 5,
            "max_offset": 35,
        },
        "E39": {
            "bolt_pattern": "5x120",
            "center_bore": 74.1,
            "stud_size": "M12x1.5",
            "oem_diameter": 16,
            "min_diameter": 16,
            "max_diameter": 19,
            "oem_width": 7.0,
            "min_width": 7.0,
            "max_width": 10.0,
            "oem_offset": 20,
            "min_offset": 5,
            "max_offset": 35,
        },
        "E46": {
            **_bmw_5x120,
            "oem_diameter": 16,
            "min_diameter": 16,
            "max_diameter": 19,
            "oem_width": 7.0,
            "min_width": 7.0,
            "max_width": 9.5,
            "oem_offset": 42,
            "min_offset": 15,
            "max_offset": 47,
        },
        "E60": {
            **_bmw_5x120,
            "oem_diameter": 17,
            "min_diameter": 17,
            "max_diameter": 20,
            "oem_width": 7.5,
            "min_width": 7.5,
            "max_width": 10.0,
            "oem_offset": 20,
            "min_offset": 5,
            "max_offset": 35,
        },
        "E82": {
            **_bmw_5x120,
            "oem_diameter": 16,
            "min_diameter": 16,
            "max_diameter": 19,
            "oem_width": 7.0,
            "min_width": 7.0,
            "max_width": 9.5,
            "oem_offset": 34,
            "min_offset": 15,
            "max_offset": 45,
        },
        "E90": {
            **_bmw_5x120,
            "oem_diameter": 17,
            "min_diameter": 17,
            "max_diameter": 19,
            "oem_width": 8.0,
            "min_width": 7.5,
            "max_width": 10.0,
            "oem_offset": 34,
            "min_offset": 15,
            "max_offset": 45,
        },
        "E92": {
            **_bmw_5x120,
            "oem_diameter": 17,
            "min_diameter": 17,
            "max_diameter": 19,
            "oem_width": 8.0,
            "min_width": 7.5,
            "max_width": 10.0,
            "oem_offset": 34,
            "min_offset": 15,
            "max_offset": 45,
        },
        "F30": {
            **_bmw_5x120,
            "oem_diameter": 18,
            "min_diameter": 17,
            "max_diameter": 20,
            "oem_width": 8.0,
            "min_width": 7.5,
            "max_width": 10.0,
            "oem_offset": 34,
            "min_offset": 15,
            "max_offset": 45,
        },
        "F32": {
            **_bmw_5x120,
            "oem_diameter": 18,
            "min_diameter": 17,
            "max_diameter": 20,
            "oem_width": 8.0,
            "min_width": 7.5,
            "max_width": 10.5,
            "oem_offset": 34,
            "min_offset": 15,
            "max_offset": 45,
        },
        "F80": {
            **_bmw_5x120,
            "oem_diameter": 18,
            "min_diameter": 18,
            "max_diameter": 20,
            "oem_width": 9.0,
            "min_width": 8.5,
            "max_width": 10.5,
            "oem_offset": 29,
            "min_offset": 15,
            "max_offset": 40,
        },
        "F82": {
            **_bmw_5x120,
            "oem_diameter": 18,
            "min_diameter": 18,
            "max_diameter": 20,
            "oem_width": 9.0,
            "min_width": 8.5,
            "max_width": 10.5,
            "oem_offset": 29,
            "min_offset": 15,
            "max_offset": 40,
        },
        "G20": {
            **_bmw_5x112,
            "oem_diameter": 18,
            "min_diameter": 17,
            "max_diameter": 20,
            "oem_width": 7.5,
            "min_width": 7.5,
            "max_width": 10.0,
            "oem_offset": 30,
            "min_offset": 15,
            "max_offset": 40,
        },
        "G80": {
            **_bmw_5x112,
            "oem_diameter": 18,
            "min_diameter": 18,
            "max_diameter": 20,
            "oem_width": 9.0,
            "min_width": 8.5,
            "max_width": 10.5,
            "oem_offset": 26,
            "min_offset": 15,
            "max_offset": 38,
        },
        "G82": {
            **_bmw_5x112,
            "oem_diameter": 18,
            "min_diameter": 18,
            "max_diameter": 20,
            "oem_width": 9.0,
            "min_width": 8.5,
            "max_width": 10.5,
            "oem_offset": 26,
            "min_offset": 15,
            "max_offset": 38,
        },
    }

    _bmw_model_to_chassis: dict[str, list[tuple[tuple[int, int], str]]] = {
        "m3": [
            ((1986, 1991), "E30"),
            ((1992, 1999), "E36"),
            ((2000, 2006), "E46"),
            ((2007, 2013), "E90"),
            ((2014, 2018), "F80"),
            ((2019, 2030), "G80"),
        ],
        "m4": [
            ((2014, 2020), "F82"),
            ((2021, 2030), "G82"),
        ],
        "m5": [
            ((1984, 1988), "E28"),
            ((1988, 1995), "E34"),
            ((1998, 2003), "E39"),
            ((2004, 2010), "E60"),
        ],
        "m6": [((1983, 1989), "E24")],
        "635csi": [((1976, 1989), "E24")],
        "325i": [
            ((1982, 1991), "E30"),
            ((1992, 1998), "E36"),
            ((1999, 2006), "E46"),
            ((2007, 2013), "E90"),
        ],
        "328i": [
            ((1992, 1998), "E36"),
            ((1999, 2006), "E46"),
            ((2007, 2013), "E90"),
            ((2012, 2018), "F30"),
        ],
        "330i": [
            ((1999, 2006), "E46"),
            ((2007, 2013), "E90"),
            ((2012, 2018), "F30"),
            ((2019, 2030), "G20"),
        ],
        "335i": [
            ((2007, 2013), "E90"),
            ((2012, 2015), "F30"),
        ],
        "340i": [
            ((2016, 2018), "F30"),
            ((2019, 2030), "G20"),
        ],
        "m340i": [((2019, 2030), "G20")],
        "535i": [
            ((1988, 1995), "E34"),
            ((1996, 2003), "E39"),
            ((2004, 2010), "E60"),
        ],
        "540i": [
            ((1996, 2003), "E39"),
            ((2004, 2010), "E60"),
        ],
        "528i": [((1996, 2003), "E39")],
        "1 series": [((2004, 2013), "E82")],
        "128i": [((2008, 2013), "E82")],
        "135i": [((2008, 2013), "E82")],
        "3 series": [
            ((1982, 1991), "E30"),
            ((1992, 1999), "E36"),
            ((2000, 2006), "E46"),
            ((2007, 2013), "E90"),
            ((2012, 2018), "F30"),
            ((2019, 2030), "G20"),
        ],
        "4 series": [((2014, 2020), "F32")],
        "5 series": [
            ((1981, 1988), "E28"),
            ((1988, 1995), "E34"),
            ((1996, 2003), "E39"),
            ((2004, 2010), "E60"),
        ],
        "6 series": [((1976, 1989), "E24")],
        "7 series": [((1994, 2001), "E38")],
        "740i": [((1994, 2001), "E38")],
        "750i": [((1994, 2001), "E38")],
    }

    # BMW: check model+chassis overrides first (e.g. E30 M3 = 5x120)
    if make_lower == "bmw":
        if chassis_upper:
            model_chassis_key = (model_lower, chassis_upper)
            if model_chassis_key in bmw_model_chassis_specs:
                return bmw_model_chassis_specs[model_chassis_key]

        resolved_chassis = _resolve_bmw_chassis(
            model_lower, year, _bmw_model_to_chassis
        )
        if resolved_chassis:
            model_chassis_key = (model_lower, resolved_chassis)
            if model_chassis_key in bmw_model_chassis_specs:
                return bmw_model_chassis_specs[model_chassis_key]

        if chassis_upper and chassis_upper in bmw_specs:
            return bmw_specs[chassis_upper]
        if resolved_chassis and resolved_chassis in bmw_specs:
            return bmw_specs[resolved_chassis]

    # Honda specs
    _honda_4x100 = {
        "bolt_pattern": "4x100",
        "center_bore": 56.1,
        "stud_size": "M12x1.5",
        "oem_diameter": 14,
        "min_diameter": 14,
        "max_diameter": 17,
        "oem_width": 5.5,
        "min_width": 6.0,
        "max_width": 8.0,
        "oem_offset": 45,
        "min_offset": 25,
        "max_offset": 50,
    }
    _honda_5x114 = {
        "bolt_pattern": "5x114.3",
        "center_bore": 64.1,
        "stud_size": "M12x1.5",
        "oem_diameter": 16,
        "min_diameter": 16,
        "max_diameter": 19,
        "oem_width": 7.0,
        "min_width": 7.0,
        "max_width": 9.5,
        "oem_offset": 45,
        "min_offset": 30,
        "max_offset": 50,
    }
    honda_specs: dict[tuple[str, str | None], dict[str, Any]] = {
        ("civic type r", "fk8"): {
            "bolt_pattern": "5x120",
            "center_bore": 64.1,
            "stud_size": "M14x1.5",
            "oem_diameter": 20,
            "min_diameter": 18,
            "max_diameter": 20,
            "oem_width": 8.5,
            "min_width": 8.5,
            "max_width": 10.0,
            "oem_offset": 60,
            "min_offset": 35,
            "max_offset": 50,
        },
        ("civic type r", "fl5"): {
            "bolt_pattern": "5x120",
            "center_bore": 64.1,
            "stud_size": "M14x1.5",
            "oem_diameter": 19,
            "min_diameter": 18,
            "max_diameter": 20,
            "oem_width": 9.5,
            "min_width": 8.5,
            "max_width": 10.5,
            "oem_offset": 45,
            "min_offset": 35,
            "max_offset": 50,
        },
        ("s2000", None): {
            "bolt_pattern": "5x114.3",
            "center_bore": 64.1,
            "stud_size": "M12x1.5",
            "oem_diameter": 16,
            "min_diameter": 16,
            "max_diameter": 18,
            "oem_width": 6.5,
            "min_width": 7.0,
            "max_width": 9.0,
            "oem_offset": 55,
            "min_offset": 25,
            "max_offset": 55,
        },
        ("accord", None): _honda_5x114,
    }

    if make_lower in ("honda", "acura"):
        for (m, c), specs in honda_specs.items():
            if model_lower in m or m in model_lower:
                if (
                    c is None
                    or (chassis_upper and c.upper() == chassis_upper)
                    or m == model_lower
                ):
                    return specs
        if "civic" in model_lower and "type r" not in model_lower:
            if year and year <= 2005:
                return _honda_4x100
            return _honda_5x114
        if "prelude" in model_lower:
            if year and year <= 1991:
                return {**_honda_4x100, "oem_diameter": 14, "max_diameter": 16}
            if year and year <= 1996:
                return {
                    "bolt_pattern": "4x114.3",
                    "center_bore": 64.1,
                    "stud_size": "M12x1.5",
                    "oem_diameter": 15,
                    "min_diameter": 15,
                    "max_diameter": 17,
                    "oem_width": 6.0,
                    "min_width": 6.0,
                    "max_width": 8.0,
                    "oem_offset": 45,
                    "min_offset": 25,
                    "max_offset": 50,
                }
            if year and year >= 1997:
                return _honda_5x114
            return None
        if make_lower == "acura":
            return _honda_5x114

    # Subaru specs
    subaru_specs: dict[tuple[str, str | None], dict[str, Any]] = {
        ("wrx", "va"): {
            "bolt_pattern": "5x114.3",
            "center_bore": 56.1,
            "stud_size": "M12x1.25",
            "oem_diameter": 17,
            "min_diameter": 17,
            "max_diameter": 19,
            "oem_width": 8.0,
            "min_width": 7.5,
            "max_width": 9.5,
            "oem_offset": 48,
            "min_offset": 30,
            "max_offset": 55,
        },
        ("wrx sti", "va"): {
            "bolt_pattern": "5x114.3",
            "center_bore": 56.1,
            "stud_size": "M12x1.25",
            "oem_diameter": 19,
            "min_diameter": 18,
            "max_diameter": 19,
            "oem_width": 8.5,
            "min_width": 8.0,
            "max_width": 10.0,
            "oem_offset": 55,
            "min_offset": 30,
            "max_offset": 55,
        },
        ("wrx", None): {
            "bolt_pattern": "5x100",
            "center_bore": 56.1,
            "stud_size": "M12x1.25",
            "oem_diameter": 17,
            "min_diameter": 16,
            "max_diameter": 18,
            "oem_width": 7.0,
            "min_width": 7.0,
            "max_width": 9.0,
            "oem_offset": 48,
            "min_offset": 30,
            "max_offset": 55,
        },
    }

    if make_lower == "subaru":
        for (m, c), specs in subaru_specs.items():
            if model_lower in m or m in model_lower:
                if c is None or (chassis_upper and c.upper() == chassis_upper):
                    return specs

    # Toyota / Scion specs
    toyota_specs: dict[tuple[str, str | None], dict[str, Any]] = {
        ("86", "zn6"): {
            "bolt_pattern": "5x100",
            "center_bore": 56.1,
            "stud_size": "M12x1.25",
            "oem_diameter": 17,
            "min_diameter": 17,
            "max_diameter": 18,
            "oem_width": 7.0,
            "min_width": 7.0,
            "max_width": 9.5,
            "oem_offset": 48,
            "min_offset": 30,
            "max_offset": 55,
        },
        ("gr86", "zn8"): {
            "bolt_pattern": "5x114.3",
            "center_bore": 56.1,
            "stud_size": "M12x1.25",
            "oem_diameter": 18,
            "min_diameter": 17,
            "max_diameter": 19,
            "oem_width": 7.5,
            "min_width": 7.0,
            "max_width": 9.5,
            "oem_offset": 48,
            "min_offset": 30,
            "max_offset": 55,
        },
        ("supra", "a80"): {
            "bolt_pattern": "5x114.3",
            "center_bore": 60.1,
            "stud_size": "M12x1.5",
            "oem_diameter": 17,
            "min_diameter": 17,
            "max_diameter": 19,
            "oem_width": 8.0,
            "min_width": 8.0,
            "max_width": 10.0,
            "oem_offset": 40,
            "min_offset": 15,
            "max_offset": 50,
        },
        ("supra", "a90"): {
            "bolt_pattern": "5x112",
            "center_bore": 66.5,
            "stud_size": "M14x1.25",
            "oem_diameter": 19,
            "min_diameter": 18,
            "max_diameter": 20,
            "oem_width": 9.0,
            "min_width": 8.5,
            "max_width": 10.5,
            "oem_offset": 32,
            "min_offset": 15,
            "max_offset": 40,
        },
        ("camry", None): {
            "bolt_pattern": "5x114.3",
            "center_bore": 60.1,
            "stud_size": "M12x1.5",
            "oem_diameter": 17,
            "min_diameter": 16,
            "max_diameter": 19,
            "oem_width": 7.0,
            "min_width": 7.0,
            "max_width": 9.0,
            "oem_offset": 40,
            "min_offset": 25,
            "max_offset": 50,
        },
        ("tacoma", None): {
            "bolt_pattern": "6x139.7",
            "center_bore": 106.1,
            "stud_size": "M12x1.5",
            "oem_diameter": 16,
            "min_diameter": 16,
            "max_diameter": 18,
            "oem_width": 7.0,
            "min_width": 7.0,
            "max_width": 9.0,
            "oem_offset": 30,
            "min_offset": -10,
            "max_offset": 40,
        },
    }

    if make_lower in ("toyota", "scion"):
        for (m, c), specs in toyota_specs.items():
            if model_lower in m or m in model_lower:
                if c is None or (chassis_upper and c.upper() == chassis_upper):
                    return specs
        if "supra" in model_lower:
            if year and year <= 2002:
                return toyota_specs[("supra", "a80")]
            if year and year >= 2019:
                return toyota_specs[("supra", "a90")]

    # Nissan specs
    nissan_specs: dict[tuple[str, str | None], dict[str, Any]] = {
        ("240sx", "s13"): {
            "bolt_pattern": "4x114.3",
            "center_bore": 66.1,
            "stud_size": "M12x1.25",
            "oem_diameter": 15,
            "min_diameter": 15,
            "max_diameter": 18,
            "oem_width": 6.0,
            "min_width": 7.0,
            "max_width": 9.5,
            "oem_offset": 40,
            "min_offset": 0,
            "max_offset": 30,
        },
        ("240sx", "s14"): {
            "bolt_pattern": "5x114.3",
            "center_bore": 66.1,
            "stud_size": "M12x1.25",
            "oem_diameter": 16,
            "min_diameter": 16,
            "max_diameter": 18,
            "oem_width": 6.5,
            "min_width": 7.0,
            "max_width": 9.5,
            "oem_offset": 40,
            "min_offset": 0,
            "max_offset": 35,
        },
        ("350z", None): {
            "bolt_pattern": "5x114.3",
            "center_bore": 66.1,
            "stud_size": "M12x1.25",
            "oem_diameter": 18,
            "min_diameter": 17,
            "max_diameter": 19,
            "oem_width": 8.0,
            "min_width": 8.0,
            "max_width": 10.5,
            "oem_offset": 30,
            "min_offset": 5,
            "max_offset": 40,
        },
        ("370z", None): {
            "bolt_pattern": "5x114.3",
            "center_bore": 66.1,
            "stud_size": "M12x1.25",
            "oem_diameter": 18,
            "min_diameter": 18,
            "max_diameter": 20,
            "oem_width": 9.0,
            "min_width": 8.5,
            "max_width": 11.0,
            "oem_offset": 30,
            "min_offset": 5,
            "max_offset": 40,
        },
    }

    if make_lower == "nissan":
        for (m, c), specs in nissan_specs.items():
            if model_lower in m or m in model_lower:
                if c is None or (chassis_upper and c.upper() == chassis_upper):
                    return specs

    # Mazda Miata specs
    miata_specs: dict[tuple[str, str | None], dict[str, Any]] = {
        ("miata", "na"): {
            "bolt_pattern": "4x100",
            "center_bore": 54.1,
            "stud_size": "M12x1.5",
            "oem_diameter": 14,
            "min_diameter": 14,
            "max_diameter": 16,
            "oem_width": 5.5,
            "min_width": 6.0,
            "max_width": 8.0,
            "oem_offset": 45,
            "min_offset": 25,
            "max_offset": 50,
        },
        ("miata", "nb"): {
            "bolt_pattern": "4x100",
            "center_bore": 54.1,
            "stud_size": "M12x1.5",
            "oem_diameter": 15,
            "min_diameter": 14,
            "max_diameter": 17,
            "oem_width": 6.0,
            "min_width": 6.0,
            "max_width": 8.0,
            "oem_offset": 40,
            "min_offset": 20,
            "max_offset": 45,
        },
        ("mx-5", "nc"): {
            "bolt_pattern": "5x114.3",
            "center_bore": 67.1,
            "stud_size": "M12x1.5",
            "oem_diameter": 17,
            "min_diameter": 16,
            "max_diameter": 18,
            "oem_width": 7.0,
            "min_width": 6.5,
            "max_width": 8.5,
            "oem_offset": 50,
            "min_offset": 30,
            "max_offset": 55,
        },
        ("mx-5", "nd"): {
            "bolt_pattern": "5x114.3",
            "center_bore": 67.1,
            "stud_size": "M12x1.5",
            "oem_diameter": 16,
            "min_diameter": 16,
            "max_diameter": 17,
            "oem_width": 6.5,
            "min_width": 6.5,
            "max_width": 8.0,
            "oem_offset": 50,
            "min_offset": 35,
            "max_offset": 55,
        },
    }

    if make_lower == "mazda":
        for (m, c), specs in miata_specs.items():
            if model_lower in m or m in model_lower:
                if c is None or (chassis_upper and c.upper() == chassis_upper):
                    return specs
        if "miata" in model_lower or "mx-5" in model_lower or "mx5" in model_lower:
            if year and year <= 1997:
                return miata_specs[("miata", "na")]
            if year and year <= 2005:
                return miata_specs[("miata", "nb")]
            if year and year <= 2015:
                return miata_specs[("mx-5", "nc")]
            return miata_specs[("mx-5", "nd")]

    # Mitsubishi
    if make_lower == "mitsubishi":
        if "evo" in model_lower or "lancer" in model_lower:
            return {
                "bolt_pattern": "5x114.3",
                "center_bore": 67.1,
                "stud_size": "M12x1.5",
                "oem_diameter": 18,
                "min_diameter": 17,
                "max_diameter": 19,
                "oem_width": 8.5,
                "min_width": 8.0,
                "max_width": 10.0,
                "oem_offset": 38,
                "min_offset": 15,
                "max_offset": 45,
            }

    # Volkswagen
    if make_lower in ("volkswagen", "vw"):
        return {
            "bolt_pattern": "5x112",
            "center_bore": 57.1,
            "stud_size": "M14x1.5",
            "oem_diameter": 18,
            "min_diameter": 17,
            "max_diameter": 19,
            "oem_width": 7.5,
            "min_width": 7.0,
            "max_width": 9.5,
            "oem_offset": 45,
            "min_offset": 30,
            "max_offset": 50,
        }

    # Audi
    if make_lower == "audi":
        return {
            "bolt_pattern": "5x112",
            "center_bore": 66.5,
            "stud_size": "M14x1.5",
            "oem_diameter": 18,
            "min_diameter": 18,
            "max_diameter": 20,
            "oem_width": 8.0,
            "min_width": 7.5,
            "max_width": 10.0,
            "oem_offset": 35,
            "min_offset": 20,
            "max_offset": 45,
        }

    # Mercedes-Benz
    if make_lower in ("mercedes-benz", "mercedes"):
        return {
            "bolt_pattern": "5x112",
            "center_bore": 66.6,
            "stud_size": "M14x1.5",
            "oem_diameter": 18,
            "min_diameter": 17,
            "max_diameter": 20,
            "oem_width": 8.0,
            "min_width": 7.5,
            "max_width": 10.0,
            "oem_offset": 43,
            "min_offset": 25,
            "max_offset": 50,
        }

    # Porsche
    if make_lower == "porsche":
        return {
            "bolt_pattern": "5x130",
            "center_bore": 71.6,
            "stud_size": "M14x1.5",
            "oem_diameter": 19,
            "min_diameter": 18,
            "max_diameter": 21,
            "oem_width": 8.5,
            "min_width": 8.0,
            "max_width": 11.0,
            "oem_offset": 50,
            "min_offset": 30,
            "max_offset": 60,
        }

    # Ford
    if make_lower == "ford":
        if "f-150" in model_lower or "f150" in model_lower:
            return {
                "bolt_pattern": "6x135",
                "center_bore": 87.1,
                "stud_size": "M14x1.5",
                "oem_diameter": 17,
                "min_diameter": 17,
                "max_diameter": 22,
                "oem_width": 7.5,
                "min_width": 7.5,
                "max_width": 10.0,
                "oem_offset": 44,
                "min_offset": -12,
                "max_offset": 50,
            }
        if "mustang" in model_lower:
            stud = '1/2"x20' if (year and year < 2015) else "M14x1.5"
            return {
                "bolt_pattern": "5x114.3",
                "center_bore": 70.5,
                "stud_size": stud,
                "oem_diameter": 18,
                "min_diameter": 17,
                "max_diameter": 20,
                "oem_width": 8.5,
                "min_width": 8.0,
                "max_width": 11.0,
                "oem_offset": 45,
                "min_offset": 20,
                "max_offset": 55,
            }
        if "focus" in model_lower:
            return {
                "bolt_pattern": "5x108",
                "center_bore": 63.4,
                "stud_size": "M12x1.5",
                "oem_diameter": 18,
                "min_diameter": 17,
                "max_diameter": 19,
                "oem_width": 7.5,
                "min_width": 7.0,
                "max_width": 9.0,
                "oem_offset": 50,
                "min_offset": 35,
                "max_offset": 55,
            }

    # Chevrolet
    if make_lower in ("chevrolet", "chevy"):
        if "silverado" in model_lower:
            return {
                "bolt_pattern": "6x139.7",
                "center_bore": 78.1,
                "stud_size": "M14x1.5",
                "oem_diameter": 17,
                "min_diameter": 17,
                "max_diameter": 22,
                "oem_width": 7.5,
                "min_width": 7.5,
                "max_width": 10.0,
                "oem_offset": 28,
                "min_offset": -12,
                "max_offset": 44,
            }
        if "camaro" in model_lower:
            return {
                "bolt_pattern": "5x120",
                "center_bore": 67.1,
                "stud_size": "M14x1.5",
                "oem_diameter": 18,
                "min_diameter": 18,
                "max_diameter": 20,
                "oem_width": 8.5,
                "min_width": 8.0,
                "max_width": 11.0,
                "oem_offset": 35,
                "min_offset": 15,
                "max_offset": 45,
            }
        if "corvette" in model_lower:
            return {
                "bolt_pattern": "5x120",
                "center_bore": 70.3,
                "stud_size": "M14x1.5",
                "oem_diameter": 19,
                "min_diameter": 18,
                "max_diameter": 21,
                "oem_width": 8.5,
                "min_width": 8.5,
                "max_width": 12.0,
                "oem_offset": 30,
                "min_offset": 15,
                "max_offset": 50,
            }

    # Dodge
    if make_lower == "dodge":
        if "challenger" in model_lower or "charger" in model_lower:
            return {
                "bolt_pattern": "5x115",
                "center_bore": 71.5,
                "stud_size": "M14x1.5",
                "oem_diameter": 18,
                "min_diameter": 18,
                "max_diameter": 22,
                "oem_width": 7.5,
                "min_width": 7.5,
                "max_width": 11.0,
                "oem_offset": 20,
                "min_offset": 5,
                "max_offset": 35,
            }

    # Ram
    if make_lower == "ram":
        return {
            "bolt_pattern": "6x139.7",
            "center_bore": 77.8,
            "stud_size": "M14x1.5",
            "oem_diameter": 18,
            "min_diameter": 17,
            "max_diameter": 22,
            "oem_width": 8.0,
            "min_width": 7.5,
            "max_width": 10.0,
            "oem_offset": 25,
            "min_offset": -12,
            "max_offset": 44,
        }

    # Tesla
    if make_lower == "tesla":
        if "model 3" in model_lower or "model3" in model_lower:
            return {
                "bolt_pattern": "5x114.3",
                "center_bore": 64.1,
                "stud_size": "M14x1.5",
                "oem_diameter": 18,
                "min_diameter": 18,
                "max_diameter": 20,
                "oem_width": 8.5,
                "min_width": 8.0,
                "max_width": 10.0,
                "oem_offset": 35,
                "min_offset": 20,
                "max_offset": 45,
            }
        if "model s" in model_lower or "models" in model_lower:
            return {
                "bolt_pattern": "5x120",
                "center_bore": 64.1,
                "stud_size": "M14x1.5",
                "oem_diameter": 19,
                "min_diameter": 19,
                "max_diameter": 21,
                "oem_width": 8.5,
                "min_width": 8.5,
                "max_width": 10.5,
                "oem_offset": 40,
                "min_offset": 25,
                "max_offset": 50,
            }
        if "model y" in model_lower or "modely" in model_lower:
            return {
                "bolt_pattern": "5x114.3",
                "center_bore": 64.1,
                "stud_size": "M14x1.5",
                "oem_diameter": 19,
                "min_diameter": 18,
                "max_diameter": 21,
                "oem_width": 9.5,
                "min_width": 8.5,
                "max_width": 10.5,
                "oem_offset": 35,
                "min_offset": 20,
                "max_offset": 45,
            }

    # Datsun
    if make_lower == "datsun":
        if "240z" in model_lower or "260z" in model_lower or "280z" in model_lower:
            return {
                "bolt_pattern": "4x114.3",
                "center_bore": 66.1,
                "stud_size": "M12x1.25",
                "oem_diameter": 14,
                "min_diameter": 14,
                "max_diameter": 16,
                "oem_width": 5.5,
                "min_width": 6.0,
                "max_width": 8.0,
                "oem_offset": 0,
                "min_offset": -10,
                "max_offset": 20,
            }

    return None


# =============================================================================
# Validation Helpers
# =============================================================================


def validate_bolt_pattern(pattern: str) -> bool:
    """Validate that a bolt pattern is in the correct format."""
    match = re.match(r"^[4-8]x\d{2,3}(\.\d)?$", pattern, re.IGNORECASE)
    return match is not None


# =============================================================================
# Fitment Scoring Engine
# =============================================================================


def score_fitment(
    wheel: KanseiWheel,
    vehicle: VehicleSpecs,
    position: str = "front",
) -> FitmentResult:
    """Score a wheel's compatibility with a vehicle.

    Returns a FitmentResult with a 0.0-1.0 score and fitment notes.

    Hub bore is checked per-wheel using wheel.center_bore from the database.
    Kansei bore varies by product line (73.1mm street, 106.1mm truck, etc.)

    Hub bore logic (3-way):
      - wheel bore < vehicle hub_bore → HARD REJECT (physically cannot mount)
      - wheel bore == vehicle hub_bore → perfect hub-centric fit
      - wheel bore > vehicle hub_bore → hub-centric rings required
    """
    notes: list[str] = []
    mods_needed: list[str] = []
    score = 1.0
    wheel_bore = wheel.center_bore

    # === HARD REJECTION: Bolt pattern mismatch ===
    if wheel.bolt_pattern.upper() != vehicle.bolt_pattern.upper():
        return FitmentResult(
            wheel=wheel,
            fitment_score=0.0,
            offset_delta=0,
            diameter_delta=0.0,
            notes=["❌ Bolt pattern mismatch — incompatible"],
        )

    # === HARD REJECTION: Hub bore incompatibility ===
    if vehicle.hub_bore is not None:
        if wheel_bore < vehicle.hub_bore:
            return FitmentResult(
                wheel=wheel,
                fitment_score=0.0,
                offset_delta=0,
                diameter_delta=0.0,
                notes=[
                    f"❌ INCOMPATIBLE: Kansei bore ({wheel_bore}mm) is smaller "
                    f"than vehicle hub ({vehicle.hub_bore}mm). The wheel cannot physically "
                    f"mount on this hub. Hub-centric rings CANNOT fix this."
                ],
            )
        elif wheel_bore == vehicle.hub_bore:
            notes.append("✅ Perfect hub-centric fit — no rings needed")
        else:
            notes.append(
                f"✅ Hub-centric rings needed ({wheel_bore}mm → {vehicle.hub_bore}mm)"
            )
            mods_needed.append(f"Hub-centric rings ({vehicle.hub_bore}mm)")

    # === BRAKE CLEARANCE ===
    brake_ok, brake_note = check_brake_clearance(
        wheel.diameter,
        vehicle.min_wheel_diameter,
        vehicle.is_performance_trim,
        vehicle.oem_diameter,
    )
    if brake_note:
        notes.append(brake_note)
    if not brake_ok:
        return FitmentResult(
            wheel=wheel,
            fitment_score=0.0,
            offset_delta=0,
            diameter_delta=0.0,
            notes=notes,
            brake_clearance_ok=False,
            brake_clearance_note=brake_note,
        )

    # === POKE CALCULATION ===
    # Use front or rear OEM specs based on position
    if position == "rear" and vehicle.oem_width_rear is not None:
        ref_width = vehicle.oem_width_rear
        ref_offset = vehicle.oem_offset_rear
    else:
        ref_width = vehicle.oem_width_front
        ref_offset = vehicle.oem_offset_front

    poke = None
    if ref_width is not None and ref_offset is not None:
        poke = calculate_poke(
            oem_width=ref_width,
            oem_offset=ref_offset,
            new_width=wheel.width,
            new_offset=wheel.wheel_offset,
        )

    if poke is not None:
        notes.append(f"Calculated poke: {poke.description}")

        # Poke impact on score
        abs_poke = abs(poke.poke_mm)
        if abs_poke <= 3:
            pass  # flush — no penalty
        elif abs_poke <= 10:
            score -= 0.05
        elif abs_poke <= 20:
            score -= 0.15
            if poke.poke_mm > 0:
                mods_needed.append("Fender roll recommended")
        else:
            score -= 0.3
            if poke.poke_mm > 0:
                mods_needed.append("Fender work + possible camber adjustment")

    # === OFFSET DELTA ===
    offset_delta = 0
    if ref_offset is not None:
        offset_delta = wheel.wheel_offset - ref_offset

    # === DIAMETER DELTA ===
    diameter_delta = 0.0
    if vehicle.oem_diameter is not None:
        diameter_delta = wheel.diameter - vehicle.oem_diameter
        abs_dia = abs(diameter_delta)
        if abs_dia == 0:
            notes.append("✅ Same diameter as OEM")
        elif abs_dia <= 1:
            score -= 0.05
        elif abs_dia <= 2:
            score -= 0.15
        else:
            score -= 0.3

    # === TIRE RECOMMENDATION ===
    ref_tire = (
        vehicle.oem_tire_rear
        if position == "rear" and vehicle.oem_tire_rear
        else vehicle.oem_tire_front
    )
    tire_rec = calculate_tire_recommendation(
        wheel_diameter=wheel.diameter,
        wheel_width=wheel.width,
        oem_tire_str=ref_tire,
        suspension_type=vehicle.suspension_type,
    )
    if tire_rec:
        notes.append(
            f"Tire: {tire_rec.size} → Sidewall: {tire_rec.sidewall_mm}mm | "
            f"{tire_rec.width_description}"
        )
        if abs(tire_rec.oem_diameter_diff_pct) > 3.0:
            score -= 0.1
            notes.append(
                f"⚠️ Overall diameter {tire_rec.oem_diameter_diff_pct:+.1f}% from OEM "
                f"— speedometer will read off"
            )

    # === STAGGERED NOTES ===
    if vehicle.is_staggered_stock and position == "front":
        notes.append(
            "⚠️ Vehicle has staggered OEM setup — square aftermarket "
            "enables tire rotation but may change handling"
        )

    # === WIDTH CONSIDERATIONS ===
    if wheel.width >= 10.0:
        notes.append("ℹ️ Wide wheel — verify fender clearance and tire availability")

    # === STOCK AVAILABILITY ===
    if not wheel.in_stock:
        score -= 0.1
        notes.append("⚠️ Currently out of stock")

    # === CONFIDENCE ===
    conf_level, conf_reason = vehicle_confidence(vehicle)

    score = max(0.0, min(1.0, score))

    return FitmentResult(
        wheel=wheel,
        fitment_score=round(score, 2),
        offset_delta=offset_delta,
        diameter_delta=round(diameter_delta, 1),
        notes=notes,
        tire_recommendation=tire_rec,
        poke=poke,
        setup_type="staggered" if vehicle.is_staggered_stock else "square",
        position=position,
        brake_clearance_ok=brake_ok,
        brake_clearance_note=brake_note,
        mods_needed=mods_needed if mods_needed else [],
        confidence=conf_level,
        confidence_reason=conf_reason,
    )
