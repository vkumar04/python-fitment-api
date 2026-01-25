"""Vehicle context parsing from queries and conversation history."""

import hashlib
from typing import Any

# Simple in-memory cache for parsed queries
_query_cache: dict[str, dict[str, Any]] = {}

# DSPy assistant (lazy loaded externally)
_dspy_assistant: Any = None


def set_dspy_assistant(assistant: Any) -> None:
    """Set the DSPy assistant for query parsing."""
    global _dspy_assistant
    _dspy_assistant = assistant


def parse_query(query: str) -> dict[str, Any]:
    """Extract vehicle info from a natural language query using DSPy."""
    global _dspy_assistant

    cache_key = hashlib.md5(query.lower().strip().encode()).hexdigest()
    if cache_key in _query_cache:
        return _query_cache[cache_key]

    if _dspy_assistant:
        try:
            parsed = _dspy_assistant.parse_query(query=query)

            def clean_str(val: Any) -> str | None:
                if val is None or val == "None":
                    return None
                if isinstance(val, str):
                    return val.strip("\"'")
                return str(val)

            result = {
                "year": parsed.year if parsed.year and parsed.year != "None" else None,
                "make": clean_str(parsed.make),
                "model": clean_str(parsed.model),
                "trim": clean_str(parsed.trim),
                "fitment_style": clean_str(parsed.fitment_style),
            }
            _query_cache[cache_key] = result
            return result
        except Exception:
            pass

    return {
        "year": None,
        "make": None,
        "model": None,
        "trim": None,
        "fitment_style": None,
    }


def parse_vehicle_context(
    query: str,
    history: list[dict[str, str]] | None,
    year: int | None = None,
    make: str | None = None,
    model: str | None = None,
    fitment_style: str | None = None,
) -> dict[str, Any]:
    """Parse vehicle info from current query, falling back to history if needed."""
    current_parsed = parse_query(query)
    year = current_parsed.get("year") or year
    make = current_parsed.get("make") or make
    model = current_parsed.get("model") or model
    trim = current_parsed.get("trim")
    fitment_style = current_parsed.get("fitment_style") or fitment_style

    # Only use history if current query doesn't specify vehicle
    if history and not any([current_parsed.get("make"), current_parsed.get("model")]):
        for msg in reversed(history):
            if msg["role"] == "user":
                hist_parsed = parse_query(msg["content"])
                if hist_parsed.get("make") and not make:
                    make = hist_parsed.get("make")
                if hist_parsed.get("model") and not model:
                    model = hist_parsed.get("model")
                if hist_parsed.get("year") and not year:
                    year = hist_parsed.get("year")
                if hist_parsed.get("trim") and not trim:
                    trim = hist_parsed.get("trim")
                if hist_parsed.get("fitment_style") and not fitment_style:
                    fitment_style = hist_parsed.get("fitment_style")
                if make and model:
                    break

    return {
        "year": year,
        "make": make,
        "model": model,
        "trim": trim,
        "fitment_style": fitment_style,
    }


def validate_vehicle_specs(
    year: int | None,
    make: str | None,
    model: str | None,
    trim: str | None,
) -> dict[str, Any]:
    """Validate vehicle and return specs using DSPy."""
    global _dspy_assistant

    if _dspy_assistant:
        specs_result = _dspy_assistant.validate_specs(
            year=year, make=make, model=model, trim=trim
        )

        vehicle_exists = specs_result.vehicle_exists
        if isinstance(vehicle_exists, str):
            vehicle_exists = vehicle_exists.lower() == "true"

        return {
            "vehicle_exists": vehicle_exists,
            "invalid_reason": specs_result.invalid_reason
            if not vehicle_exists
            else None,
            "bolt_pattern": str(specs_result.bolt_pattern)
            if specs_result.bolt_pattern
            else "Unknown",
            "center_bore": float(specs_result.center_bore)
            if specs_result.center_bore
            else 0.0,
            "max_diameter": int(specs_result.max_wheel_diameter)
            if specs_result.max_wheel_diameter
            else 20,
            "width_range": str(specs_result.typical_width_range)
            if specs_result.typical_width_range
            else "7-9",
            "offset_range": str(specs_result.typical_offset_range)
            if specs_result.typical_offset_range
            else "+20 to +45",
        }

    # Fallback if DSPy not available
    return {
        "vehicle_exists": True,
        "invalid_reason": None,
        "bolt_pattern": "Unknown",
        "center_bore": 0.0,
        "max_diameter": 20,
        "width_range": "7-9",
        "offset_range": "+20 to +45",
    }
