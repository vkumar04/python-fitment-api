"""Kansei wheel catalog lookup and recommendation formatting."""

import os
from typing import Any, cast

from supabase import Client, create_client

from .validation import filter_wheels_by_vehicle_specs, validate_recommendations

# Supabase client for Kansei queries (lazy loaded)
_kansei_supabase: Client | None = None


def _get_supabase() -> Client:
    """Get or create Supabase client for Kansei queries."""
    global _kansei_supabase
    if _kansei_supabase is None:
        _kansei_supabase = create_client(
            os.getenv("SUPABASE_URL", ""),
            os.getenv("SUPABASE_KEY", ""),
        )
    return _kansei_supabase


def find_matching_wheels(
    bolt_pattern: str,
    diameter: float | None = None,
    width: float | None = None,
    offset: int | None = None,
    offset_tolerance: int = 10,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Find Kansei wheels from Supabase that match the given specs."""
    supabase = _get_supabase()

    result = supabase.rpc(
        "find_kansei_wheels",
        {
            "p_bolt_pattern": bolt_pattern,
            "p_diameter": diameter,
            "p_width": width,
            "p_offset": offset,
            "p_offset_tolerance": offset_tolerance,
            "p_limit": limit,
        },
    ).execute()

    if result.data and isinstance(result.data, list):
        return [
            cast(dict[str, Any], row) for row in result.data if isinstance(row, dict)
        ]
    return []


def get_validated_recommendations(
    bolt_pattern: str,
    vehicle_specs: dict[str, Any],
    fitment_data: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """
    Get Kansei wheel recommendations validated against vehicle specs.

    Flow:
    1. Get all Kansei wheels for this bolt pattern
    2. If we have fitment data, find wheels matching those proven specs
    3. Validate all candidates against vehicle specs
    4. Return only wheels that pass validation

    Returns:
        (validated_wheels, source) - source is 'proven', 'compatible', or 'none'
    """
    # Step 1: Get all wheels for bolt pattern
    all_wheels = find_matching_wheels(bolt_pattern=bolt_pattern, limit=100)
    if not all_wheels:
        return [], "none"

    # Step 2: If fitment data exists, find matching wheels first
    if fitment_data:
        matched_wheels = _match_to_fitment_data(bolt_pattern, fitment_data, all_wheels)
        if matched_wheels:
            # Step 3: Validate matched wheels
            validated = validate_recommendations(
                matched_wheels, vehicle_specs, fitment_data
            )
            if validated:
                return validated, "proven"

    # Step 4: No fitment matches - filter all wheels by vehicle specs
    filtered = filter_wheels_by_vehicle_specs(all_wheels, vehicle_specs)
    if filtered:
        return filtered, "compatible"

    return [], "none"


def _match_to_fitment_data(
    bolt_pattern: str,
    fitment_data: list[dict[str, Any]],
    all_wheels: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Find wheels that match community fitment data specs."""
    matches: dict[str, dict[str, Any]] = {}

    for spec in fitment_data:
        metadata = spec.get("metadata", {})
        front_diameter = metadata.get("front_diameter")
        front_width = metadata.get("front_width")
        front_offset = metadata.get("front_offset", 0)

        if not front_diameter or not front_width:
            continue

        # Find wheels close to this spec
        for wheel in all_wheels:
            w_diameter = wheel.get("diameter", 0)
            w_width = wheel.get("width", 0)
            w_offset = wheel.get("wheel_offset", 0)

            # Match within tolerance
            if (
                abs(w_diameter - front_diameter) < 0.5
                and abs(w_width - front_width) <= 0.5
                and abs(w_offset - front_offset) <= 15
            ):
                key = f"{wheel['model']}-{w_diameter}-{w_width}-{w_offset}"
                if key not in matches:
                    matches[key] = wheel

    return list(matches.values())


def format_recommendations(
    bolt_pattern: str,
    vehicle_specs: dict[str, Any],
    fitment_data: list[dict[str, Any]] | None = None,
) -> str:
    """
    Format validated Kansei wheel recommendations.

    Args:
        bolt_pattern: Vehicle's bolt pattern
        vehicle_specs: Validated vehicle specs (max_diameter, width_range, offset_range)
        fitment_data: Community fitment data (may be empty)
    """
    validated_wheels, source = get_validated_recommendations(
        bolt_pattern, vehicle_specs, fitment_data
    )

    if not validated_wheels:
        return ""

    # Group by model
    models: dict[str, list[dict[str, Any]]] = {}
    for wheel in validated_wheels:
        model_name = wheel.get("model", "Unknown")
        if model_name not in models:
            models[model_name] = []
        models[model_name].append(wheel)

    # Format header based on source
    if source == "proven":
        header = "**KANSEI WHEELS THAT FIT (verified by community data):**"
    else:
        header = "**KANSEI WHEELS THAT FIT (based on vehicle specs):**"

    lines = [f"\n{header}"]

    for model_name, wheels in list(models.items())[:5]:
        # Format each size with its specific URL
        size_links = []
        seen_sizes: set[str] = set()
        for w in sorted(
            wheels, key=lambda x: (x.get("diameter", 0), x.get("width", 0))
        ):
            size_str = f"{int(w['diameter'])}x{w['width']} +{w.get('wheel_offset', 0)}"
            if size_str in seen_sizes:
                continue
            seen_sizes.add(size_str)
            url = w.get("url", "")
            if url:
                size_links.append(f"[{size_str}]({url})")
            else:
                size_links.append(size_str)
            if len(size_links) >= 4:
                break

        price = min(w.get("price", 0) for w in wheels if w.get("price", 0) > 0) or 0
        lines.append(
            f"- **{model_name}**: {', '.join(size_links)} (from ${price:.0f}/wheel)"
        )

    # Add specs note
    max_d = vehicle_specs.get("max_diameter", "?")
    width_r = vehicle_specs.get("width_range", "?")
    offset_r = vehicle_specs.get("offset_range", "?")
    lines.append(
        f'\n*Vehicle specs: max {max_d}" diameter, {width_r}" width, {offset_r} offset*'
    )

    return "\n".join(lines)
