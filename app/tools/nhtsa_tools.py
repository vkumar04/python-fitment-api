"""Synchronous tool wrappers for DSPy ReAct agent.

DSPy tools must be synchronous functions that return strings.
These wrap the async NHTSA client and Supabase queries.
"""

import json
import logging
from typing import Any

import httpx

from app.config import get_settings
from app.models.vehicle import VehicleSpecs
from app.services.fitment_engine import (
    lookup_known_specs,
    score_fitment,
)
from app.services.kansei_db import (
    find_vehicle_specs as db_find_vehicle_specs,
)
from app.services.kansei_db import (
    find_wheels_by_bolt_pattern,
)

logger = logging.getLogger(__name__)


def decode_vin(vin: str) -> str:
    """Decode a vehicle VIN using the NHTSA vPIC API.
    Returns vehicle year, make, model, trim, and available specs."""
    settings = get_settings()
    url = f"{settings.nhtsa_base_url}/vehicles/DecodeVinValues/{vin}?format=json"
    resp = httpx.get(url, timeout=15.0)
    resp.raise_for_status()
    result = resp.json().get("Results", [{}])[0]
    relevant = {
        k: v
        for k, v in result.items()
        if v
        and str(v).strip()
        and k
        in [
            "Make",
            "Model",
            "ModelYear",
            "Trim",
            "DriveType",
            "BodyClass",
            "WheelSizeFront",
            "WheelSizeRear",
            "WheelBaseType",
            "GVWR",
        ]
    }
    return str(relevant)


def get_models_for_make_year(make: str, year: int) -> str:
    """Get all vehicle models for a given make and year from NHTSA."""
    settings = get_settings()
    url = (
        f"{settings.nhtsa_base_url}/vehicles/GetModelsForMakeYear"
        f"/make/{make}/modelyear/{year}?format=json"
    )
    resp = httpx.get(url, timeout=15.0)
    resp.raise_for_status()
    results = resp.json().get("Results", [])
    models = [r.get("Model_Name", "") for r in results]
    return str(models)


def _build_vehicle_specs(
    year: int, make: str, model: str, trim: str = ""
) -> VehicleSpecs | None:
    """Build a VehicleSpecs object from the database.

    Priority: Supabase vehicle_specs table → lookup_known_specs() fallback.
    """
    # 1. Query the database (primary source)
    db_specs: dict[str, Any] | None = None
    try:
        db_specs = db_find_vehicle_specs(
            year=year, make=make, model=model, trim=trim or None
        )
    except Exception as e:
        logger.warning("DB find_vehicle_specs failed: %s", e)

    # 2. Fall back to knowledge base if DB has no match
    kb = lookup_known_specs(make, model, year=year)

    bolt_pattern = (db_specs.get("bolt_pattern") if db_specs else None) or (
        kb.get("bolt_pattern") if kb else None
    )
    if not bolt_pattern:
        return None

    kwargs: dict[str, Any] = {
        "year": year,
        "make": make,
        "model": model,
        "trim": trim or None,
        "bolt_pattern": bolt_pattern,
    }

    # Populate from DB specs (detailed data)
    if db_specs:
        kwargs.update(
            {
                "hub_bore": db_specs.get("center_bore"),
                "chassis_code": db_specs.get("chassis_code"),
                "oem_diameter_front": db_specs.get("oem_diameter_front"),
                "oem_diameter_rear": db_specs.get("oem_diameter_rear"),
                "oem_width_front": db_specs.get("oem_width_front"),
                "oem_width_rear": db_specs.get("oem_width_rear"),
                "oem_offset_front": db_specs.get("oem_offset_front"),
                "oem_offset_rear": db_specs.get("oem_offset_rear"),
                "oem_tire_front": db_specs.get("oem_tire_front"),
                "oem_tire_rear": db_specs.get("oem_tire_rear"),
                "front_brake_size": db_specs.get("front_brake_size"),
                "min_wheel_diameter": db_specs.get("min_wheel_diameter"),
                "is_staggered_stock": db_specs.get("is_staggered_stock", False),
                "is_performance_trim": db_specs.get("is_performance_trim", False),
            }
        )
        # Also set legacy single-value fields from DB
        if db_specs.get("oem_diameter"):
            kwargs.setdefault("oem_diameter", db_specs["oem_diameter"])
        if db_specs.get("oem_width"):
            kwargs.setdefault("oem_width", db_specs["oem_width"])
        if db_specs.get("oem_offset") is not None:
            kwargs.setdefault("oem_offset", db_specs["oem_offset"])

    # Fill gaps from knowledge base
    if kb:
        if kwargs.get("hub_bore") is None:
            kwargs["hub_bore"] = kb.get("center_bore")
        if kwargs.get("oem_diameter_front") is None and kb.get("oem_diameter"):
            kwargs["oem_diameter"] = kb.get("oem_diameter")
        if kwargs.get("oem_width_front") is None and kb.get("oem_width"):
            kwargs["oem_width"] = kb.get("oem_width")
        if kwargs.get("oem_offset_front") is None and kb.get("oem_offset") is not None:
            kwargs["oem_offset"] = kb.get("oem_offset")

    return VehicleSpecs(**{k: v for k, v in kwargs.items() if v is not None})


def _format_result(r: Any) -> dict[str, Any]:
    """Format a single FitmentResult into a JSON-serializable dict."""
    entry: dict[str, Any] = {
        "model": r.wheel.model,
        "finish": r.wheel.finish,
        "size": f"{r.wheel.diameter}x{r.wheel.width}",
        "offset": r.wheel.wheel_offset,
        "bolt_pattern": r.wheel.bolt_pattern,
        "center_bore": r.wheel.center_bore,
        "score": r.fitment_score,
        "notes": r.notes,
        "in_stock": r.wheel.in_stock,
    }
    if r.wheel.url:
        entry["url"] = r.wheel.url
    if r.poke:
        entry["poke"] = {
            "mm": r.poke.poke_mm,
            "stance": r.poke.stance_label,
            "description": r.poke.description,
        }
    if r.tire_recommendation:
        entry["tire"] = r.tire_recommendation.size
    if r.mods_needed:
        entry["mods_needed"] = r.mods_needed
    if r.confidence:
        entry["confidence"] = r.confidence
    if r.position and r.position != "front":
        entry["position"] = r.position
    return entry


def _build_staggered_pairings(
    compatible: list[Any],
    vehicle: Any,
    wheels: list[Any],
) -> list[dict[str, Any]]:
    """Build staggered front/rear pairings from compatible wheels.

    Groups wheels by model name, finds pairs where:
    - Front wheel width <= rear wheel width
    - Front width is close to OEM front, rear width is close to OEM rear
    - Same diameter for both
    Returns up to 5 best pairings sorted by combined score.
    """
    from collections import defaultdict

    oem_wf = vehicle.oem_width_front or 8.0
    oem_wr = vehicle.oem_width_rear or 9.0

    # Score all wheels for rear position too
    rear_scored = {id(w): score_fitment(w, vehicle, position="rear") for w in wheels}
    rear_compatible = {k: v for k, v in rear_scored.items() if v.fitment_score > 0}

    # Group front-compatible wheels by model name
    by_model: dict[str, list[Any]] = defaultdict(list)
    for r in compatible:
        by_model[r.wheel.model].append(r)

    pairings: list[dict[str, Any]] = []

    for model_name, front_candidates in by_model.items():
        # Find rear candidates from the same model
        rear_candidates = [
            rear_scored[id(w)]
            for w in wheels
            if w.model == model_name and id(w) in rear_compatible
        ]
        if not rear_candidates:
            continue

        # Find best front/rear pair: front narrower, rear wider, same diameter
        for front in front_candidates:
            for rear in rear_candidates:
                if front.wheel.diameter != rear.wheel.diameter:
                    continue
                if front.wheel.width >= rear.wheel.width:
                    continue  # front must be narrower than rear
                # Skip if it's the exact same wheel object
                if id(front.wheel) == id(rear.wheel):
                    continue

                # Prefer pairings close to OEM width split
                front_width_diff = abs(front.wheel.width - oem_wf)
                rear_width_diff = abs(rear.wheel.width - oem_wr)
                width_penalty = front_width_diff + rear_width_diff
                combined_score = ((front.fitment_score + rear.fitment_score) / 2) - (
                    width_penalty * 0.02
                )

                pairing = {
                    "type": "staggered_pairing",
                    "model": model_name,
                    "combined_score": round(combined_score, 2),
                    "front": _format_result(front),
                    "rear": _format_result(rear),
                }
                pairing["front"]["position"] = "front"
                pairing["rear"]["position"] = "rear"
                pairings.append(pairing)

    # Sort by combined score, deduplicate by model+sizes
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for p in sorted(pairings, key=lambda x: x["combined_score"], reverse=True):
        key = f"{p['model']}_{p['front']['size']}_{p['rear']['size']}"
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique[:5]


def find_kansei_fitment(year: int, make: str, model: str, trim: str = "") -> str:
    """Find compatible Kansei wheels for a vehicle with full fitment scoring.
    ALWAYS call lookup_vehicle first to confirm the vehicle specs, then call this
    with the same year/make/model/trim to get scored wheel recommendations.
    Returns wheels sorted by fitment score with compatibility notes, poke info,
    tire recommendations, and brake clearance warnings.
    For staggered-stock vehicles, also returns matched front/rear pairings.
    Wheels that physically cannot mount (bore too small, bolt mismatch) are excluded."""
    vehicle = _build_vehicle_specs(year, make, model, trim)
    if vehicle is None:
        return (
            f"Could not build specs for {year} {make} {model}. "
            "Need at least a bolt pattern. Ask the user or try VIN decode."
        )

    wheels = find_wheels_by_bolt_pattern(
        bolt_pattern=vehicle.bolt_pattern, category=None
    )
    if not wheels:
        return f"No Kansei wheels found for bolt pattern {vehicle.bolt_pattern}."

    # Score every wheel for front position (default)
    scored = [score_fitment(w, vehicle, position="front") for w in wheels]
    compatible = [r for r in scored if r.fitment_score > 0]
    compatible.sort(key=lambda r: r.fitment_score, reverse=True)

    if not compatible:
        reasons = set()
        for r in scored:
            if r.notes:
                reasons.add(r.notes[0])
        return (
            f"No compatible Kansei wheels for {year} {make} {model}. "
            f"All {len(scored)} wheels were rejected. "
            f"Reasons: {'; '.join(list(reasons)[:3])}"
        )

    # Format top square (universal) results
    results = [_format_result(r) for r in compatible[:15]]

    # Build staggered pairings for staggered-stock vehicles
    staggered_pairings: list[dict[str, Any]] = []
    if vehicle.is_staggered_stock:
        staggered_pairings = _build_staggered_pairings(compatible, vehicle, wheels)

    summary = (
        f"Found {len(compatible)} compatible wheels out of {len(scored)} total "
        f"for {year} {make} {model}. "
        f"Bolt pattern: {vehicle.bolt_pattern}. "
    )
    if vehicle.hub_bore:
        summary += f"Vehicle hub bore: {vehicle.hub_bore}mm. "
    if vehicle.is_staggered_stock:
        oem_note = ""
        if vehicle.oem_width_front and vehicle.oem_width_rear:
            oem_note = f" (OEM: {vehicle.oem_width_front}F / {vehicle.oem_width_rear}R)"
        summary += f"Vehicle has staggered OEM setup{oem_note}. "
        if staggered_pairings:
            summary += (
                f"Includes {len(staggered_pairings)} staggered front/rear pairings "
                f"that approximate the factory width split. "
            )

    output: dict[str, Any] = {
        "square_setups": results,
    }
    if staggered_pairings:
        output["staggered_pairings"] = staggered_pairings

    return summary + json.dumps(output, default=str)


def lookup_vehicle(make: str, model: str, year: int, trim: str = "") -> str:
    """Look up a vehicle's bolt pattern, hub bore, OEM wheel specs, and brake info.
    ALWAYS call this first to get the bolt pattern before searching for Kansei wheels."""
    # Try database first (primary source of truth)
    try:
        db_specs = db_find_vehicle_specs(
            year=year, make=make, model=model, trim=trim or None
        )
        if db_specs and db_specs.get("bolt_pattern"):
            return str(db_specs)
    except Exception as e:
        logger.warning("DB lookup failed for %s %s %s: %s", year, make, model, e)

    # Fall back to knowledge base
    kb = lookup_known_specs(make, model, year=year)
    if kb:
        return str(kb)
    return f"No specs found for {year} {make} {model}. Try NHTSA VIN decode or ask the user for bolt pattern."
