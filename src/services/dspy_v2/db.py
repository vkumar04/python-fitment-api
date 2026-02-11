"""Database operations for the DSPy v2 pipeline.

Handles vehicle_specs lookups and inserts, plus Kansei wheel queries.
All functions are **synchronous** because the pipeline runs inside
``asyncio.to_thread()`` from the RAG service.
"""

from typing import Any

from ...db.client import get_supabase_client as _get_client
from ...utils.converters import safe_float as _safe_float, safe_int as _safe_int
from ...utils.tire_math import recommend_tire_size, calculate_sidewall_height


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

    Uses a direct table query instead of an RPC to ensure correct model
    matching and compatibility with both old and new DB schemas.

    Returns the best matching spec or None if not found.
    """
    client = _get_client()
    query = client.table("vehicle_specs").select("*")

    if make:
        query = query.ilike("make", make)
    if model:
        query = query.ilike("model", model)
    if chassis_code:
        query = query.ilike("chassis_code", chassis_code)

    result = query.limit(10).execute()

    if not result.data or not isinstance(result.data, list):
        return None

    # Filter and score results in Python for accurate matching
    best: dict[str, Any] | None = None
    best_score = -1

    for row in result.data:
        if not isinstance(row, dict):
            continue

        score = 0

        # Year match: row must span the requested year
        if year:
            y_start = _safe_int(row.get("year_start"))
            y_end = _safe_int(row.get("year_end"))
            if y_start is not None and year < y_start:
                continue
            if y_end is not None and year > y_end:
                continue
            score += 1  # Year is within range

        # Exact model match scores higher than substring match
        row_model = str(row.get("model") or "").lower()
        if model and model.lower() == row_model:
            score += 10  # Exact match
        elif model and model.lower() in row_model:
            score += 2  # Substring match

        # Chassis code match
        row_chassis = str(row.get("chassis_code") or "")
        if chassis_code and row_chassis:
            if chassis_code.upper() == row_chassis.upper():
                score += 5

        # Prefer verified / high-confidence rows (new schema)
        if row.get("verified"):
            score += 3
        confidence = _safe_float(row.get("confidence"), 0.0)
        if confidence >= 0.8:
            score += 2

        if score > best_score:
            best_score = score
            best = row

    if best is None:
        return None

    return {
        "id": best.get("id"),
        "year_start": best.get("year_start"),
        "year_end": best.get("year_end"),
        "make": best.get("make"),
        "model": best.get("model"),
        "chassis_code": best.get("chassis_code"),
        "trim": best.get("trim"),
        "bolt_pattern": best.get("bolt_pattern"),
        "center_bore": _safe_float(best.get("center_bore"), 0.0),
        "stud_size": best.get("stud_size"),
        "oem_diameter": _safe_float(best.get("oem_diameter"))
        if best.get("oem_diameter")
        else None,
        "min_diameter": _safe_int(best.get("min_diameter"), 15),
        "max_diameter": _safe_int(best.get("max_diameter"), 20),
        "oem_width": _safe_float(best.get("oem_width"))
        if best.get("oem_width")
        else None,
        "min_width": _safe_float(best.get("min_width"), 6.0),
        "max_width": _safe_float(best.get("max_width"), 10.0),
        "oem_offset": _safe_int(best.get("oem_offset"))
        if best.get("oem_offset")
        else None,
        "min_offset": _safe_int(best.get("min_offset"), -10),
        "max_offset": _safe_int(best.get("max_offset"), 50),
        "source": best.get("source"),
        "verified": best.get("verified", False),
        "confidence": _safe_float(best.get("confidence"), 0.8),
    }


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
    max_diameter: int | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Search community fitment data for proven setups.

    Args:
        max_diameter: Optional maximum wheel diameter filter. Useful for classic cars
                      where extreme setups (19"+) are uncommon and likely from heavily
                      modified builds.
    """
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
                "result_limit": limit * 2 if max_diameter else limit,  # Fetch more if filtering
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

    # Filter by max diameter if specified (useful for classic cars)
    if max_diameter and fitments:
        fitments = [
            f for f in fitments
            if (f.get("front_diameter") or 0) <= max_diameter
            and (f.get("rear_diameter") or 0) <= max_diameter
        ]

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

    # Ensure we don't exceed the requested limit after filtering
    return fitments[:limit]


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
    """Format Kansei wheels as a string for the LLM prompt.

    Includes math-based fitment calculations (poke, style, mods needed).
    """
    if not wheels:
        return "(No Kansei wheels available for this bolt pattern)"

    # Calculate max width available
    all_widths = [w.get("width", 0) for w in wheels]
    max_width = max(all_widths) if all_widths else 0

    # Group by fitment category for clearer recommendations
    daily_safe = []
    needs_mods = []
    aggressive = []

    for w in wheels:
        fitment_calc = w.get("fitment_calc", {})
        poke = fitment_calc.get("poke_mm", 0)
        mods = fitment_calc.get("mods_needed", [])

        # Categorize by poke level (consistent with style thresholds)
        # - flush/daily-safe: poke < 10mm AND no mods needed
        # - mild poke: 10mm <= poke < 20mm (may need minor work)
        # - aggressive: poke >= 20mm OR significant mods needed
        if poke >= 20:
            aggressive.append(w)
        elif poke >= 10 or mods:
            needs_mods.append(w)  # 10-20mm poke OR has mods = needs work
        else:
            daily_safe.append(w)  # < 10mm poke and no mods = daily-safe

    # Get all unique sizes WITH offsets and poke values
    lines = [
        "## KANSEI WHEELS AVAILABLE (with calculated fitment)",
        f"Max width: {max_width}\"",
        "",
    ]

    # Format by category
    def format_wheel_list(wheel_list: list[dict[str, Any]], category: str) -> list[str]:
        result = [f"**{category}:**"]
        seen = set()
        for w in sorted(wheel_list, key=lambda x: (x.get("diameter", 0), x.get("width", 0))):
            size_key = f"{w.get('diameter')}-{w.get('width')}-{w.get('offset')}"
            if size_key in seen:
                continue
            seen.add(size_key)

            d = int(w.get("diameter", 0))
            width = w.get("width", 0)
            offset = w.get("offset", 0)
            fitment_calc = w.get("fitment_calc", {})
            poke = fitment_calc.get("poke_mm", 0)
            style = fitment_calc.get("style", "unknown")
            mods = fitment_calc.get("mods_needed", [])

            # Build size string with math data
            size_str = f"{d}x{width} +{offset}"
            math_info = f"({poke:+.0f}mm poke, {style})"
            mod_info = f" — {', '.join(mods)}" if mods else ""

            url = w.get("url", "")
            if url:
                result.append(f"- [{size_str}]({url}) {math_info}{mod_info}")
            else:
                result.append(f"- {size_str} {math_info}{mod_info}")

        return result if len(result) > 1 else []

    if daily_safe:
        lines.extend(format_wheel_list(daily_safe, "Daily-safe (no mods needed)"))
        lines.append("")

    if needs_mods:
        lines.extend(format_wheel_list(needs_mods, "Needs minor mods (fender roll/camber)"))
        lines.append("")

    if aggressive:
        lines.extend(format_wheel_list(aggressive, "Aggressive/Show (significant mods)"))
        lines.append("")

    # Add available sizes summary for validation
    unique_sizes = set()
    for w in wheels:
        d = int(w.get("diameter", 0))
        width = w.get("width", 0)
        offset = w.get("offset", 0)
        unique_sizes.add(f"{d}x{width}+{offset}")

    lines.append("**Available sizes:** " + ", ".join(sorted(unique_sizes)))
    lines.append("")
    lines.append("CRITICAL: Only recommend sizes from this list. Use the poke values to match user's desired fitment style.")

    return "\n".join(lines)


def generate_recommended_setups(
    wheels: list[dict[str, Any]],
    fitment_style: str | None = None,
    suspension: str | None = None,
    specs: dict[str, Any] | None = None,
) -> str:
    """Generate pre-computed setup recommendations using math.

    This produces concrete recommendations that OpenAI should present verbatim,
    rather than letting OpenAI invent specs.

    The tire sizing now accounts for BOTH style AND suspension:
    - Flush + Stock = standard sizing
    - Aggressive + Bagged = narrow tires to clear when aired out
    - Track + Coilovers = narrow tires for compression clearance

    Args:
        wheels: List of validated Kansei wheels with fitment_calc data
        fitment_style: User's desired style (flush/aggressive/track)
        suspension: User's suspension type (stock/lowered/coilovers/air)

    Returns:
        Formatted string with 1-2 recommended setups
    """
    if not wheels:
        return "(No Kansei wheels fit this vehicle)"

    susp = (suspension or "stock").lower()

    # Categorize by fitment style using consistent thresholds:
    # - flush: poke < 10mm (matches calculate_wheel_fitment thresholds)
    # - mild poke: 10mm <= poke < 20mm
    # - aggressive: poke >= 20mm
    flush_wheels = []       # poke < 10mm
    mild_poke_wheels = []   # 10mm <= poke < 20mm
    aggressive_wheels = []  # poke >= 20mm

    for w in wheels:
        calc = w.get("fitment_calc", {})
        poke = calc.get("poke_mm", 0)

        if poke < 10:
            flush_wheels.append(w)
        elif poke < 20:
            mild_poke_wheels.append(w)
        else:
            aggressive_wheels.append(w)

    # Select wheels based on style preference with STRICT filtering
    target_wheels = []

    if fitment_style:
        style_lower = fitment_style.lower()
        if style_lower in ("flush", "daily", "conservative", "safe"):
            target_wheels = flush_wheels
            # Only fall back to mild poke if user is okay with it
            if not target_wheels:
                # No flush wheels available - don't silently recommend aggressive
                return _no_matching_style_message("flush", mild_poke_wheels, aggressive_wheels)
        elif style_lower in ("aggressive", "poke", "stance", "show"):
            target_wheels = aggressive_wheels or mild_poke_wheels
        elif style_lower in ("track", "performance"):
            # Track/performance: prefer flush/mild for grip, not extreme poke
            target_wheels = flush_wheels or mild_poke_wheels
        else:
            target_wheels = flush_wheels or mild_poke_wheels or aggressive_wheels
    else:
        # No style specified - default to daily-safe
        target_wheels = flush_wheels or mild_poke_wheels or aggressive_wheels

    if not target_wheels:
        target_wheels = wheels

    # Get best square setup (same front/rear)
    square_setup = None
    for w in sorted(target_wheels, key=lambda x: abs(x.get("fitment_calc", {}).get("poke_mm", 0))):
        d = int(w.get("diameter", 0))
        width = w.get("width", 0)
        offset = w.get("offset", 0)
        calc = w.get("fitment_calc", {})
        poke = calc.get("poke_mm", 0)
        style = calc.get("style", "unknown")
        mods = calc.get("mods_needed", [])
        url = w.get("url", "")

        # Calculate correct tire size based on BOTH style AND suspension
        tire_calc = _get_tire_for_suspension(
            wheel_width=width,
            wheel_diameter=d,
            suspension=susp,
            fitment_style=fitment_style,
        )

        square_setup = {
            "type": "Square",
            "front": f"{d}x{width} +{offset}",
            "rear": f"{d}x{width} +{offset}",
            "tire": tire_calc["tire"],
            "tire_alt": tire_calc["tire_alt"],
            "tire_notes": tire_calc["notes"],
            "sidewall_mm": tire_calc["sidewall_mm"],
            "poke": poke,
            "style": style,
            "mods": mods,
            "url": url,
            "model": w.get("model", ""),
            "suspension": susp,
        }
        break

    # Build output
    lines = ["## PRE-COMPUTED RECOMMENDATIONS (use these exact specs)", ""]

    if square_setup:
        susp_label = square_setup['suspension'].title()
        lines.append(f"**Recommended Setup ({square_setup['style']}, {susp_label} suspension)**")
        lines.append(f"Front: {square_setup['front']} | Rear: {square_setup['rear']}")
        lines.append(f"Tire: {square_setup['tire']} (recommended for {susp_label})")
        lines.append(f"  → Sidewall: {square_setup['sidewall_mm']}mm | {square_setup['tire_notes']}")
        if square_setup['tire_alt']:
            lines.append(f"Alternative: {square_setup['tire_alt']} (only if you need more clearance)")
        lines.append(f"Calculated poke: {square_setup['poke']:+.0f}mm ({square_setup['style']})")

        # Mods logic depends on suspension + tire combo
        if square_setup['mods']:
            lines.append(f"Mods needed: {', '.join(square_setup['mods'])}")
        elif square_setup['suspension'] in ("air", "bagged", "bags"):
            lines.append("Mods needed: None with recommended tire (WILL rub with wider tires)")
        elif square_setup['suspension'] in ("coilovers", "coils", "slammed"):
            lines.append("Mods needed: None with recommended tire (may rub with wider/taller tires)")
        else:
            lines.append("Mods needed: None (daily-safe)")
        if square_setup['url']:
            lines.append(f"Kansei: [{square_setup['model']}]({square_setup['url']})")
        lines.append("")

    # Add vehicle-specific warnings
    if specs:
        # Brake clearance warning
        brake_min = specs.get("min_brake_clearance_diameter")
        oem_d = specs.get("oem_diameter")
        if brake_min and oem_d and brake_min >= 17:
            lines.append(f"⚠️ BRAKE CLEARANCE: This vehicle has large brakes that require "
                         f"minimum {brake_min}\" wheels. Smaller wheels will NOT physically fit "
                         f"over the calipers. Stock wheel diameter is {oem_d}\".")
            lines.append("")

        # Staggered-stock warning
        if specs.get("is_staggered_stock"):
            oem_w = specs.get("oem_width", "?")
            oem_rw = specs.get("oem_rear_width", "?")
            oem_o = specs.get("oem_offset", "?")
            oem_ro = specs.get("oem_rear_offset", "?")
            lines.append(
                f"⚠️ STAGGERED STOCK: This vehicle runs staggered from factory "
                f"(front {oem_w}\" +{oem_o} / rear {oem_rw}\" +{oem_ro}). "
                f"A square setup changes the rear handling balance. "
                f"If Kansei doesn't offer the right rear width, consider "
                f"whether the handling tradeoff is acceptable."
            )
            lines.append("")

    lines.append("IMPORTANT: Present these EXACT specs to the user. Do not invent different sizes.")

    return "\n".join(lines)


def _no_matching_style_message(
    requested_style: str,
    mild_poke_wheels: list[dict[str, Any]],
    aggressive_wheels: list[dict[str, Any]],
) -> str:
    """Generate a message when no wheels match the requested fitment style.

    This prevents the system from silently recommending aggressive wheels
    when the user asked for flush.
    """
    lines = ["## PRE-COMPUTED RECOMMENDATIONS", ""]

    if requested_style == "flush":
        lines.append("**No true flush options available** for this vehicle with Kansei wheels.")
        lines.append("")
        if mild_poke_wheels:
            # Show what IS available as an alternative
            w = mild_poke_wheels[0]
            calc = w.get("fitment_calc", {})
            poke = calc.get("poke_mm", 0)
            d = int(w.get("diameter", 0))
            width = w.get("width", 0)
            offset = w.get("offset", 0)
            lines.append(f"Closest option: {d}x{width} +{offset} ({poke:+.0f}mm poke - mild poke, not flush)")
            lines.append("")
            lines.append("This setup will have noticeable poke beyond the fender line.")
            lines.append("If you need true flush fitment, you may need to consider spacers or a different wheel brand.")
        elif aggressive_wheels:
            w = aggressive_wheels[0]
            calc = w.get("fitment_calc", {})
            poke = calc.get("poke_mm", 0)
            lines.append(f"Available Kansei wheels have {poke:+.0f}mm+ poke (aggressive), which is not suitable for a flush look.")
        else:
            lines.append("No Kansei wheels are available for this bolt pattern.")

    lines.append("")
    lines.append("IMPORTANT: Be honest with the user that flush fitment is not achievable with available wheels.")

    return "\n".join(lines)


def _get_tire_for_suspension(
    wheel_width: float,
    wheel_diameter: int,
    suspension: str | None,
    fitment_style: str | None,
) -> dict[str, Any]:
    """Calculate tire size based on wheel specs AND suspension type.

    Uses centralized tire_math module which implements industry-standard formulas:
    - Sidewall height = tire_width × (aspect_ratio / 100)
    - Tire width range from ISO/industry charts
    - Suspension-based width adjustments

    Args:
        wheel_width: Wheel width in inches
        wheel_diameter: Wheel diameter in inches
        suspension: Suspension type (stock/lowered/coilovers/air)
        fitment_style: Fitment style (currently unused, reserved for future)

    Returns:
        Dict with tire recommendation including size, sidewall, and notes
    """
    # fitment_style reserved for future style-specific tire recommendations
    _ = fitment_style

    # Normalize suspension type
    susp = (suspension or "stock").lower()
    if susp in ("coils", "slammed"):
        susp = "coilovers"
    elif susp in ("bags", "bagged"):
        susp = "air"
    elif susp in ("springs", "dropped"):
        susp = "lowered"
    elif susp in ("oem", "factory"):
        susp = "stock"

    # Use centralized tire math
    rec = recommend_tire_size(wheel_width, wheel_diameter, susp)

    return {
        "tire": rec["tire"],
        "tire_alt": rec["tire_alt"],
        "tire_width": rec["tire_width"],
        "tire_aspect": rec["aspect_ratio"],
        "sidewall_mm": rec["sidewall_mm"],
        "alt_sidewall_mm": calculate_sidewall_height(
            rec["tire_width"] + 10, rec["aspect_ratio"]
        ) if rec["tire_alt"] else rec["sidewall_mm"],
        "notes": rec["notes"],
        "is_safe": True,
        "suspension": susp,
    }
