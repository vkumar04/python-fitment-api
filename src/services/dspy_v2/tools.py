"""Tools for the DSPy v2 pipeline.

Provides vehicle spec web scraping from wheel-size.com and validation utilities.
All functions are **synchronous** because the pipeline runs inside
``asyncio.to_thread()`` from the RAG service.
"""

import logging
import re
from typing import Any

from ..wheel_size_lookup import OEMSpecs, get_wheel_size_lookup

logger = logging.getLogger(__name__)


def scrape_vehicle_specs(
    year: int,
    make: str,
    model: str,
) -> dict[str, Any] | None:
    """Scrape vehicle wheel specs from wheel-size.com.

    Requires a year to construct the URL. Returns pipeline-format dict on
    success, or None on failure.
    """
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
