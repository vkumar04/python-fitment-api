"""Supabase fitment database operations."""

import os
from typing import Any, cast

import pandas as pd

from supabase import Client, create_client

from ..services.fitment import (
    determine_setup,
    determine_style,
    has_poke,
    needs_modifications,
    to_document_text,
)
from ..utils.converters import safe_float, safe_int

# Supabase client (lazy loaded)
_supabase: Client | None = None


def _get_client() -> Client:
    """Get or create Supabase client."""
    global _supabase
    if _supabase is None:
        _supabase = create_client(
            os.getenv("SUPABASE_URL", ""),
            os.getenv("SUPABASE_KEY", ""),
        )
    return _supabase


def search(
    query: str,
    year: int | None = None,
    make: str | None = None,
    model: str | None = None,
    fitment_style: str | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Search for fitments using full-text search."""
    client = _get_client()
    result = client.rpc(
        "search_fitments",
        {
            "search_query": query,
            "filter_year": year,
            "filter_make": make,
            "filter_model": model,
            "filter_style": fitment_style,
            "result_limit": limit,
        },
    ).execute()

    fitments: list[dict[str, Any]] = []
    if result.data and isinstance(result.data, list):
        for row in result.data:
            if isinstance(row, dict):
                fitments.append(_format_fitment_result(row))

    return fitments


def find_similar_vehicles(
    make: str | None,
    model: str | None,
    year: int | None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Find fitments from similar vehicles when exact match not found."""
    client = _get_client()
    similar_results: list[dict[str, Any]] = []

    # Strategy 1: Same make, different years of same model
    if make and model:
        result = (
            client.table("fitments")
            .select(_fitment_columns())
            .eq("make", make)
            .ilike("model", f"%{model}%")
            .limit(limit)
            .execute()
        )

        if result.data and isinstance(result.data, list):
            for row in result.data:
                if isinstance(row, dict):
                    similar_results.append(
                        _format_similar_result(row, "Same model, different year")
                    )

    # Strategy 2: Same make, different model
    if len(similar_results) < limit and make:
        result = (
            client.table("fitments")
            .select(_fitment_columns())
            .eq("make", make)
            .limit(limit - len(similar_results))
            .execute()
        )

        if result.data and isinstance(result.data, list):
            for row in result.data:
                if not isinstance(row, dict):
                    continue
                # Skip duplicates
                if any(
                    r["metadata"]["model"] == row.get("model")
                    and r["metadata"]["year"] == row.get("year")
                    for r in similar_results
                ):
                    continue
                similar_results.append(
                    _format_similar_result(row, f"Same make ({make}), different model")
                )

    return similar_results[:limit]


def get_makes() -> list[str]:
    """Get all unique makes."""
    result = _get_client().rpc("get_makes").execute()
    if not isinstance(result.data, list):
        return []
    return [cast(str, row["make"]) for row in result.data if isinstance(row, dict)]


def get_models(make: str) -> list[str]:
    """Get all models for a make."""
    result = _get_client().rpc("get_models", {"filter_make": make}).execute()
    if not isinstance(result.data, list):
        return []
    return [cast(str, row["model"]) for row in result.data if isinstance(row, dict)]


def get_years() -> list[int]:
    """Get all unique years."""
    result = _get_client().rpc("get_years").execute()
    if not isinstance(result.data, list):
        return []
    return [cast(int, row["year"]) for row in result.data if isinstance(row, dict)]


def save_pending_fitment(
    year: int | None,
    make: str | None,
    model: str | None,
    trim: str | None,
    fitment_style: str | None,
    bolt_pattern: str | None,
    notes: str | None = None,
) -> int | None:
    """Save an LLM-generated fitment to the pending table for review."""
    if not make or not model:
        return None

    try:
        result = (
            _get_client()
            .table("fitments_pending")
            .insert(
                {
                    "year": year,
                    "make": make,
                    "model": model,
                    "trim": trim,
                    "bolt_pattern": bolt_pattern,
                    "fitment_style": fitment_style,
                    "source": "llm_generated",
                    "notes": notes,
                    "reviewed": False,
                    "approved": False,
                }
            )
            .execute()
        )

        if result.data and isinstance(result.data, list) and len(result.data) > 0:
            first_row = result.data[0]
            if isinstance(first_row, dict):
                id_val = first_row.get("id")
                if isinstance(id_val, int):
                    return id_val
                elif isinstance(id_val, (str, float)):
                    return int(id_val)
    except Exception:
        pass
    return None


def load_csv_data(csv_path: str, batch_size: int = 500) -> int:
    """Load fitment data from CSV into Supabase."""
    client = _get_client()
    df = pd.read_csv(csv_path)
    df = df.fillna("")

    records: list[dict[str, Any]] = []

    for _, row in df.iterrows():
        row_dict = row.to_dict()
        records.append(_csv_row_to_record(row_dict))

    total_inserted = 0
    for i in range(0, len(records), batch_size):
        batch = records[i : i + batch_size]
        client.table("fitments").insert(batch).execute()
        total_inserted += len(batch)
        print(f"Inserted {total_inserted}/{len(records)} records...")

    return len(records)


# -----------------------------------------------------------------------------
# Private helpers
# -----------------------------------------------------------------------------


def _fitment_columns() -> str:
    """Column list for fitment queries."""
    return (
        "year, make, model, document, front_diameter, front_width, front_offset, "
        "rear_diameter, rear_width, rear_offset, fitment_setup, fitment_style, "
        "has_poke, needs_mods"
    )


def _format_fitment_result(row: dict[str, Any]) -> dict[str, Any]:
    """Format a fitment row into standard result format."""
    return {
        "document": row.get("document", ""),
        "metadata": {
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
            "needs_modifications": row.get("needs_mods"),
        },
        "rank": row.get("rank", 0),
    }


def _format_similar_result(row: dict[str, Any], reason: str) -> dict[str, Any]:
    """Format a similar vehicle result."""
    result = _format_fitment_result(row)
    result["is_similar"] = True
    result["similarity_reason"] = reason
    return result


def _csv_row_to_record(row: dict[str, Any]) -> dict[str, Any]:
    """Convert a CSV row to a database record."""
    doc_text = to_document_text(row)
    setup = determine_setup(row)
    style = determine_style(row)

    tire_front = f"{row.get('front_tire_width', '')}/{row.get('front_tire_aspect', '')}R{row.get('front_tire_diameter', '')}"
    tire_rear = f"{row.get('rear_tire_width', '')}/{row.get('rear_tire_aspect', '')}R{row.get('rear_tire_diameter', '')}"

    return {
        "year": safe_int(row.get("year")),
        "make": str(row.get("make", "")),
        "model": str(row.get("model", "")),
        "front_diameter": safe_float(row.get("front_diameter")),
        "front_width": safe_float(row.get("front_width")),
        "front_offset": safe_int(row.get("front_offset")),
        "front_backspacing": safe_float(row.get("front_backspacing")),
        "front_spacer": safe_float(
            row.get("front_wheel_spacers")
            if str(row.get("front_wheel_spacers", "")).replace(".", "").isdigit()
            else 0
        ),
        "rear_diameter": safe_float(row.get("rear_diameter")),
        "rear_width": safe_float(row.get("rear_width")),
        "rear_offset": safe_int(row.get("rear_offset")),
        "rear_backspacing": safe_float(row.get("rear_backspacing")),
        "rear_spacer": safe_float(
            row.get("rear_wheel_spacers")
            if str(row.get("rear_wheel_spacers", "")).replace(".", "").isdigit()
            else 0
        ),
        "tire_front": tire_front,
        "tire_rear": tire_rear,
        "fitment_setup": setup,
        "fitment_style": style,
        "has_poke": has_poke(row),
        "needs_mods": needs_modifications(row),
        "notes": f"Rubbing: {row.get('rubbing', '')} | Trimming: {row.get('trimming', '')} | Suspension: {row.get('suspension_type', '')}",
        "document": doc_text,
    }
