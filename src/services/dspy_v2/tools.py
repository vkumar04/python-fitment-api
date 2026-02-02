"""Tools for the DSPy v2 pipeline.

Provides vehicle spec lookup: knowledge base first, then wheel-size.com scraping.
All functions are **synchronous** because the pipeline runs inside
``asyncio.to_thread()`` from the RAG service.
"""

import logging
import re
from typing import Any

from ..wheel_size_lookup import OEMSpecs, get_wheel_size_lookup

logger = logging.getLogger(__name__)


def search_vehicle_specs_web(
    year: int | None,
    make: str,
    model: str,
    chassis_code: str | None = None,
) -> dict[str, Any]:
    """Look up vehicle wheel specs from knowledge base, then wheel-size.com.

    1. Try hardcoded knowledge base (fast, reliable for common cars).
    2. If not found and we have a year, scrape wheel-size.com.
    3. Validate scraped data before returning.

    Returns dict with specs on success, or error info on failure.
    """
    # Step 1: Knowledge base lookup
    specs = _lookup_known_specs(make, model, chassis_code, year)
    if specs:
        return {
            "found": True,
            "source": "knowledge_base",
            "source_url": f"https://wheel-size.com/{make.lower()}/{model.lower().replace(' ', '-')}/",
            "confidence": 0.85,
            **specs,
        }

    # Step 2: Scrape wheel-size.com (requires year for URL construction)
    if year:
        scraped = _scrape_wheel_size(year, make, model)
        if scraped:
            return scraped

    # Nothing found
    query_parts = [str(year)] if year else []
    query_parts.extend([make, model])
    if chassis_code:
        query_parts.append(chassis_code)
    return {
        "found": False,
        "error": f"Could not find wheel specs for {' '.join(query_parts)}",
        "suggestion": "Try searching with the chassis code or a specific year",
    }


def _scrape_wheel_size(
    year: int, make: str, model: str
) -> dict[str, Any] | None:
    """Scrape wheel-size.com and validate the results."""
    try:
        lookup = get_wheel_size_lookup()
        oem: OEMSpecs | None = lookup.lookup(year, make, model)
    except Exception as e:
        logger.warning("wheel-size.com scrape failed: %s", e)
        return None

    if oem is None:
        return None

    # Validate scraped data
    if not validate_bolt_pattern(oem.bolt_pattern):
        logger.warning("Scraped bolt pattern invalid: %s", oem.bolt_pattern)
        return None

    if oem.center_bore > 0 and not validate_center_bore(oem.center_bore):
        logger.warning("Scraped center bore invalid: %s", oem.center_bore)
        return None

    if not oem.oem_wheel_sizes:
        logger.warning("No wheel sizes scraped for %s %s %s", year, make, model)
        return None

    if not validate_offset(oem.oem_offset_min) or not validate_offset(oem.oem_offset_max):
        logger.warning("Scraped offset range invalid: %s-%s", oem.oem_offset_min, oem.oem_offset_max)
        return None

    # Convert OEM specs to pipeline format with safe aftermarket ranges
    return _oem_to_pipeline_specs(oem)


def _oem_to_pipeline_specs(oem: OEMSpecs) -> dict[str, Any]:
    """Convert scraped OEMSpecs to the dict format the pipeline expects.

    Computes safe aftermarket ranges from OEM data:
    - min_diameter: smallest OEM - 1 (brake clearance floor)
    - max_diameter: largest OEM + 2
    - width: parsed from OEM wheel sizes ± 1"
    - offset: OEM range ± 15mm for aftermarket flexibility
    """
    # Parse diameters and widths from OEM wheel sizes (e.g. "17x7", "18x8")
    oem_diameters: list[int] = []
    oem_widths: list[float] = []
    for size in oem.oem_wheel_sizes:
        parts = size.split("x")
        if len(parts) == 2:
            try:
                oem_diameters.append(int(parts[0]))
                oem_widths.append(float(parts[1]))
            except ValueError:
                continue

    min_d = min(oem_diameters) if oem_diameters else 15
    max_d = max(oem_diameters) if oem_diameters else 18
    min_w = min(oem_widths) if oem_widths else 6.5
    max_w = max(oem_widths) if oem_widths else 8.0

    return {
        "found": True,
        "source": "wheel_size_scrape",
        "source_url": f"https://www.wheel-size.com/size/{oem.make.lower().replace(' ', '-')}/{oem.model.lower().replace(' ', '-')}/{oem.year}/",
        "confidence": 0.7,
        "bolt_pattern": oem.bolt_pattern,
        "center_bore": oem.center_bore if oem.center_bore > 0 else 67.1,
        "stud_size": oem.stud_size or "",
        "oem_diameter": max_d,
        "min_diameter": max(min_d - 1, 13),
        "max_diameter": min(max_d + 2, 22),
        "oem_width": max_w,
        "min_width": max(min_w - 1.0, 5.0),
        "max_width": min(max_w + 1.5, 12.0),
        "oem_offset": (oem.oem_offset_min + oem.oem_offset_max) // 2,
        "min_offset": max(oem.oem_offset_min - 15, -20),
        "max_offset": min(oem.oem_offset_max + 15, 60),
    }


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
    # No year — return the latest chassis code
    return entries[-1][1]


def _lookup_known_specs(
    make: str,
    model: str,
    chassis_code: str | None,
    year: int | None,
) -> dict[str, Any] | None:
    """Lookup specs from known vehicle database.

    This is a fallback knowledge base for common vehicles.
    """
    make_lower = make.lower()
    model_lower = model.lower()
    chassis_upper = chassis_code.upper() if chassis_code else None

    # BMW specs by chassis code (5x120 unless noted)
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

    # BMW model+chassis overrides for performance variants with different specs
    # These take priority over generic chassis specs (e.g., E30 M3 is 5x120, not 4x100)
    bmw_model_chassis_specs: dict[tuple[str, str], dict[str, Any]] = {
        # E30 M3 (1986-1991) - uses 5x120, NOT 4x100 like regular E30
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
        # E39 M5 (1998-2003) - uses 74.1mm hub bore (NOT 72.6mm like most BMW 5x120)
        # Standard 73.1mm Kansei wheels are INCOMPATIBLE - hub-specific SKUs required
        # OEM: 18x8 +20 front, 18x9.5 +22 rear (Style 65 "M Parallels")
        # Safe aftermarket: +32 to +45 offset range, 18-19" max
        ("m5", "E39"): {
            "bolt_pattern": "5x120",
            "center_bore": 74.1,
            "stud_size": "M12x1.5",
            "year_start": 1998,
            "year_end": 2003,
            "oem_diameter": 18,
            "min_diameter": 17,
            "max_diameter": 19,  # 20" is show-only, not recommended
            "oem_width": 8.0,
            "min_width": 8.0,
            "max_width": 10.5,  # 10.5" rear max
            "oem_offset": 20,  # OEM was +20/+22 staggered
            "min_offset": 32,  # Safe minimum for no-mod fitment
            "max_offset": 45,  # Conservative max
        },
    }

    bmw_specs = {
        # 4x100 era
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
        # 5x120 era — classic
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
            "center_bore": 74.1,  # E39 uniquely uses 74.1mm, not 72.6mm
            "stud_size": "M12x1.5",
            "year_start": 1996,
            "year_end": 2003,
            "oem_diameter": 16,
            "min_diameter": 16,
            "max_diameter": 19,
            "oem_width": 7.0,
            "min_width": 7.0,
            "max_width": 9.5,
            "oem_offset": 20,
            "min_offset": 32,  # Safe minimum for E39
            "max_offset": 45,
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
        # 5x112 era (G-series, 2019+)
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

    # BMW model → chassis code mapping (for queries without explicit chassis code)
    _bmw_model_to_chassis: dict[str, list[tuple[tuple[int, int], str]]] = {
        # model_lower: [(year_range, chassis_code), ...]
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
        "m6": [
            ((1983, 1989), "E24"),
        ],
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
        "528i": [
            ((1996, 2003), "E39"),
        ],
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
        "4 series": [
            ((2014, 2020), "F32"),
        ],
        "5 series": [
            ((1981, 1988), "E28"),
            ((1988, 1995), "E34"),
            ((1996, 2003), "E39"),
            ((2004, 2010), "E60"),
        ],
        "6 series": [
            ((1976, 1989), "E24"),
        ],
        "7 series": [
            ((1994, 2001), "E38"),
        ],
        "740i": [((1994, 2001), "E38")],
        "750i": [((1994, 2001), "E38")],
    }

    # Check BMW model+chassis overrides FIRST (e.g., E30 M3 has different specs than E30)
    if make_lower == "bmw":
        # Try explicit chassis + model combination
        if chassis_upper:
            model_chassis_key = (model_lower, chassis_upper)
            if model_chassis_key in bmw_model_chassis_specs:
                return bmw_model_chassis_specs[model_chassis_key]

        # Try resolving chassis from model+year, then check overrides
        resolved_chassis = _resolve_bmw_chassis(model_lower, year, _bmw_model_to_chassis)
        if resolved_chassis:
            model_chassis_key = (model_lower, resolved_chassis)
            if model_chassis_key in bmw_model_chassis_specs:
                return bmw_model_chassis_specs[model_chassis_key]

        # Fall back to generic chassis specs
        if chassis_upper and chassis_upper in bmw_specs:
            return bmw_specs[chassis_upper]
        if resolved_chassis and resolved_chassis in bmw_specs:
            return bmw_specs[resolved_chassis]

    # Honda specs — year-aware
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
    honda_specs = {
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
        # Try specific chassis/model match first
        for (m, c), specs in honda_specs.items():
            if model_lower in m or m in model_lower:
                # Match if: no chassis required, chassis matches, or model name is specific enough
                if c is None or (chassis_upper and c.upper() == chassis_upper) or m == model_lower:
                    return specs

        # Civic year-based lookup (4x100 before 2006, 5x114.3 after)
        if "civic" in model_lower and "type r" not in model_lower:
            if year and year <= 2005:
                return _honda_4x100
            return _honda_5x114

        # Prelude year-based lookup
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
            # No year — can't determine
            return None

        # Acura / other Honda models default to 5x114.3
        if make_lower == "acura":
            return _honda_5x114

    # Subaru specs
    subaru_specs = {
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
        # 2004-2014 WRX STI — always 5x114.3 (different from base WRX)
        ("wrx sti", None): {
            "bolt_pattern": "5x114.3",
            "center_bore": 56.1,
            "stud_size": "M12x1.25",
            "oem_diameter": 17,
            "min_diameter": 17,
            "max_diameter": 19,
            "oem_width": 8.0,
            "min_width": 7.5,
            "max_width": 10.0,
            "oem_offset": 53,
            "min_offset": 30,
            "max_offset": 55,
        },
        ("wrx", None): {  # Pre-2015 WRX (non-STI)
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
        # Check STI specifically first (more specific model)
        if "sti" in model_lower:
            for (m, c), specs in subaru_specs.items():
                if "sti" in m:
                    if c is None or (chassis_upper and c.upper() == chassis_upper):
                        return specs
        # Then check generic WRX
        for (m, c), specs in subaru_specs.items():
            if model_lower in m or m in model_lower:
                if c is None or (chassis_upper and c.upper() == chassis_upper):
                    return specs

    # Toyota/Scion specs
    toyota_specs = {
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
        # Supra year-based: A80 (1993-2002) vs A90 (2019+)
        if "supra" in model_lower:
            if year and year <= 2002:
                return toyota_specs[("supra", "a80")]
            if year and year >= 2019:
                return toyota_specs[("supra", "a90")]

    # Nissan specs
    nissan_specs = {
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
    miata_specs = {
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
        # Miata/MX-5 year-based: NA (1990-1997), NB (1999-2005), NC (2006-2015), ND (2016+)
        if "miata" in model_lower or "mx-5" in model_lower or "mx5" in model_lower:
            if year and year <= 1997:
                return miata_specs[("miata", "na")]
            if year and year <= 2005:
                return miata_specs[("miata", "nb")]
            if year and year <= 2015:
                return miata_specs[("mx-5", "nc")]
            return miata_specs[("mx-5", "nd")]

    # Mitsubishi specs
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

    # Volkswagen specs
    _vw_5x112 = {
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
    if make_lower in ("volkswagen", "vw"):
        return _vw_5x112

    # Audi specs
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

    # Mercedes-Benz specs
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

    # Porsche specs
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

    # American trucks / muscle cars
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
            # Pre-2015 (SN95/S197) used 1/2"x20 studs; S550+ (2015+) uses M14x1.5
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

    # Jeep specs
    if make_lower == "jeep":
        if "wrangler" in model_lower:
            # JK (2007-2018) and JL (2018+) use 5x127 (5x5")
            return {
                "bolt_pattern": "5x127",
                "center_bore": 71.5,
                "stud_size": "M14x1.5",
                "oem_diameter": 17,
                "min_diameter": 17,
                "max_diameter": 20,
                "oem_width": 7.5,
                "min_width": 7.0,
                "max_width": 10.0,
                "oem_offset": -12,
                "min_offset": -24,
                "max_offset": 15,
            }
        if "gladiator" in model_lower:
            return {
                "bolt_pattern": "5x127",
                "center_bore": 71.5,
                "stud_size": "M14x1.5",
                "oem_diameter": 17,
                "min_diameter": 17,
                "max_diameter": 20,
                "oem_width": 7.5,
                "min_width": 7.0,
                "max_width": 10.0,
                "oem_offset": -12,
                "min_offset": -24,
                "max_offset": 15,
            }
        if "grand cherokee" in model_lower:
            return {
                "bolt_pattern": "5x127",
                "center_bore": 71.5,
                "stud_size": "M14x1.5",
                "oem_diameter": 18,
                "min_diameter": 17,
                "max_diameter": 22,
                "oem_width": 8.0,
                "min_width": 7.5,
                "max_width": 10.0,
                "oem_offset": 34,
                "min_offset": 15,
                "max_offset": 45,
            }

    # GMC specs
    if make_lower == "gmc":
        if "sierra" in model_lower:
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
        if "canyon" in model_lower:
            return {
                "bolt_pattern": "6x120",
                "center_bore": 67.1,
                "stud_size": "M14x1.5",
                "oem_diameter": 17,
                "min_diameter": 16,
                "max_diameter": 20,
                "oem_width": 7.0,
                "min_width": 7.0,
                "max_width": 9.0,
                "oem_offset": 28,
                "min_offset": 0,
                "max_offset": 40,
            }

    # More Toyota trucks
    if make_lower == "toyota":
        if "tundra" in model_lower:
            return {
                "bolt_pattern": "6x139.7",
                "center_bore": 106.1,
                "stud_size": "M14x1.5",
                "oem_diameter": 18,
                "min_diameter": 17,
                "max_diameter": 22,
                "oem_width": 8.0,
                "min_width": 7.5,
                "max_width": 10.0,
                "oem_offset": 50,
                "min_offset": -12,
                "max_offset": 60,
            }
        if "4runner" in model_lower:
            return {
                "bolt_pattern": "6x139.7",
                "center_bore": 106.1,
                "stud_size": "M12x1.5",
                "oem_diameter": 17,
                "min_diameter": 16,
                "max_diameter": 20,
                "oem_width": 7.0,
                "min_width": 7.0,
                "max_width": 9.0,
                "oem_offset": 15,
                "min_offset": -10,
                "max_offset": 35,
            }

    # Nissan trucks
    if make_lower == "nissan":
        if "frontier" in model_lower:
            return {
                "bolt_pattern": "6x114.3",
                "center_bore": 66.1,
                "stud_size": "M12x1.25",
                "oem_diameter": 16,
                "min_diameter": 16,
                "max_diameter": 18,
                "oem_width": 7.0,
                "min_width": 7.0,
                "max_width": 9.0,
                "oem_offset": 30,
                "min_offset": 0,
                "max_offset": 40,
            }
        if "titan" in model_lower:
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
                "oem_offset": 20,
                "min_offset": -12,
                "max_offset": 44,
            }

    # More Ford trucks
    if make_lower == "ford":
        if "ranger" in model_lower:
            return {
                "bolt_pattern": "6x139.7",
                "center_bore": 93.1,
                "stud_size": "M12x1.5",
                "oem_diameter": 17,
                "min_diameter": 16,
                "max_diameter": 20,
                "oem_width": 7.5,
                "min_width": 7.0,
                "max_width": 9.0,
                "oem_offset": 40,
                "min_offset": 0,
                "max_offset": 50,
            }
        if "bronco" in model_lower:
            return {
                "bolt_pattern": "6x139.7",
                "center_bore": 93.1,
                "stud_size": "M14x1.5",
                "oem_diameter": 17,
                "min_diameter": 17,
                "max_diameter": 20,
                "oem_width": 8.0,
                "min_width": 7.5,
                "max_width": 10.0,
                "oem_offset": 25,
                "min_offset": -10,
                "max_offset": 40,
            }

    # More Chevy trucks
    if make_lower in ("chevrolet", "chevy"):
        if "colorado" in model_lower:
            return {
                "bolt_pattern": "6x120",
                "center_bore": 67.1,
                "stud_size": "M14x1.5",
                "oem_diameter": 17,
                "min_diameter": 16,
                "max_diameter": 20,
                "oem_width": 7.0,
                "min_width": 7.0,
                "max_width": 9.0,
                "oem_offset": 28,
                "min_offset": 0,
                "max_offset": 40,
            }

    # Tesla specs
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

    # Datsun / Nissan classics
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


def validate_bolt_pattern(pattern: str) -> bool:
    """Validate that a bolt pattern is in the correct format."""
    # Pattern should be like "4x100", "5x114.3", "5x120"
    match = re.match(r"^[4-8]x\d{2,3}(\.\d)?$", pattern)
    return match is not None


def validate_center_bore(bore: float) -> bool:
    """Validate that center bore is within reasonable range."""
    # Cars 50-80mm, trucks/SUVs up to 110mm
    return 45.0 <= bore <= 115.0


def validate_offset(offset: int) -> bool:
    """Validate that offset is within reasonable range."""
    # Street cars typically -20 to +60
    return -30 <= offset <= 70


def validate_diameter(diameter: int) -> bool:
    """Validate that wheel diameter is within reasonable range."""
    # Street cars typically 13" to 22"
    return 13 <= diameter <= 24


def validate_width(width: float) -> bool:
    """Validate that wheel width is within reasonable range."""
    # Street cars typically 5" to 12"
    return 4.5 <= width <= 13.0
