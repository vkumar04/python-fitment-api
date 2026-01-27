"""Tools for the DSPy v2 pipeline.

Provides vehicle spec lookup: knowledge base first, then wheel-size.com scraping.
"""

import asyncio
import logging
import re
from typing import Any

from ..wheel_size_lookup import OEMSpecs, get_wheel_size_lookup

logger = logging.getLogger(__name__)


async def search_vehicle_specs_web(
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
        scraped = await _scrape_wheel_size(year, make, model)
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


async def _scrape_wheel_size(
    year: int, make: str, model: str
) -> dict[str, Any] | None:
    """Scrape wheel-size.com and validate the results."""
    try:
        lookup = get_wheel_size_lookup()
        oem: OEMSpecs | None = await asyncio.to_thread(lookup.lookup, year, make, model)
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

    # BMW specs by chassis code
    bmw_specs = {
        "E30": {
            "bolt_pattern": "4x100",
            "center_bore": 57.1,
            "stud_size": "M12x1.5",
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
        "E36": {
            "bolt_pattern": "5x120",
            "center_bore": 72.6,
            "stud_size": "M12x1.5",
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
        "E46": {
            "bolt_pattern": "5x120",
            "center_bore": 72.6,
            "stud_size": "M12x1.5",
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
        "E39": {
            "bolt_pattern": "5x120",
            "center_bore": 72.6,
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
        "E90": {
            "bolt_pattern": "5x120",
            "center_bore": 72.6,
            "stud_size": "M12x1.5",
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
            "bolt_pattern": "5x120",
            "center_bore": 72.6,
            "stud_size": "M12x1.5",
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
        "G20": {
            "bolt_pattern": "5x112",
            "center_bore": 66.5,
            "stud_size": "M14x1.25",
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
    }

    # Check BMW by chassis code first
    if make_lower == "bmw" and chassis_upper and chassis_upper in bmw_specs:
        return bmw_specs[chassis_upper]

    # Honda specs
    honda_specs = {
        ("civic", "eg"): {
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
        },
        ("civic", "ek"): {
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
        },
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
        ("civic", None): {  # Generic modern Civic
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
        },
    }

    if make_lower == "honda":
        # Try specific chassis match first
        for (m, c), specs in honda_specs.items():
            if model_lower in m or m in model_lower:
                if c is None or (chassis_upper and c.upper() == chassis_upper):
                    return specs

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
        ("wrx", None): {  # Pre-2015 WRX
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
    }

    if make_lower in ("toyota", "scion"):
        for (m, c), specs in toyota_specs.items():
            if model_lower in m or m in model_lower:
                if c is None or (chassis_upper and c.upper() == chassis_upper):
                    return specs

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

    return None


def validate_bolt_pattern(pattern: str) -> bool:
    """Validate that a bolt pattern is in the correct format."""
    # Pattern should be like "4x100", "5x114.3", "5x120"
    match = re.match(r"^[4-8]x\d{2,3}(\.\d)?$", pattern)
    return match is not None


def validate_center_bore(bore: float) -> bool:
    """Validate that center bore is within reasonable range."""
    # Most cars are between 50mm and 80mm
    return 45.0 <= bore <= 85.0


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
