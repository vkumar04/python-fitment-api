"""Database service for querying Kansei wheel inventory and vehicle specs.

Uses the existing Supabase client and PostgreSQL functions.
All public methods are synchronous (for use in DSPy tools and sync contexts).
"""

from typing import Any, Optional

from app.models.wheel import KanseiWheel
from app.services.db import get_supabase_client


def _safe_float(val: Any, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _safe_int(val: Any, default: int = 0) -> int:
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


def find_wheels_by_bolt_pattern(
    bolt_pattern: str,
    category: Optional[str] = None,
    min_diameter: Optional[float] = None,
    max_diameter: Optional[float] = None,
    in_stock_only: bool = True,
) -> list[KanseiWheel]:
    """Find Kansei wheels matching a bolt pattern with optional filters."""
    client = get_supabase_client()
    query = (
        client.table("kansei_wheels")
        .select(
            "id, model, finish, sku, diameter, width, bolt_pattern, "
            "wheel_offset, category, url, in_stock, center_bore, weight"
        )
        .ilike("bolt_pattern", bolt_pattern)
    )

    if in_stock_only:
        query = query.eq("in_stock", True)
    if category:
        query = query.eq("category", category)
    if min_diameter is not None:
        query = query.gte("diameter", min_diameter)
    if max_diameter is not None:
        query = query.lte("diameter", max_diameter)

    query = query.order("model")
    result = query.execute()

    wheels: list[KanseiWheel] = []
    if result.data and isinstance(result.data, list):
        for row in result.data:
            if isinstance(row, dict):
                wheels.append(
                    KanseiWheel(
                        id=_safe_int(row["id"]),
                        model=str(row["model"]),
                        finish=str(row["finish"]) if row.get("finish") else "",
                        sku=str(row["sku"]) if row.get("sku") else "",
                        diameter=_safe_float(row["diameter"]),
                        width=_safe_float(row["width"]),
                        bolt_pattern=str(row["bolt_pattern"]),
                        wheel_offset=_safe_int(row["wheel_offset"]),
                        category=str(row["category"]) if row.get("category") else "",
                        url=str(row["url"]) if row.get("url") else "",
                        in_stock=bool(row.get("in_stock", True)),
                        center_bore=_safe_float(row.get("center_bore"), 73.1),
                        weight=_safe_float(row.get("weight")) or None,
                    )
                )
    return wheels


def get_all_wheels() -> list[KanseiWheel]:
    """Return full in-stock catalog."""
    return find_wheels_by_bolt_pattern("%", in_stock_only=True)


def get_unique_bolt_patterns() -> list[str]:
    """Return all bolt patterns in catalog."""
    client = get_supabase_client()
    result = client.table("kansei_wheels").select("bolt_pattern").execute()
    patterns: set[str] = set()
    if result.data and isinstance(result.data, list):
        for row in result.data:
            if isinstance(row, dict) and row.get("bolt_pattern"):
                patterns.add(str(row["bolt_pattern"]))
    return sorted(patterns)


def find_vehicle_specs(
    year: Optional[int] = None,
    make: Optional[str] = None,
    model: Optional[str] = None,
    chassis_code: Optional[str] = None,
    trim: Optional[str] = None,
) -> dict[str, Any] | None:
    """Find vehicle specs from the database via RPC.

    Returns the best-matching row with full enhanced fields:
    bolt_pattern, center_bore, OEM front/rear sizes, tire sizes,
    brake data, staggered/performance flags.
    """
    result = (
        get_supabase_client()
        .rpc(
            "find_vehicle_specs",
            {
                "p_year": year,
                "p_make": make,
                "p_model": model,
                "p_chassis_code": chassis_code,
                "p_trim": trim,
            },
        )
        .execute()
    )

    if result.data and isinstance(result.data, list) and len(result.data) > 0:
        row = result.data[0]
        if isinstance(row, dict):
            return {
                "id": row.get("id"),
                "year_start": row.get("year_start"),
                "year_end": row.get("year_end"),
                "make": row.get("make"),
                "model": row.get("model"),
                "chassis_code": row.get("chassis_code"),
                "trim": row.get("trim"),
                "bolt_pattern": row.get("bolt_pattern"),
                "center_bore": _safe_float(row.get("center_bore"), 0.0),
                "stud_size": row.get("stud_size"),
                # Legacy single-value fields
                "oem_diameter": _safe_float(row.get("oem_diameter"))
                if row.get("oem_diameter")
                else None,
                "oem_width": _safe_float(row.get("oem_width"))
                if row.get("oem_width")
                else None,
                "oem_offset": _safe_int(row.get("oem_offset"))
                if row.get("oem_offset")
                else None,
                # Front/rear split
                "oem_diameter_front": _safe_float(row.get("oem_diameter_front"))
                if row.get("oem_diameter_front")
                else None,
                "oem_diameter_rear": _safe_float(row.get("oem_diameter_rear"))
                if row.get("oem_diameter_rear")
                else None,
                "oem_width_front": _safe_float(row.get("oem_width_front"))
                if row.get("oem_width_front")
                else None,
                "oem_width_rear": _safe_float(row.get("oem_width_rear"))
                if row.get("oem_width_rear")
                else None,
                "oem_offset_front": _safe_int(row.get("oem_offset_front"))
                if row.get("oem_offset_front")
                else None,
                "oem_offset_rear": _safe_int(row.get("oem_offset_rear"))
                if row.get("oem_offset_rear")
                else None,
                # Tire sizes
                "oem_tire_front": row.get("oem_tire_front"),
                "oem_tire_rear": row.get("oem_tire_rear"),
                # Brake data
                "front_brake_size": row.get("front_brake_size"),
                "min_wheel_diameter": _safe_int(row.get("min_wheel_diameter"))
                if row.get("min_wheel_diameter")
                else None,
                # Flags
                "is_staggered_stock": bool(row.get("is_staggered_stock", False)),
                "is_performance_trim": bool(row.get("is_performance_trim", False)),
                # Ranges
                "min_diameter": _safe_int(row.get("min_diameter"), 15),
                "max_diameter": _safe_int(row.get("max_diameter"), 20),
                "min_width": _safe_float(row.get("min_width"), 6.0),
                "max_width": _safe_float(row.get("max_width"), 10.0),
                "min_offset": _safe_int(row.get("min_offset"), -10),
                "max_offset": _safe_int(row.get("max_offset"), 50),
                # Provenance
                "source": row.get("source"),
                "verified": row.get("verified", False),
                "confidence": _safe_float(row.get("confidence"), 0.8),
            }
    return None


def search_community_fitments(
    make: str,
    model: str,
    year: Optional[int] = None,
    fitment_style: Optional[str] = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Search community fitment data for proven setups."""
    search_terms = [str(year)] if year else []
    search_terms.extend([make, model])
    search_query = " ".join(search_terms)

    result = (
        get_supabase_client()
        .rpc(
            "search_fitments",
            {
                "search_query": search_query,
                "filter_year": year,
                "filter_make": make,
                "filter_model": model,
                "filter_style": fitment_style,
                "result_limit": limit,
            },
        )
        .execute()
    )

    fitments: list[dict[str, Any]] = []
    if result.data and isinstance(result.data, list):
        for row in result.data:
            if isinstance(row, dict):
                fitments.append(
                    {
                        "year": row.get("year"),
                        "make": row.get("make"),
                        "model": row.get("model"),
                        "front_diameter": row.get("front_diameter"),
                        "front_width": row.get("front_width"),
                        "front_offset": row.get("front_offset"),
                        "rear_diameter": row.get("rear_diameter"),
                        "rear_width": row.get("rear_width"),
                        "rear_offset": row.get("rear_offset"),
                        "fitment_setup": row.get("fitment_setup"),
                        "fitment_style": row.get("fitment_style"),
                        "has_poke": row.get("has_poke"),
                        "needs_mods": row.get("needs_mods"),
                    }
                )
    return fitments
