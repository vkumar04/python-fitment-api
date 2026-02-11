"""Tire and wheel fitment calculations using industry-standard formulas.

This module is the single source of truth for all tire/wheel math.

## Core Formulas (from industry standards)

### Sidewall Height
    sidewall_mm = tire_width_mm × (aspect_ratio / 100)

### Total Tire Diameter
    tire_diameter_mm = (wheel_diameter_inches × 25.4) + (2 × sidewall_mm)

### Poke Calculation (outer position change)
    poke_mm = ((new_width - oem_width) × 25.4 / 2) - (new_offset - oem_offset)

    Simplified (when oem_offset > new_offset, poke increases):
    poke_mm = (width_diff_mm / 2) + (oem_offset - new_offset)

### Inner Clearance Change
    inner_change_mm = ((new_width - oem_width) × 25.4 / 2) + (new_offset - oem_offset)

### Tire Width to Wheel Width (industry standard)
    - Tire section width changes ~5mm for every 0.5" change in rim width
    - Ideal tire width = (wheel_width_inches × 25.4) + 10mm to +20mm
    - Min tire width = wheel_width_inches × 25.4
    - Max tire width = (wheel_width_inches × 25.4) + 30mm

Sources:
- ISO 4000-1, ISO 4000-2 (Passenger car tyres and rims)
- Tire Rack engineering guidelines
- KIPARDO wheel offset formulas
- Roadkill Customs tire width charts
"""

from typing import Any

# =============================================================================
# CONSTANTS
# =============================================================================

# Conversion factor
MM_PER_INCH = 25.4

# Industry-standard tire width ranges by wheel width (inches)
# Source: Roadkill Customs, cross-referenced with Tire Rack
TIRE_WIDTH_BY_WHEEL: dict[float, dict[str, int]] = {
    5.0:  {"min": 155, "ideal_low": 165, "ideal_high": 175, "max": 185},
    5.5:  {"min": 165, "ideal_low": 175, "ideal_high": 185, "max": 195},
    6.0:  {"min": 175, "ideal_low": 185, "ideal_high": 195, "max": 205},
    6.5:  {"min": 185, "ideal_low": 195, "ideal_high": 205, "max": 215},
    7.0:  {"min": 195, "ideal_low": 205, "ideal_high": 215, "max": 225},
    7.5:  {"min": 205, "ideal_low": 215, "ideal_high": 225, "max": 235},
    8.0:  {"min": 215, "ideal_low": 225, "ideal_high": 235, "max": 245},
    8.5:  {"min": 225, "ideal_low": 235, "ideal_high": 245, "max": 255},
    9.0:  {"min": 235, "ideal_low": 245, "ideal_high": 255, "max": 265},
    9.5:  {"min": 245, "ideal_low": 255, "ideal_high": 265, "max": 275},
    10.0: {"min": 255, "ideal_low": 265, "ideal_high": 275, "max": 285},
    10.5: {"min": 265, "ideal_low": 275, "ideal_high": 285, "max": 295},
    11.0: {"min": 275, "ideal_low": 285, "ideal_high": 295, "max": 305},
    11.5: {"min": 285, "ideal_low": 295, "ideal_high": 305, "max": 315},
    12.0: {"min": 295, "ideal_low": 305, "ideal_high": 315, "max": 325},
}

# Aspect ratio recommendations by wheel diameter and suspension
# Lower profile = shorter sidewall = less rub risk when lowered
ASPECT_RATIO_BY_DIAMETER: dict[int, dict[str, int]] = {
    15: {"stock": 55, "lowered": 50},
    16: {"stock": 50, "lowered": 45},
    17: {"stock": 45, "lowered": 40},
    18: {"stock": 40, "lowered": 35},
    19: {"stock": 35, "lowered": 30},
    20: {"stock": 35, "lowered": 30},
    21: {"stock": 30, "lowered": 25},
    22: {"stock": 30, "lowered": 25},
}

# Poke thresholds for fitment classification (mm)
POKE_FLUSH_MAX = 10      # < 10mm = flush
POKE_MILD_MAX = 20       # 10-20mm = mild poke
# >= 20mm = aggressive

# Suspension clearance adjustments (mm to subtract from tire width)
SUSPENSION_TIRE_WIDTH_ADJUSTMENT: dict[str, int] = {
    "stock": 0,       # No adjustment needed
    "lowered": 10,    # Go 10mm narrower
    "coilovers": 20,  # Go 20mm narrower for compression clearance
    "air": 20,        # Go 20mm narrower for aired-out clearance
}


# =============================================================================
# CORE CALCULATION FUNCTIONS
# =============================================================================

def calculate_sidewall_height(tire_width_mm: int, aspect_ratio: int) -> float:
    """Calculate tire sidewall height in mm.

    Formula: sidewall_mm = tire_width_mm × (aspect_ratio / 100)

    Args:
        tire_width_mm: Tire section width in millimeters (e.g., 245)
        aspect_ratio: Tire aspect ratio as percentage (e.g., 40 for 40%)

    Returns:
        Sidewall height in millimeters

    Example:
        >>> calculate_sidewall_height(245, 40)
        98.0  # 245 × 0.40 = 98mm sidewall
    """
    return tire_width_mm * (aspect_ratio / 100)


def calculate_tire_diameter(
    wheel_diameter_inches: int,
    tire_width_mm: int,
    aspect_ratio: int,
) -> float:
    """Calculate total tire diameter in mm.

    Formula: tire_diameter_mm = (wheel_diameter × 25.4) + (2 × sidewall_height)

    Args:
        wheel_diameter_inches: Wheel diameter in inches (e.g., 18)
        tire_width_mm: Tire section width in mm (e.g., 245)
        aspect_ratio: Tire aspect ratio (e.g., 40)

    Returns:
        Total tire outside diameter in millimeters

    Example:
        >>> calculate_tire_diameter(18, 245, 40)
        653.2  # (18 × 25.4) + (2 × 98) = 457.2 + 196 = 653.2mm
    """
    wheel_diameter_mm = wheel_diameter_inches * MM_PER_INCH
    sidewall_mm = calculate_sidewall_height(tire_width_mm, aspect_ratio)
    return wheel_diameter_mm + (2 * sidewall_mm)


def calculate_poke(
    wheel_width_inches: float,
    wheel_offset_mm: float,
    oem_width_inches: float = 7.5,
    oem_offset_mm: float = 35,
) -> float:
    """Calculate wheel poke (outer position change) in mm.

    Formula: poke_mm = ((new_width - oem_width) × 25.4 / 2) + (oem_offset - new_offset)

    This formula accounts for two factors:
    1. Width change: Wider wheel pushes the outer lip outward
    2. Offset change: Lower offset moves entire wheel outward

    Args:
        wheel_width_inches: Aftermarket wheel width in inches
        wheel_offset_mm: Aftermarket wheel offset in mm
        oem_width_inches: Stock wheel width in inches
        oem_offset_mm: Stock wheel offset in mm

    Returns:
        Poke in mm (positive = sticks out past fender, negative = tucked)

    Examples:
        >>> calculate_poke(9.0, 35, 7.5, 35)  # Wider wheel, same offset
        19.05  # Width alone adds ~19mm poke

        >>> calculate_poke(7.5, 22, 7.5, 35)  # Same width, lower offset
        13.0   # Offset alone adds 13mm poke

        >>> calculate_poke(9.0, 22, 7.5, 35)  # Both wider AND lower offset
        32.05  # Combined effect
    """
    width_diff_inches = wheel_width_inches - oem_width_inches
    width_contribution_mm = (width_diff_inches * MM_PER_INCH) / 2
    offset_contribution_mm = oem_offset_mm - wheel_offset_mm

    return width_contribution_mm + offset_contribution_mm


def calculate_inner_clearance_change(
    wheel_width_inches: float,
    wheel_offset_mm: float,
    oem_width_inches: float = 7.5,
    oem_offset_mm: float = 35,
) -> float:
    """Calculate inner clearance change (suspension side) in mm.

    Formula: inner_change_mm = ((new_width - oem_width) × 25.4 / 2) + (new_offset - oem_offset)

    Positive value = wheel moved CLOSER to suspension (less clearance)
    Negative value = wheel moved AWAY from suspension (more clearance)

    Args:
        wheel_width_inches: Aftermarket wheel width in inches
        wheel_offset_mm: Aftermarket wheel offset in mm
        oem_width_inches: Stock wheel width in inches
        oem_offset_mm: Stock wheel offset in mm

    Returns:
        Inner clearance change in mm
    """
    width_diff_inches = wheel_width_inches - oem_width_inches
    width_contribution_mm = (width_diff_inches * MM_PER_INCH) / 2
    offset_contribution_mm = wheel_offset_mm - oem_offset_mm

    return width_contribution_mm + offset_contribution_mm


def classify_poke(poke_mm: float) -> str:
    """Classify poke amount into fitment style.

    Args:
        poke_mm: Calculated poke in millimeters

    Returns:
        'flush', 'mild_poke', or 'aggressive'
    """
    if poke_mm < POKE_FLUSH_MAX:
        return "flush"
    elif poke_mm < POKE_MILD_MAX:
        return "mild_poke"
    else:
        return "aggressive"


# =============================================================================
# TIRE SIZE RECOMMENDATION FUNCTIONS
# =============================================================================

def get_tire_width_range(wheel_width_inches: float) -> dict[str, int]:
    """Get recommended tire width range for a wheel width.

    Uses industry-standard tire width charts.

    Args:
        wheel_width_inches: Wheel width in inches (e.g., 9.0)

    Returns:
        Dict with 'min', 'ideal_low', 'ideal_high', 'max' tire widths in mm
    """
    # Find closest wheel width in our chart
    closest = min(TIRE_WIDTH_BY_WHEEL.keys(), key=lambda x: abs(x - wheel_width_inches))
    return TIRE_WIDTH_BY_WHEEL[closest].copy()


def get_aspect_ratio(
    wheel_diameter: int,
    suspension: str = "stock",
) -> int:
    """Get recommended aspect ratio for wheel diameter and suspension.

    Args:
        wheel_diameter: Wheel diameter in inches (e.g., 18)
        suspension: Suspension type ('stock', 'lowered', 'coilovers', 'air')

    Returns:
        Recommended aspect ratio (e.g., 40 for 40-series)
    """
    # Normalize suspension
    susp_key = "lowered" if suspension in ("lowered", "coilovers", "air") else "stock"

    # Find closest diameter in our chart
    if wheel_diameter in ASPECT_RATIO_BY_DIAMETER:
        return ASPECT_RATIO_BY_DIAMETER[wheel_diameter][susp_key]

    # Interpolate for unusual sizes
    closest = min(ASPECT_RATIO_BY_DIAMETER.keys(), key=lambda x: abs(x - wheel_diameter))
    return ASPECT_RATIO_BY_DIAMETER[closest][susp_key]


def recommend_tire_size(
    wheel_width_inches: float,
    wheel_diameter: int,
    suspension: str = "stock",
) -> dict[str, Any]:
    """Generate complete tire size recommendation.

    Uses industry-standard formulas and charts to recommend optimal tire size
    based on wheel specs and suspension type.

    For aggressive lowered/bagged setups, we allow going 10-20mm BELOW the
    industry minimum. This creates a "stretched" tire look that:
    - Reduces sidewall bulge (less rub risk when aired out)
    - Looks more aggressive
    - Is common in stance/show communities

    Args:
        wheel_width_inches: Wheel width in inches
        wheel_diameter: Wheel diameter in inches
        suspension: Suspension type ('stock', 'lowered', 'coilovers', 'air')

    Returns:
        Dict with:
        - tire: Recommended tire size string (e.g., "245/40/18")
        - tire_alt: Alternative tire option
        - tire_width: Width in mm
        - aspect_ratio: Aspect ratio
        - sidewall_mm: Sidewall height in mm
        - tire_diameter_mm: Total tire diameter in mm
        - notes: Explanation of recommendation
        - width_range: Full range of acceptable widths
        - is_stretched: Whether tire is narrower than industry minimum
    """
    susp = suspension.lower() if suspension else "stock"

    # Get base tire width range for this wheel
    width_range = get_tire_width_range(wheel_width_inches)

    # Determine suspension adjustment
    # For coilovers/air, we go BELOW industry minimum for clearance
    if susp in ("coilovers", "coils", "slammed"):
        adjustment = 30  # Go 30mm narrower than ideal
    elif susp in ("air", "bagged", "bags"):
        adjustment = 30  # Same for bagged - need max clearance
    elif susp in ("lowered", "springs", "dropped"):
        adjustment = 20  # Go 20mm narrower
    else:
        adjustment = 0

    # Calculate recommended width (ideal_low minus suspension adjustment)
    base_width = width_range["ideal_low"]
    recommended_width = base_width - adjustment

    # For stock, don't go below minimum
    # For lowered/coilovers/air, allow going below minimum (stretched look)
    is_stretched = False
    if susp in ("stock", "oem", "factory"):
        recommended_width = max(recommended_width, width_range["min"])
    else:
        # Allow stretched tires, but not more than 20mm below minimum
        min_stretched = width_range["min"] - 20
        if recommended_width < min_stretched:
            recommended_width = min_stretched
        if recommended_width < width_range["min"]:
            is_stretched = True

    # Round to nearest standard tire width (5mm increments)
    recommended_width = round(recommended_width / 5) * 5

    # Get aspect ratio
    aspect = get_aspect_ratio(wheel_diameter, susp)

    # Calculate alternative (one step wider if possible)
    alt_width = recommended_width + 10
    if alt_width > width_range["max"]:
        alt_width = recommended_width  # No wider alternative

    # Calculate derived values
    sidewall = calculate_sidewall_height(recommended_width, aspect)
    tire_diameter = calculate_tire_diameter(wheel_diameter, recommended_width, aspect)

    # Generate notes
    if is_stretched:
        notes = f"Stretched tire ({recommended_width}mm) for max clearance - allows airing out without rub"
    elif susp in ("coilovers", "coils", "slammed", "air", "bagged", "bags"):
        notes = f"Narrow tire ({recommended_width}mm) for compression/aired-out clearance"
    elif susp in ("lowered", "springs", "dropped"):
        notes = f"Conservative width ({recommended_width}mm) for lowered fitment"
    else:
        notes = f"Standard width ({recommended_width}mm) for stock suspension"

    return {
        "tire": f"{recommended_width}/{aspect}/{wheel_diameter}",
        "tire_alt": f"{alt_width}/{aspect}/{wheel_diameter}" if alt_width != recommended_width else None,
        "tire_width": recommended_width,
        "aspect_ratio": aspect,
        "sidewall_mm": round(sidewall, 1),
        "tire_diameter_mm": round(tire_diameter, 1),
        "notes": notes,
        "width_range": width_range,
        "suspension": susp,
        "is_stretched": is_stretched,
    }


# =============================================================================
# FITMENT VALIDATION
# =============================================================================

def validate_tire_wheel_combo(
    tire_width_mm: int,
    wheel_width_inches: float,
) -> dict[str, Any]:
    """Validate if a tire width is appropriate for a wheel width.

    Args:
        tire_width_mm: Tire section width in mm
        wheel_width_inches: Wheel width in inches

    Returns:
        Dict with 'valid', 'fit_type', and 'message'
    """
    range_info = get_tire_width_range(wheel_width_inches)

    if tire_width_mm < range_info["min"]:
        return {
            "valid": False,
            "fit_type": "too_narrow",
            "message": f"Tire too narrow ({tire_width_mm}mm). Min for {wheel_width_inches}\" wheel: {range_info['min']}mm",
        }
    elif tire_width_mm > range_info["max"]:
        return {
            "valid": False,
            "fit_type": "too_wide",
            "message": f"Tire too wide ({tire_width_mm}mm). Max for {wheel_width_inches}\" wheel: {range_info['max']}mm",
        }
    elif range_info["ideal_low"] <= tire_width_mm <= range_info["ideal_high"]:
        return {
            "valid": True,
            "fit_type": "ideal",
            "message": f"Ideal fit: {tire_width_mm}mm on {wheel_width_inches}\" wheel",
        }
    else:
        return {
            "valid": True,
            "fit_type": "acceptable",
            "message": f"Acceptable fit: {tire_width_mm}mm on {wheel_width_inches}\" wheel (ideal: {range_info['ideal_low']}-{range_info['ideal_high']}mm)",
        }
