"""Validation logic for vehicle specs and wheel recommendations."""

import re
from typing import Any


def parse_range(range_str: str) -> tuple[float, float]:
    """Parse a range string like '7-9' or '+25 to +45' into min/max values."""
    # Extract all numbers (positive or negative)
    numbers = re.findall(r"-?\d+\.?\d*", range_str)
    if len(numbers) >= 2:
        vals = [float(n) for n in numbers]
        return min(vals), max(vals)
    elif len(numbers) == 1:
        val = float(numbers[0])
        return val - 5, val + 5
    return 0, 100


def validate_wheel_for_vehicle(
    wheel: dict[str, Any],
    vehicle_specs: dict[str, Any],
) -> tuple[bool, str | None]:
    """
    Validate if a wheel is appropriate for a vehicle.

    Returns:
        (is_valid, reason) - True if wheel fits, False with reason if not
    """
    diameter = wheel.get("diameter", 0)
    width = wheel.get("width", 0)
    offset = wheel.get("wheel_offset", 0)

    max_diameter = vehicle_specs.get("max_diameter", 20)
    min_diameter = vehicle_specs.get("min_diameter", 15)

    width_range = vehicle_specs.get("width_range", "7-10")
    min_width, max_width = parse_range(width_range)

    offset_range = vehicle_specs.get("offset_range", "+20 to +45")
    min_offset, max_offset = parse_range(offset_range)

    # Check diameter
    if diameter > max_diameter:
        return (
            False,
            f'Diameter {diameter}" exceeds max {max_diameter}" for this vehicle',
        )
    if diameter < min_diameter:
        return (
            False,
            f'Diameter {diameter}" below min {min_diameter}" (brake clearance)',
        )

    # Check width (allow +1" over max for aggressive fitment)
    if width > max_width + 1:
        return False, f'Width {width}" too wide (max ~{max_width}" for this vehicle)'
    if width < min_width - 0.5:
        return False, f'Width {width}" too narrow (min ~{min_width}" recommended)'

    # Check offset (allow some tolerance)
    if offset < min_offset - 10:
        return False, f"Offset +{offset} too low (would poke significantly)"
    if offset > max_offset + 10:
        return False, f"Offset +{offset} too high (would tuck excessively)"

    return True, None


def filter_wheels_by_vehicle_specs(
    wheels: list[dict[str, Any]],
    vehicle_specs: dict[str, Any],
) -> list[dict[str, Any]]:
    """Filter a list of wheels to only those valid for the vehicle."""
    valid_wheels = []
    for wheel in wheels:
        is_valid, _ = validate_wheel_for_vehicle(wheel, vehicle_specs)
        if is_valid:
            valid_wheels.append(wheel)
    return valid_wheels


def validate_recommendations(
    recommendations: list[dict[str, Any]],
    vehicle_specs: dict[str, Any],
    fitment_data: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """
    Validate wheel recommendations against vehicle specs and fitment data.

    Priority:
    1. If fitment data shows this exact spec works -> valid
    2. If spec falls within vehicle's safe ranges -> valid
    3. Otherwise -> invalid
    """
    validated = []

    # Build set of proven specs from fitment data
    proven_specs: set[tuple[float, float, int]] = set()
    if fitment_data:
        for fit in fitment_data:
            meta = fit.get("metadata", {})
            if meta.get("front_diameter") and meta.get("front_width"):
                proven_specs.add(
                    (
                        float(meta["front_diameter"]),
                        float(meta["front_width"]),
                        int(meta.get("front_offset", 0)),
                    )
                )

    for wheel in recommendations:
        diameter = wheel.get("diameter", 0)
        width = wheel.get("width", 0)
        offset = wheel.get("wheel_offset", 0)

        # Check if this spec is proven by community data
        is_proven = any(
            abs(diameter - d) < 0.5 and abs(width - w) < 0.5 and abs(offset - o) <= 10
            for d, w, o in proven_specs
        )

        if is_proven:
            wheel["validation"] = "proven"
            validated.append(wheel)
            continue

        # Otherwise validate against vehicle specs
        is_valid, reason = validate_wheel_for_vehicle(wheel, vehicle_specs)
        if is_valid:
            wheel["validation"] = "compatible"
            validated.append(wheel)
        else:
            wheel["validation"] = "incompatible"
            wheel["validation_reason"] = reason
            # Don't include incompatible wheels

    return validated
