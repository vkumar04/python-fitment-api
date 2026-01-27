"""Supabase fitment database operations - async version.

Provides metadata queries (makes/models/years) and CSV data loading.
Fitment search is handled by dspy_v2/db.py's search_community_fitments().
"""

import asyncio
import time
from typing import Any, cast

import pandas as pd

from ..core.logging import log_db_query, logger
from ..services.fitment import (
    determine_setup,
    determine_style,
    has_poke,
    needs_modifications,
    to_document_text,
)
from ..utils.converters import safe_float, safe_int
from .client import get_supabase_client as _get_client


async def get_makes() -> list[str]:
    """Get all unique makes."""
    start = time.time()

    def _query():
        return _get_client().rpc("get_makes").execute()

    result = await asyncio.to_thread(_query)
    log_db_query("get_makes", "fitments", (time.time() - start) * 1000)

    if not isinstance(result.data, list):
        return []
    return [cast(str, row["make"]) for row in result.data if isinstance(row, dict)]


async def get_models(make: str) -> list[str]:
    """Get all models for a make."""
    start = time.time()

    def _query():
        return _get_client().rpc("get_models", {"filter_make": make}).execute()

    result = await asyncio.to_thread(_query)
    log_db_query("get_models", "fitments", (time.time() - start) * 1000)

    if not isinstance(result.data, list):
        return []
    return [cast(str, row["model"]) for row in result.data if isinstance(row, dict)]


async def get_years() -> list[int]:
    """Get all unique years."""
    start = time.time()

    def _query():
        return _get_client().rpc("get_years").execute()

    result = await asyncio.to_thread(_query)
    log_db_query("get_years", "fitments", (time.time() - start) * 1000)

    if not isinstance(result.data, list):
        return []
    return [cast(int, row["year"]) for row in result.data if isinstance(row, dict)]


async def load_csv_data(csv_path: str, batch_size: int = 500) -> int:
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

        def _insert_batch(b=batch):
            return client.table("fitments").insert(b).execute()

        await asyncio.to_thread(_insert_batch)
        total_inserted += len(batch)
        logger.info(f"Inserted {total_inserted}/{len(records)} records...")

    return len(records)


# -----------------------------------------------------------------------------
# Private helpers
# -----------------------------------------------------------------------------


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
