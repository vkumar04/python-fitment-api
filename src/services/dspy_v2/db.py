"""Database operations for the DSPy v2 pipeline.

Handles vehicle_specs lookups and inserts, plus Kansei wheel queries.
All functions are **synchronous** because the pipeline runs inside
``asyncio.to_thread()`` from the RAG service.
"""

from typing import Any

from ...db.client import get_supabase_client as _get_client


def _safe_float(val: Any, default: float = 0.0) -> float:
    """Safely convert value to float."""
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _safe_int(val: Any, default: int = 0) -> int:
    """Safely convert value to int."""
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


# -----------------------------------------------------------------------------
# Vehicle Specs Operations
# -----------------------------------------------------------------------------


def find_vehicle_specs(
    year: int | None = None,
    make: str | None = None,
    model: str | None = None,
    chassis_code: str | None = None,
) -> dict[str, Any] | None:
    """Find vehicle specs from the database.

    Returns the best matching spec or None if not found.
    """
    result = (
        _get_client()
        .rpc(
            "find_vehicle_specs",
            {
                "p_year": year,
                "p_make": make,
                "p_model": model,
                "p_chassis_code": chassis_code,
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
                "oem_diameter": _safe_float(row.get("oem_diameter"))
                if row.get("oem_diameter")
                else None,
                "min_diameter": _safe_int(row.get("min_diameter"), 15),
                "max_diameter": _safe_int(row.get("max_diameter"), 20),
                "oem_width": _safe_float(row.get("oem_width"))
                if row.get("oem_width")
                else None,
                "min_width": _safe_float(row.get("min_width"), 6.0),
                "max_width": _safe_float(row.get("max_width"), 10.0),
                "oem_offset": _safe_int(row.get("oem_offset"))
                if row.get("oem_offset")
                else None,
                "min_offset": _safe_int(row.get("min_offset"), -10),
                "max_offset": _safe_int(row.get("max_offset"), 50),
                "stock_offset_adjustment": _safe_int(
                    row.get("stock_offset_adjustment"), 0
                ),
                "lowered_offset_adjustment": _safe_int(
                    row.get("lowered_offset_adjustment"), -5
                ),
                "coilover_offset_adjustment": _safe_int(
                    row.get("coilover_offset_adjustment"), -10
                ),
                "air_offset_adjustment": _safe_int(
                    row.get("air_offset_adjustment"), -15
                ),
                "source": row.get("source"),
                "verified": row.get("verified", False),
                "confidence": _safe_float(row.get("confidence"), 0.8),
            }

    return None


def save_vehicle_specs(
    year_start: int | None,
    year_end: int | None,
    make: str,
    model: str,
    chassis_code: str | None,
    bolt_pattern: str,
    center_bore: float,
    stud_size: str | None = None,
    min_diameter: int = 15,
    max_diameter: int = 20,
    min_width: float = 6.0,
    max_width: float = 10.0,
    min_offset: int = -10,
    max_offset: int = 50,
    source: str = "web_search",
    source_url: str | None = None,
    confidence: float = 0.8,
) -> int | None:
    """Save or update vehicle specs in the database.

    Returns the ID of the inserted/updated row.
    """
    result = (
        _get_client()
        .rpc(
            "upsert_vehicle_specs",
            {
                "p_year_start": year_start,
                "p_year_end": year_end,
                "p_make": make,
                "p_model": model,
                "p_chassis_code": chassis_code,
                "p_bolt_pattern": bolt_pattern,
                "p_center_bore": center_bore,
                "p_stud_size": stud_size,
                "p_min_diameter": min_diameter,
                "p_max_diameter": max_diameter,
                "p_min_width": min_width,
                "p_max_width": max_width,
                "p_min_offset": min_offset,
                "p_max_offset": max_offset,
                "p_source": source,
                "p_source_url": source_url,
                "p_confidence": confidence,
            },
        )
        .execute()
    )

    if result.data is not None:
        return int(result.data) if isinstance(result.data, (int, float, str)) else None

    return None


# -----------------------------------------------------------------------------
# Kansei Wheels Operations
# -----------------------------------------------------------------------------


def find_kansei_wheels(
    bolt_pattern: str,
    min_diameter: int | None = None,
    max_diameter: int | None = None,
    min_width: float | None = None,
    max_width: float | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Find Kansei wheels matching the bolt pattern and size constraints.

    Returns list of wheels with all relevant info.
    """
    client = _get_client()
    query = (
        client.table("kansei_wheels")
        .select(
            "id, model, finish, sku, diameter, width, bolt_pattern, wheel_offset, price, category, url, in_stock, weight"
        )
        .ilike("bolt_pattern", bolt_pattern)
    )

    if min_diameter is not None:
        query = query.gte("diameter", min_diameter)
    if max_diameter is not None:
        query = query.lte("diameter", max_diameter)
    if min_width is not None:
        query = query.gte("width", min_width)
    if max_width is not None:
        query = query.lte("width", max_width)

    result = query.eq("in_stock", True).limit(limit).execute()

    wheels = []
    if result.data and isinstance(result.data, list):
        for row in result.data:
            if isinstance(row, dict):
                wheels.append(
                    {
                        "id": row.get("id"),
                        "model": row.get("model"),
                        "finish": row.get("finish"),
                        "sku": row.get("sku"),
                        "diameter": _safe_float(row.get("diameter"), 0.0),
                        "width": _safe_float(row.get("width"), 0.0),
                        "bolt_pattern": row.get("bolt_pattern"),
                        "offset": _safe_int(row.get("wheel_offset"), 0),
                        "price": _safe_float(row.get("price"))
                        if row.get("price")
                        else None,
                        "category": row.get("category"),
                        "url": row.get("url"),
                        "in_stock": row.get("in_stock", True),
                        "weight": _safe_float(row.get("weight"))
                        if row.get("weight")
                        else None,
                    }
                )

    return wheels


# -----------------------------------------------------------------------------
# Community Fitments Operations
# -----------------------------------------------------------------------------


def search_community_fitments(
    make: str,
    model: str,
    year: int | None = None,
    fitment_style: str | None = None,
    suspension: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Search community fitment data for proven setups."""
    # Build search query
    search_terms = [make, model]
    if year:
        search_terms.insert(0, str(year))
    search_query = " ".join(search_terms)

    result = (
        _get_client()
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

    fitments = []
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
                        "document": row.get("document"),
                    }
                )

    # Filter by suspension if specified (parse from document/notes)
    if suspension and fitments:
        suspension_lower = suspension.lower()
        suspension_keywords = {
            "stock": ["stock", "factory", "oem"],
            "lowered": ["lowered", "lowering springs", "dropped"],
            "coilovers": ["coilovers", "coils"],
            "air": ["air", "bagged", "air ride"],
            "lifted": ["lifted", "lift kit", "leveled"],
        }
        keywords = suspension_keywords.get(suspension_lower, [suspension_lower])

        matching = []
        other = []
        for f in fitments:
            doc = (f.get("document") or "").lower()
            if any(kw in doc for kw in keywords):
                matching.append(f)
            else:
                other.append(f)

        fitments = matching + other

    return fitments


def format_fitments_for_prompt(fitments: list[dict[str, Any]]) -> str:
    """Format community fitments as a string for the LLM prompt."""
    if not fitments:
        return "(No community fitment data available for this vehicle)"

    lines = []
    for i, f in enumerate(fitments[:5], 1):
        setup = f.get("fitment_setup", "square")
        style = f.get("fitment_style", "unknown")

        front = f"{f.get('front_diameter', '?')}x{f.get('front_width', '?')} +{f.get('front_offset', '?')}"
        rear = f"{f.get('rear_diameter', '?')}x{f.get('rear_width', '?')} +{f.get('rear_offset', '?')}"

        notes = []
        if f.get("has_poke"):
            notes.append("has poke")
        if f.get("needs_mods"):
            notes.append("needs mods")

        notes_str = f" ({', '.join(notes)})" if notes else ""

        lines.append(
            f"**Setup {i}** ({style}, {setup}): Front {front} | Rear {rear}{notes_str}"
        )

    return "\n".join(lines)


def format_kansei_for_prompt(wheels: list[dict[str, Any]]) -> str:
    """Format Kansei wheels as a string for the LLM prompt."""
    if not wheels:
        return "(No Kansei wheels available for this bolt pattern)"

    # Group by model
    by_model: dict[str, list[dict[str, Any]]] = {}
    for w in wheels:
        model = w.get("model", "Unknown")
        if model not in by_model:
            by_model[model] = []
        by_model[model].append(w)

    lines = []
    for model, model_wheels in list(by_model.items())[:6]:
        # Get unique sizes
        sizes = []
        seen = set()
        for w in sorted(
            model_wheels, key=lambda x: (x.get("diameter", 0), x.get("width", 0))
        ):
            size_key = f"{w.get('diameter')}-{w.get('width')}-{w.get('offset')}"
            if size_key in seen:
                continue
            seen.add(size_key)

            size_str = f"{int(w['diameter'])}x{w['width']} +{w['offset']}"
            url = w.get("url", "")
            if url:
                sizes.append(f"[{size_str}]({url})")
            else:
                sizes.append(size_str)

            if len(sizes) >= 4:
                break

        prices = [w.get("price", 0) for w in model_wheels if w.get("price")]
        min_price = min(prices) if prices else 0

        lines.append(f"- **{model}**: {', '.join(sizes)} (from ${min_price:.0f}/wheel)")

    return "\n".join(lines)
