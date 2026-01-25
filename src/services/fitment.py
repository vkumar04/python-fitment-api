"""Fitment analysis and classification utilities."""

from typing import Any

from ..utils.converters import safe_float


def determine_setup(row: dict[str, Any]) -> str:
    """Determine if fitment is square or staggered."""
    front_width = safe_float(row.get("front_width"))
    rear_width = safe_float(row.get("rear_width"))
    front_diameter = safe_float(row.get("front_diameter"))
    rear_diameter = safe_float(row.get("rear_diameter"))
    front_offset = safe_float(row.get("front_offset"))
    rear_offset = safe_float(row.get("rear_offset"))

    if (
        front_width == rear_width
        and front_diameter == rear_diameter
        and front_offset == rear_offset
    ):
        return "square"
    return "staggered"


def determine_style(row: dict[str, Any]) -> str:
    """Determine fitment style based on offset and width."""
    front_offset = safe_float(row.get("front_offset"))
    rear_offset = safe_float(row.get("rear_offset"))
    front_width = safe_float(row.get("front_width"))
    rear_width = safe_float(row.get("rear_width"))

    avg_offset = (front_offset + rear_offset) / 2
    avg_width = (front_width + rear_width) / 2

    if avg_offset < 15 and avg_width >= 9:
        return "aggressive"
    elif avg_offset < 25:
        return "flush"
    elif avg_offset >= 40:
        return "tucked"
    else:
        return "flush"


def has_poke(row: dict[str, Any]) -> bool:
    """Determine if wheels poke past fender."""
    front_offset = safe_float(row.get("front_offset"))
    rear_offset = safe_float(row.get("rear_offset"))
    return front_offset < 20 or rear_offset < 20


def needs_modifications(row: dict[str, Any]) -> bool:
    """Check if fitment requires modifications."""
    rubbing = str(row.get("rubbing", "")).lower()
    trimming = str(row.get("trimming", "")).lower()
    front_spacers = str(row.get("front_wheel_spacers", "")).lower()
    rear_spacers = str(row.get("rear_wheel_spacers", "")).lower()

    has_rubbing = "rub" in rubbing and "no rub" not in rubbing
    needs_trimming = "no" not in trimming and trimming != ""
    has_spacers = front_spacers not in ["none", ""] or rear_spacers not in ["none", ""]

    return has_rubbing or needs_trimming or has_spacers


def to_document_text(row: dict[str, Any]) -> str:
    """Convert a fitment row to searchable document text."""
    setup = determine_setup(row)
    style = determine_style(row)
    poke = "poke" if has_poke(row) else "no poke"
    mods = (
        "requires modifications"
        if needs_modifications(row)
        else "no modifications needed"
    )

    parts = [
        f"{row.get('year', '')} {row.get('make', '')} {row.get('model', '')}",
        f"Setup: {setup} {style} fitment {poke}",
        f"Wheels: {row.get('wheel_brand', '')} {row.get('wheel_model', '')}",
        f"Front wheel: {row.get('front_diameter', '')}x{row.get('front_width', '')} ET{row.get('front_offset', '')} backspacing {row.get('front_backspacing', '')}",
        f"Rear wheel: {row.get('rear_diameter', '')}x{row.get('rear_width', '')} ET{row.get('rear_offset', '')} backspacing {row.get('rear_backspacing', '')}",
        f"Tires: {row.get('tire_brand', '')} {row.get('tire_model', '')}",
        f"Front tire: {row.get('front_tire_width', '')}/{row.get('front_tire_aspect', '')}R{row.get('front_tire_diameter', '')}",
        f"Rear tire: {row.get('rear_tire_width', '')}/{row.get('rear_tire_aspect', '')}R{row.get('rear_tire_diameter', '')}",
        f"Rubbing: {row.get('rubbing', '')}",
        f"Trimming: {row.get('trimming', '')}",
        f"Spacers: Front {row.get('front_wheel_spacers', '')}, Rear {row.get('rear_wheel_spacers', '')}",
        f"Suspension: {row.get('suspension_type', '')}",
        f"Modifications: {mods}",
    ]
    return " | ".join(parts)
