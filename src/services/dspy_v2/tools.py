"""Tools for the DSPy ReAct agent.

These tools allow the agent to search the web for vehicle specs
and interact with external data sources.
"""

import re
from typing import Any



async def search_vehicle_specs_web(
    year: int | None,
    make: str,
    model: str,
    chassis_code: str | None = None,
) -> dict[str, Any]:
    """Search the web for vehicle wheel specifications.

    This is a simulated web search that returns structured data.
    In production, this would call a real search API.

    Args:
        year: Vehicle year (optional)
        make: Vehicle manufacturer
        model: Vehicle model
        chassis_code: Chassis code if known (e.g., E30, FK8)

    Returns:
        Dictionary with bolt_pattern, center_bore, and other specs,
        or error information if not found.
    """
    # Build search query
    query_parts = []
    if year:
        query_parts.append(str(year))
    query_parts.append(make)
    query_parts.append(model)
    if chassis_code:
        query_parts.append(chassis_code)
    query_parts.append("bolt pattern wheel specs")

    query = " ".join(query_parts)

    # In production, this would call a real search API
    # For now, we'll use a knowledge base fallback
    specs = _lookup_known_specs(make, model, chassis_code, year)

    if specs:
        return {
            "found": True,
            "source": "knowledge_base",
            "source_url": f"https://wheel-size.com/{make.lower()}/{model.lower().replace(' ', '-')}/",
            "confidence": 0.85,
            **specs,
        }

    return {
        "found": False,
        "error": f"Could not find wheel specs for {query}",
        "suggestion": "Try searching with the chassis code or a specific year",
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
