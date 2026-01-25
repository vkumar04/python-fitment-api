"""Kansei wheel catalog lookup and recommendation formatting."""

import os
from typing import Any, cast

from supabase import Client, create_client

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


def format_recommendations(
    bolt_pattern: str,
    fitment_specs: list[dict[str, Any]],
    offset_tolerance: int = 15,
) -> str:
    """Format Kansei wheel recommendations based on fitment specs."""
    all_matches: dict[str, dict[str, Any]] = {}

    for spec in fitment_specs:
        metadata = spec.get("metadata", {})
        front_diameter = metadata.get("front_diameter")
        front_width = metadata.get("front_width")
        front_offset = metadata.get("front_offset")

        matches = find_matching_wheels(
            bolt_pattern=bolt_pattern,
            diameter=front_diameter,
            width=front_width,
            offset=front_offset,
            offset_tolerance=offset_tolerance,
        )

        for wheel in matches:
            key = f"{wheel['model']}-{wheel['diameter']}-{wheel['width']}-{wheel.get('wheel_offset', 0)}"
            if key not in all_matches:
                all_matches[key] = wheel

    if not all_matches:
        return _format_broader_search(bolt_pattern)

    return _format_matches(all_matches)


def _format_broader_search(bolt_pattern: str) -> str:
    """Format recommendations from a broader bolt-pattern-only search."""
    broader_matches = find_matching_wheels(bolt_pattern=bolt_pattern)
    if not broader_matches:
        return "\n**KANSEI WHEELS:** No exact matches found for your bolt pattern."

    broader_models: dict[str, list[dict[str, Any]]] = {}
    for w in broader_matches[:20]:
        model_name = w.get("model", "Unknown")
        if model_name not in broader_models:
            broader_models[model_name] = []
        broader_models[model_name].append(w)

    lines = ["\n**KANSEI WHEELS AVAILABLE FOR YOUR BOLT PATTERN:**"]
    for model_name, wheels in list(broader_models.items())[:5]:
        wheel = wheels[0]
        url = wheel.get("url", "")
        sizes = set(
            f"{int(w['diameter'])}x{w['width']} +{w.get('wheel_offset', 0)}"
            for w in wheels
        )
        if url:
            lines.append(f"- [**{model_name}**]({url}): {', '.join(sorted(sizes)[:4])}")
        else:
            lines.append(f"- **{model_name}**: {', '.join(sorted(sizes)[:4])}")
    lines.append("\n*Note: Check offset compatibility with your desired fitment.*")
    return "\n".join(lines)


def _format_matches(all_matches: dict[str, dict[str, Any]]) -> str:
    """Format exact wheel matches."""
    lines = ["\n**KANSEI WHEELS THAT FIT:**"]

    grouped_models: dict[str, list[dict[str, Any]]] = {}
    for wheel in all_matches.values():
        model_name = wheel.get("model", "Unknown")
        if model_name not in grouped_models:
            grouped_models[model_name] = []
        grouped_models[model_name].append(wheel)

    for model_name, wheels in list(grouped_models.items())[:5]:
        wheel = wheels[0]
        url = wheel.get("url", "")
        sizes = [
            f"{int(w['diameter'])}x{w['width']} +{w.get('wheel_offset', 0)}"
            for w in wheels[:3]
        ]
        price = wheel.get("price", 0)
        if url:
            lines.append(
                f"- [**{model_name}**]({url}): {', '.join(sizes)} (from ${price:.0f}/wheel)"
            )
        else:
            lines.append(
                f"- **{model_name}**: {', '.join(sizes)} (from ${price:.0f}/wheel)"
            )

    return "\n".join(lines)
