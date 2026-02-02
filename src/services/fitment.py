"""Fitment analysis and classification utilities.

This module provides geometry-based fitment calculations. The core math:

    poke_mm = (wheel_width - oem_width) * 25.4 / 2 + (oem_offset - wheel_offset)

Where:
- Positive poke = wheel sticks out past fender
- Negative poke = wheel is tucked under fender
- Zero = flush with fender line

Thresholds (consistent across codebase):
- Flush: poke < 10mm
- Mild poke: 10mm <= poke < 20mm
- Aggressive: poke >= 20mm
"""

from typing import Any

from ..utils.converters import safe_float


# =============================================================================
# CONSTANTS (single source of truth for thresholds)
# =============================================================================

# Poke thresholds in mm
FLUSH_THRESHOLD = 10      # < 10mm = flush
MILD_POKE_THRESHOLD = 20  # 10-20mm = mild poke, >= 20mm = aggressive

# Default OEM specs when not provided (conservative assumptions)
DEFAULT_OEM_WIDTH = 7.5   # inches
DEFAULT_OEM_OFFSET = 35   # mm


# =============================================================================
# CORE GEOMETRY CALCULATIONS
# =============================================================================

def calculate_poke(
    wheel_width: float,
    wheel_offset: float,
    oem_width: float = DEFAULT_OEM_WIDTH,
    oem_offset: float = DEFAULT_OEM_OFFSET,
) -> float:
    """Calculate poke in mm using geometry.

    The formula accounts for both width change AND offset change:
    - Wider wheel pushes mounting face inward (more poke)
    - Lower offset moves wheel outward (more poke)

    Args:
        wheel_width: Aftermarket wheel width in inches
        wheel_offset: Aftermarket wheel offset in mm
        oem_width: Factory wheel width in inches
        oem_offset: Factory wheel offset in mm

    Returns:
        Poke in mm (positive = sticks out, negative = tucked)

    Examples:
        >>> calculate_poke(9.0, 35, 7.5, 35)  # Wider wheel, same offset
        19.05  # ~19mm poke from width alone
        >>> calculate_poke(7.5, 22, 7.5, 35)  # Same width, lower offset
        13.0   # 13mm poke from offset alone
    """
    width_diff_inches = wheel_width - oem_width
    width_diff_mm = width_diff_inches * 25.4
    width_contribution = width_diff_mm / 2  # Half goes to each side

    offset_contribution = oem_offset - wheel_offset  # Lower offset = more poke

    return width_contribution + offset_contribution


def classify_poke(poke_mm: float) -> str:
    """Classify poke amount into style category.

    Args:
        poke_mm: Calculated poke in mm

    Returns:
        'flush', 'mild_poke', or 'aggressive'
    """
    if poke_mm < FLUSH_THRESHOLD:
        return "flush"
    elif poke_mm < MILD_POKE_THRESHOLD:
        return "mild_poke"
    else:
        return "aggressive"


# =============================================================================
# ROW-BASED ANALYSIS (for CSV/database records)
# =============================================================================

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
    """Determine fitment style using geometry-based poke calculation.

    Uses the average poke of front and rear wheels.
    """
    front_width = safe_float(row.get("front_width"))
    rear_width = safe_float(row.get("rear_width"))
    front_offset = safe_float(row.get("front_offset"))
    rear_offset = safe_float(row.get("rear_offset"))

    # Calculate poke for front and rear
    front_poke = calculate_poke(front_width, front_offset)
    rear_poke = calculate_poke(rear_width, rear_offset)

    # Use the more aggressive (higher poke) value
    max_poke = max(front_poke, rear_poke)

    style = classify_poke(max_poke)

    # Map internal classification to display style
    if style == "flush":
        return "flush"
    elif style == "mild_poke":
        return "flush"  # Mild poke is still presentable as flush-ish
    else:
        return "aggressive"


def has_poke(row: dict[str, Any]) -> bool:
    """Determine if wheels poke past fender using geometry.

    Uses proper poke calculation instead of simple offset threshold.
    """
    front_width = safe_float(row.get("front_width"))
    rear_width = safe_float(row.get("rear_width"))
    front_offset = safe_float(row.get("front_offset"))
    rear_offset = safe_float(row.get("rear_offset"))

    front_poke = calculate_poke(front_width, front_offset)
    rear_poke = calculate_poke(rear_width, rear_offset)

    # Any wheel with >= 10mm poke is considered "poking"
    return front_poke >= FLUSH_THRESHOLD or rear_poke >= FLUSH_THRESHOLD


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
