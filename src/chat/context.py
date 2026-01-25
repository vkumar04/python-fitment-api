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
                    # Strip quotes and any DSPy metadata/notes
                    cleaned = val.strip("\"'")
                    # Remove any DSPy schema notes (e.g., "# note: ...")
                    if "#" in cleaned:
                        cleaned = cleaned.split("#")[0].strip()
                    return cleaned if cleaned else None
                return str(val)

            result = {
                "year": parsed.year if parsed.year and parsed.year != "None" else None,
                "make": clean_str(parsed.make),
                "model": clean_str(parsed.model),
                "trim": clean_str(parsed.trim),
                "fitment_style": clean_str(parsed.fitment_style),
                "suspension": clean_str(getattr(parsed, "suspension", None)),
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
        "suspension": None,
    }


def parse_vehicle_context(
    query: str,
    history: list[dict[str, str]] | None,
    year: int | None = None,
    make: str | None = None,
    model: str | None = None,
    fitment_style: str | None = None,
    suspension: str | None = None,
) -> dict[str, Any]:
    """Parse vehicle info from current query, falling back to history if needed."""
    current_parsed = parse_query(query)
    year = current_parsed.get("year") or year
    make = current_parsed.get("make") or make
    model = current_parsed.get("model") or model
    trim = current_parsed.get("trim")
    fitment_style = current_parsed.get("fitment_style") or fitment_style
    suspension = current_parsed.get("suspension") or suspension

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
                if hist_parsed.get("suspension") and not suspension:
                    suspension = hist_parsed.get("suspension")
                if make and model:
                    break

    return {
        "year": year,
        "make": make,
        "model": model,
        "trim": trim,
        "fitment_style": fitment_style,
        "suspension": suspension,
    }


# Vehicles where year significantly affects specs (bolt pattern changes, etc.)
YEAR_SENSITIVE_VEHICLES: dict[str, dict[str, list[str]]] = {
    "Honda": {
        "Prelude": ["1979-1987: 4x100", "1988-1991: 4x114.3", "1992-2001: 5x114.3"],
        "Accord": ["pre-1990: 4x100", "1990-1997: 4x114.3", "1998+: 5x114.3"],
        "Civic": ["pre-2006: 4x100", "2006+: 5x114.3"],
    },
    "Toyota": {
        "Supra": [
            "A70 (1986-1993): 5x114.3",
            "A80 (1993-2002): 5x114.3",
            "A90 (2019+): 5x112",
        ],
        "Celica": ["pre-1986: 4x114.3", "1986-1999: 5x100", "2000-2006: 5x100"],
    },
    "Nissan": {
        "240SX": ["S13 (1989-1994): 4x114.3", "S14 (1995-1998): 5x114.3"],
        "350Z": ["all years: 5x114.3"],
    },
    "Subaru": {
        "WRX": ["2001-2014: 5x100", "2015+: 5x114.3"],
        "Impreza": ["pre-2005: 5x100", "2005+: 5x100 or 5x114.3 depending on trim"],
    },
}

# BMW chassis codes - when user only provides chassis code, ask for specific year
BMW_CHASSIS_CODES: dict[str, dict[str, Any]] = {
    "E30": {
        "years": "1982-1994",
        "models": ["318i", "318is", "325i", "325is", "325e", "M3"],
        "bolt_pattern": "4x100",
    },
    "E36": {
        "years": "1992-1999",
        "models": ["318i", "323i", "325i", "328i", "M3"],
        "bolt_pattern": "5x120",
    },
    "E46": {
        "years": "1999-2006",
        "models": ["323i", "325i", "328i", "330i", "M3"],
        "bolt_pattern": "5x120",
    },
    "E90": {
        "years": "2006-2011",
        "models": ["325i", "328i", "330i", "335i", "M3"],
        "bolt_pattern": "5x120",
    },
    "E39": {
        "years": "1996-2003",
        "models": ["525i", "528i", "530i", "540i", "M5"],
        "bolt_pattern": "5x120",
    },
    "F30": {
        "years": "2012-2019",
        "models": ["320i", "328i", "330i", "335i", "340i"],
        "bolt_pattern": "5x120",
    },
    "G20": {
        "years": "2019+",
        "models": ["330i", "M340i"],
        "bolt_pattern": "5x112",
    },
}


def needs_year_clarification(make: str | None, model: str | None) -> str | None:
    """Check if this vehicle needs year clarification due to spec changes.

    Returns a message explaining the generations if clarification needed, None otherwise.
    """
    if not make or not model:
        return None

    make_vehicles = YEAR_SENSITIVE_VEHICLES.get(make)
    if not make_vehicles:
        return None

    # Check for exact model match or partial match
    for vehicle_model, generations in make_vehicles.items():
        if (
            model.lower() == vehicle_model.lower()
            or vehicle_model.lower() in model.lower()
        ):
            gen_info = "\n".join(f"  - {g}" for g in generations)
            return f"The {make} {model} had different specs across generations:\n{gen_info}\n\nWhat year is your {model}?"

    return None


def validate_vehicle_specs(
    year: int | None,
    make: str | None,
    model: str | None,
    trim: str | None,
) -> dict[str, Any]:
    """Validate vehicle and return specs using DSPy."""
    global _dspy_assistant

    # Check if we need year clarification first
    if year is None:
        clarification_msg = needs_year_clarification(make, model)
        if clarification_msg:
            return {
                "vehicle_exists": True,
                "needs_year": True,
                "year_clarification": clarification_msg,
                "invalid_reason": None,
                "bolt_pattern": "Unknown",
                "center_bore": 0.0,
                "max_diameter": 20,
                "width_range": "7-9",
                "offset_range": "+20 to +45",
            }

    if _dspy_assistant:
        specs_result = _dspy_assistant.validate_specs(
            year=year, make=make, model=model, trim=trim
        )

        vehicle_exists = specs_result.vehicle_exists
        if isinstance(vehicle_exists, str):
            vehicle_exists = vehicle_exists.lower() == "true"

        return {
            "vehicle_exists": vehicle_exists,
            "needs_year": False,
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
        "needs_year": False,
        "invalid_reason": None,
        "bolt_pattern": "Unknown",
        "center_bore": 0.0,
        "max_diameter": 20,
        "width_range": "7-9",
        "offset_range": "+20 to +45",
    }
