"""RAG service using Supabase for storage and full-text search."""

import hashlib
import json
import os
from collections.abc import Generator
from typing import Any, cast

import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

from supabase import Client, create_client

load_dotenv()

# OpenAI client for streaming (lazy loaded)
_openai_client: OpenAI | None = None


def _get_openai_client() -> OpenAI:
    """Get or create OpenAI client."""
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _openai_client


# Simple in-memory cache for parsed queries
_query_cache: dict[str, dict[str, Any]] = {}

# DSPy model instance (lazy loaded)
_dspy_assistant: Any = None

# Supabase client for Kansei queries (lazy loaded)
_kansei_supabase: Client | None = None


def _get_kansei_supabase() -> Client:
    """Get or create Supabase client for Kansei queries."""
    global _kansei_supabase
    if _kansei_supabase is None:
        _kansei_supabase = create_client(
            os.getenv("SUPABASE_URL", ""),
            os.getenv("SUPABASE_KEY", ""),
        )
    return _kansei_supabase


def find_matching_kansei_wheels(
    bolt_pattern: str,
    diameter: float | None = None,
    width: float | None = None,
    offset: int | None = None,
    offset_tolerance: int = 10,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Find Kansei wheels from Supabase that match the given specs."""
    supabase = _get_kansei_supabase()

    # Use the database function for efficient querying
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


def format_kansei_recommendations(
    bolt_pattern: str,
    fitment_specs: list[dict[str, Any]],
    offset_tolerance: int = 15,
) -> str:
    """Format Kansei wheel recommendations based on fitment specs."""
    all_matches: dict[str, dict[str, Any]] = {}  # Use dict to dedupe by model+size

    for spec in fitment_specs:
        metadata = spec.get("metadata", {})
        front_diameter = metadata.get("front_diameter")
        front_width = metadata.get("front_width")
        front_offset = metadata.get("front_offset")

        # Find matching Kansei wheels for this spec
        matches = find_matching_kansei_wheels(
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
        # Try broader search with just bolt pattern
        broader_matches = find_matching_kansei_wheels(bolt_pattern=bolt_pattern)
        if broader_matches:
            # Group by model and show available sizes
            broader_models: dict[str, list[dict[str, Any]]] = {}
            for w in broader_matches[:20]:  # Limit to 20
                model_name = w.get("model", "Unknown")
                if model_name not in broader_models:
                    broader_models[model_name] = []
                broader_models[model_name].append(w)

            lines = ["\n**KANSEI WHEELS AVAILABLE FOR YOUR BOLT PATTERN:**"]
            for model_name, wheels in list(broader_models.items())[:5]:  # Top 5 models
                wheel = wheels[0]
                url = wheel.get("url", "")
                sizes = set(
                    f"{int(w['diameter'])}x{w['width']} +{w.get('wheel_offset', 0)}"
                    for w in wheels
                )
                if url:
                    lines.append(
                        f"- [**{model_name}**]({url}): {', '.join(sorted(sizes)[:4])}"
                    )
                else:
                    lines.append(f"- **{model_name}**: {', '.join(sorted(sizes)[:4])}")
            lines.append(
                "\n*Note: Check offset compatibility with your desired fitment.*"
            )
            return "\n".join(lines)
        return "\n**KANSEI WHEELS:** No exact matches found for your bolt pattern."

    # Format the matches
    lines = ["\n**KANSEI WHEELS THAT FIT:**"]

    # Group by model
    grouped_models: dict[str, list[dict[str, Any]]] = {}
    for wheel in all_matches.values():
        model_name = wheel.get("model", "Unknown")
        if model_name not in grouped_models:
            grouped_models[model_name] = []
        grouped_models[model_name].append(wheel)

    for model_name, wheels in list(grouped_models.items())[:5]:  # Top 5 models
        wheel = wheels[0]  # Show first variant
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


def safe_float(val: Any) -> float:
    """Safely convert a value to float."""
    try:
        return float(val) if val != "" else 0.0
    except (ValueError, TypeError):
        return 0.0


def safe_int(val: Any) -> int:
    """Safely convert a value to int."""
    try:
        return int(float(val)) if val != "" else 0
    except (ValueError, TypeError):
        return 0


def determine_fitment_setup(row: dict[str, Any]) -> str:
    """Determine if fitment is square or staggered."""
    front_width = safe_float(row.get("front_width"))
    rear_width = safe_float(row.get("rear_width"))
    front_diameter = safe_float(row.get("front_diameter"))
    rear_diameter = safe_float(row.get("rear_diameter"))
    front_offset = safe_float(row.get("front_offset"))
    rear_offset = safe_float(row.get("rear_offset"))

    if (
        front_width == rear_width
        and front_diameter == rear_diameter
        and front_offset == rear_offset
    ):
        return "square"
    return "staggered"


def determine_fitment_style(row: dict[str, Any]) -> str:
    """Determine fitment style based on offset and width."""
    front_offset = safe_float(row.get("front_offset"))
    rear_offset = safe_float(row.get("rear_offset"))
    front_width = safe_float(row.get("front_width"))
    rear_width = safe_float(row.get("rear_width"))

    avg_offset = (front_offset + rear_offset) / 2
    avg_width = (front_width + rear_width) / 2

    if avg_offset < 15 and avg_width >= 9:
        return "aggressive"
    elif avg_offset < 25:
        return "flush"
    elif avg_offset >= 40:
        return "tucked"
    else:
        return "flush"


def has_poke(row: dict[str, Any]) -> bool:
    """Determine if wheels poke past fender."""
    front_offset = safe_float(row.get("front_offset"))
    rear_offset = safe_float(row.get("rear_offset"))
    return front_offset < 20 or rear_offset < 20


def needs_modifications(row: dict[str, Any]) -> bool:
    """Check if fitment requires modifications."""
    rubbing = str(row.get("rubbing", "")).lower()
    trimming = str(row.get("trimming", "")).lower()
    front_spacers = str(row.get("front_wheel_spacers", "")).lower()
    rear_spacers = str(row.get("rear_wheel_spacers", "")).lower()

    has_rubbing = "rub" in rubbing and "no rub" not in rubbing
    needs_trimming = "no" not in trimming and trimming != ""
    has_spacers = front_spacers not in ["none", ""] or rear_spacers not in ["none", ""]

    return has_rubbing or needs_trimming or has_spacers


class RAGService:
    # Database context - precomputed stats about available data
    DB_CONTEXT = """
DATABASE COVERAGE:
- Total fitment records: 54,570
- Year range: 1991-2026 (strongest coverage: 2003-2019)
- Top makes by record count: Honda (8,027), Subaru (7,367), Volkswagen (4,576), Ford (4,011), Toyota (3,191), Nissan (3,009), Mazda (2,780), BMW (2,722), INFINITI (2,517), Hyundai (2,499)
- Fitment styles: mostly flush, some aggressive and tucked
- Fitment setups: mostly square, some staggered

IMPORTANT NOTES:
- No data for vehicles before 1991
- Limited data for 2023+ vehicles (newer cars)
- BMW M3 data covers: 1995-1999, 2001-2006, 2008-2013, 2015-2018, 2020-2025 (no E30 1986-1991)
- When showing data from different years, explain that specs may vary but provide the data as a helpful reference
"""

    # Bolt patterns by make - these are defaults, model-specific logic in _get_bolt_pattern
    # Center bores included for reference
    BOLT_PATTERNS: dict[str, str | list[tuple[int, int, str]]] = {
        # Japanese makes
        "honda": "5x114.3",  # 10th gen Civic (2016+), Accord, etc. Center bore: 64.1mm
        "acura": "5x114.3",  # Center bore: 64.1mm
        "toyota": "5x114.3",  # Most modern Toyotas. Center bore: 60.1mm
        "lexus": "5x114.3",  # Center bore: 60.1mm
        "nissan": "5x114.3",  # Center bore: 66.1mm
        "datsun": "4x114.3",  # Classic 240Z, 280Z. Center bore: 66.1mm
        "infiniti": "5x114.3",  # Center bore: 66.1mm
        "mazda": "5x114.3",  # Most models (Miata is 4x100). Center bore: 67.1mm
        "subaru": "5x114.3",  # 2015+ WRX/STI. Center bore: 56.1mm
        "mitsubishi": "5x114.3",  # Center bore: 67.1mm
        # Korean makes
        "hyundai": "5x114.3",  # Center bore: 67.1mm
        "kia": "5x114.3",  # Center bore: 67.1mm
        "genesis": "5x114.3",  # Center bore: 67.1mm
        # American makes
        "ford": "5x114.3",  # Mustang, Focus, etc. Center bore: 70.5mm (Mustang: 67.1mm)
        "chevrolet": "5x120",  # Camaro. Center bore: 67.1mm. Trucks are 6x139.7
        "dodge": "5x115",  # Challenger/Charger. Center bore: 71.5mm
        # German makes - complex, handled in _get_bolt_pattern
        "bmw": "5x120",  # Default, but G-series (2019+) is 5x112. Center bore: 72.6mm
        "mini": "5x112",  # F-series (2014+). Center bore: 56.1mm
        "volkswagen": "5x112",  # MK5+ Golf. Center bore: 57.1mm
        "audi": "5x112",  # Center bore: 57.1mm (66.5mm on some)
        "mercedes-benz": "5x112",  # Center bore: 66.6mm
        "porsche": "5x130",  # Center bore: 71.6mm
        # Electric
        "tesla": "5x114.3",  # Model 3/Y. Center bore: 64.1mm. S/X are 5x120
    }

    # Center bore by make (mm) - important for hub-centric fit
    CENTER_BORES: dict[str, float] = {
        "honda": 64.1,
        "acura": 64.1,
        "toyota": 60.1,
        "lexus": 60.1,
        "nissan": 66.1,
        "infiniti": 66.1,
        "mazda": 67.1,
        "subaru": 56.1,
        "mitsubishi": 67.1,
        "hyundai": 67.1,
        "kia": 67.1,
        "genesis": 67.1,
        "ford": 70.5,
        "chevrolet": 67.1,
        "dodge": 71.5,
        "bmw": 72.6,
        "mini": 56.1,
        "volkswagen": 57.1,
        "audi": 57.1,
        "mercedes-benz": 66.6,
        "porsche": 71.6,
        "tesla": 64.1,
    }

    def __init__(self, use_dspy: bool = True) -> None:
        self.supabase: Client = create_client(
            os.getenv("SUPABASE_URL", ""),
            os.getenv("SUPABASE_KEY", ""),
        )
        self.use_dspy = use_dspy
        self._init_dspy()

    def _init_dspy(self) -> None:
        """Initialize DSPy with OpenAI."""
        global _dspy_assistant
        if _dspy_assistant is None and self.use_dspy:
            from .dspy_fitment import create_fitment_assistant

            _dspy_assistant = create_fitment_assistant("openai/gpt-4o-mini")

    # BMW chassis codes and their bolt patterns
    # E/F series = 5x120, G series (2019+) = 5x112
    # Exception: E21/E30 small cars = 4x100
    BMW_4x100_MODELS = {"2002", "1600", "1602", "1802", "2000", "2002tii", "e21", "e30"}
    BMW_5x112_MODELS = {
        "g20",
        "g21",
        "g22",
        "g23",
        "g26",
        "g80",
        "g81",
        "g82",
        "g83",
        "g42",
        "g87",
    }

    # Mazda Miata uses 4x100 (all generations)
    MAZDA_4x100_MODELS = {"miata", "mx-5", "mx5", "roadster"}

    # Subaru models with 5x100 (older WRX/STI, BRZ, etc.)
    SUBARU_5x100_MODELS = {"brz", "frs", "fr-s", "86", "gt86"}

    def _validate_vehicle_exists(
        self,
        original_query: str,
        make: str | None = None,
        model: str | None = None,
        year: int | None = None,
        trim: str | None = None,
    ) -> dict[str, Any]:
        """
        Use LLM to validate if a vehicle combination actually exists.
        Uses the original query for better accuracy since parsed values may be wrong.
        Returns {"valid": bool, "reason": str, "suggestion": str | None}
        """
        if not original_query.strip():
            return {
                "valid": True,
                "reason": "No vehicle info",
                "suggestion": None,
            }

        client = _get_openai_client()

        # Use original query - parsing can misinterpret (e.g., "e30 m5" -> "5 Series")
        vehicle_str = original_query.strip()

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": """You are a vehicle expert. Determine if the vehicle mentioned in the query actually exists/existed.

The query may include extra words like "wheels", "fitment", "aggressive", "flush" - IGNORE these and focus only on the vehicle (year, make, model, chassis code).

Return ONLY a JSON object:
{"valid": true/false, "reason": "brief explanation", "suggestion": "correct vehicle if invalid, else null"}

Examples:
- "e30 m5 wheels" -> {"valid": false, "reason": "The E30 chassis never had an M5. The E30 only had the M3.", "suggestion": "BMW E30 M3 or BMW E28 M5"}
- "e30 m3 aggressive fitment" -> {"valid": true, "reason": "The BMW E30 M3 was produced 1986-1991", "suggestion": null}
- "2020 Honda Civic flush" -> {"valid": true, "reason": "The 2020 Honda Civic exists", "suggestion": null}
- "Toyota Supra MK4" -> {"valid": true, "reason": "The MK4 Supra (A80) was produced 1993-2002", "suggestion": null}
- "Ford Mustang Hellcat" -> {"valid": false, "reason": "Hellcat is a Dodge engine/trim, not Ford", "suggestion": "Ford Mustang GT or Dodge Challenger Hellcat"}
- "e36 m5" -> {"valid": false, "reason": "The E36 chassis only had the M3, never the M5", "suggestion": "BMW E36 M3 or BMW E34 M5"}

Be strict - if a specific chassis code + model combination never existed, mark it invalid.""",
                    },
                    {
                        "role": "user",
                        "content": f"Does this vehicle exist? {vehicle_str}",
                    },
                ],
                max_tokens=150,
                temperature=0,
            )

            content = response.choices[0].message.content or ""
            # Parse JSON response
            import re

            json_match = re.search(r"\{[^}]+\}", content)
            if json_match:
                result = json.loads(json_match.group())
                return {
                    "valid": result.get("valid", True),
                    "reason": result.get("reason", ""),
                    "suggestion": result.get("suggestion"),
                }
        except Exception:
            pass

        # Default to valid if LLM fails
        return {"valid": True, "reason": "Could not validate", "suggestion": None}

    def _get_vehicle_specs_from_llm(
        self, make: str, year: int | None, model: str
    ) -> dict[str, Any] | None:
        """
        Get OEM specs for a vehicle using LLM knowledge.
        More reliable than web scraping.
        """
        client = _get_openai_client()

        vehicle_str = f"{year} {make} {model}" if year else f"{make} {model}"

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": """You are a vehicle specifications expert. Return ONLY a JSON object with wheel specs.
Be precise - bolt patterns changed across generations (e.g., BMW G-series uses 5x112, F-series uses 5x120).

Return format:
{"bolt_pattern": "5x114.3", "center_bore": 64.1, "stud_size": "M12x1.5"}

Rules:
- bolt_pattern: format as "5x114.3" (lugs x PCD in mm)
- center_bore: in mm (e.g., 64.1, 72.6, 56.1)
- stud_size: format as "M12x1.5" or "M14x1.5"
- If unsure, return null for that field
- Return ONLY valid JSON, no explanation""",
                    },
                    {
                        "role": "user",
                        "content": f"What are the wheel specs for a {vehicle_str}?",
                    },
                ],
                max_tokens=100,
                temperature=0,  # Deterministic for factual data
            )

            content = response.choices[0].message.content or ""
            # Parse JSON response
            import re

            json_match = re.search(r"\{[^}]+\}", content)
            if json_match:
                return json.loads(json_match.group())
            return None
        except Exception:
            return None

    def _get_bolt_pattern(
        self, make: str | None, year: int | None = None, model: str | None = None
    ) -> str:
        """
        Get bolt pattern for a vehicle.

        Priority:
        1. Hardcoded patterns for known special cases (most reliable)
        2. Dynamic lookup from wheel-size.com (can be unreliable)
        3. Default patterns by make
        """
        if not make:
            return "Unknown"

        make_lower = make.lower()
        model_lower = (model or "").lower().replace("-", "").replace(" ", "")

        # BMW - complex logic based on chassis generation
        if make_lower == "bmw":
            # Check for G-series chassis codes = 5x112
            for g_chassis in self.BMW_5x112_MODELS:
                if g_chassis in model_lower:
                    return "5x112"
            # G-series by year (if no chassis code specified)
            # M3/M4 G80/G82 started 2021
            if year and year >= 2021:
                if any(m in model_lower for m in ["m3", "m4"]):
                    return "5x112"
            # 3/4 series G20/G22 started 2019
            if year and year >= 2019:
                if any(
                    m in model_lower
                    for m in ["3series", "4series", "330", "340", "430", "440"]
                ):
                    return "5x112"
            # 5/7 series G30/G11 started 2017 - still 5x112
            if year and year >= 2017:
                if any(
                    m in model_lower
                    for m in ["5series", "7series", "530", "540", "550", "740", "750"]
                ):
                    return "5x112"
            # Check for old small BMWs (4x100)
            for small_model in self.BMW_4x100_MODELS:
                if small_model in model_lower:
                    return "4x100"
            # E30 M3 specifically
            if "m3" in model_lower and year and year <= 1991:
                return "4x100"
            # Default BMW = 5x120 (E/F series, pre-G series)
            return "5x120"

        # Mazda - Miata is 4x100
        if make_lower == "mazda":
            for miata_name in self.MAZDA_4x100_MODELS:
                if miata_name in model_lower:
                    return "4x100"
            return "5x114.3"

        # Subaru - BRZ/86 and older WRX are 5x100
        if make_lower == "subaru":
            for model_5x100 in self.SUBARU_5x100_MODELS:
                if model_5x100 in model_lower:
                    return "5x100"
            # Pre-2015 WRX/STI were 5x100
            if (
                year
                and year < 2015
                and any(m in model_lower for m in ["wrx", "sti", "impreza"])
            ):
                return "5x100"
            return "5x114.3"

        # Toyota - special cases
        if make_lower == "toyota":
            # GR86/86 is 5x100
            if any(m in model_lower for m in ["86", "gt86", "gr86"]):
                return "5x100"
            # Supra (A90) uses BMW platform = 5x112
            if "supra" in model_lower and year and year >= 2019:
                return "5x112"
            return "5x114.3"

        # Scion FR-S is 5x100
        if make_lower == "scion":
            if "frs" in model_lower or "fr-s" in model_lower:
                return "5x100"
            return "5x114.3"

        # Honda - pre-2001 Civic was 4x100
        if make_lower == "honda":
            if "civic" in model_lower and year and year <= 2000:
                return "4x100"
            return "5x114.3"

        # Acura - NSX uses 5x120
        if make_lower == "acura":
            if "nsx" in model_lower:
                return "5x120"
            return "5x114.3"

        # Tesla - Model S/X are 5x120, Model 3/Y are 5x114.3
        if make_lower == "tesla":
            if any(
                m in model_lower for m in ["model s", "models", "model x", "modelx"]
            ):
                return "5x120"
            return "5x114.3"

        # Ford - trucks and Focus RS have different patterns
        if make_lower == "ford":
            # F-150, F-250, F-350 trucks = 6x135
            if any(
                m in model_lower
                for m in ["f150", "f-150", "f250", "f-250", "f350", "f-350"]
            ):
                return "6x135"
            # Focus RS uses 5x108
            if "focus" in model_lower and "rs" in model_lower:
                return "5x108"
            return "5x114.3"

        # Chevrolet - trucks vs cars
        if make_lower == "chevrolet":
            # Silverado, Colorado, Tahoe, Suburban = 6x139.7
            if any(
                m in model_lower for m in ["silverado", "colorado", "tahoe", "suburban"]
            ):
                return "6x139.7"
            # Camaro, Corvette = 5x120
            return "5x120"

        # Default lookup from BOLT_PATTERNS
        pattern_data = self.BOLT_PATTERNS.get(make_lower)
        if pattern_data is None:
            return "Unknown"

        if isinstance(pattern_data, str):
            return pattern_data

        # List of year ranges
        if year:
            for start_year, end_year, pattern in pattern_data:
                if start_year <= year <= end_year:
                    return pattern

        # Return most recent pattern
        if pattern_data:
            return pattern_data[-1][2]

        return "Unknown"

    def _get_center_bore(
        self, make: str | None, year: int | None = None, model: str | None = None
    ) -> float | None:
        """Get center bore for a vehicle."""
        if not make:
            return None

        # Fallback to hardcoded (LLM lookup is done together with bolt pattern if needed)
        return self.CENTER_BORES.get(make.lower())

    def parse_query(self, query: str) -> dict[str, Any]:
        """Use DSPy to extract year, make, model, and fitment style from natural language."""
        global _dspy_assistant

        # Check cache first
        cache_key = hashlib.md5(query.lower().strip().encode()).hexdigest()
        if cache_key in _query_cache:
            return _query_cache[cache_key]

        # Use DSPy's parse_query module
        if self.use_dspy and _dspy_assistant:
            try:
                parsed = _dspy_assistant.parse_query(query=query)

                # Strip quotes that DSPy sometimes adds to string outputs
                def clean_str(val: Any) -> str | None:
                    if val is None or val == "None":
                        return None
                    if isinstance(val, str):
                        return val.strip("\"'")
                    return str(val)

                result = {
                    "year": parsed.year
                    if parsed.year and parsed.year != "None"
                    else None,
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

    def _fitment_to_text(self, row: dict[str, Any]) -> str:
        """Convert a fitment row to searchable text."""
        setup = determine_fitment_setup(row)
        style = determine_fitment_style(row)
        poke = "poke" if has_poke(row) else "no poke"
        mods = (
            "requires modifications"
            if needs_modifications(row)
            else "no modifications needed"
        )

        parts = [
            f"{row.get('year', '')} {row.get('make', '')} {row.get('model', '')}",
            f"Setup: {setup} {style} fitment {poke}",
            f"Wheels: {row.get('wheel_brand', '')} {row.get('wheel_model', '')}",
            f"Front wheel: {row.get('front_diameter', '')}x{row.get('front_width', '')} ET{row.get('front_offset', '')} backspacing {row.get('front_backspacing', '')}",
            f"Rear wheel: {row.get('rear_diameter', '')}x{row.get('rear_width', '')} ET{row.get('rear_offset', '')} backspacing {row.get('rear_backspacing', '')}",
            f"Tires: {row.get('tire_brand', '')} {row.get('tire_model', '')}",
            f"Front tire: {row.get('front_tire_width', '')}/{row.get('front_tire_aspect', '')}R{row.get('front_tire_diameter', '')}",
            f"Rear tire: {row.get('rear_tire_width', '')}/{row.get('rear_tire_aspect', '')}R{row.get('rear_tire_diameter', '')}",
            f"Rubbing: {row.get('rubbing', '')}",
            f"Trimming: {row.get('trimming', '')}",
            f"Spacers: Front {row.get('front_wheel_spacers', '')}, Rear {row.get('rear_wheel_spacers', '')}",
            f"Suspension: {row.get('suspension_type', '')}",
            f"Modifications: {mods}",
        ]
        return " | ".join(parts)

    def load_csv_data(self, csv_path: str, batch_size: int = 500) -> int:
        """Load fitment data from CSV into Supabase."""
        df = pd.read_csv(csv_path)
        df = df.fillna("")

        records: list[dict[str, Any]] = []

        for _, row in df.iterrows():
            row_dict = row.to_dict()
            doc_text = self._fitment_to_text(row_dict)
            setup = determine_fitment_setup(row_dict)
            style = determine_fitment_style(row_dict)

            # Build tire strings
            tire_front = f"{row.get('front_tire_width', '')}/{row.get('front_tire_aspect', '')}R{row.get('front_tire_diameter', '')}"
            tire_rear = f"{row.get('rear_tire_width', '')}/{row.get('rear_tire_aspect', '')}R{row.get('rear_tire_diameter', '')}"

            record = {
                "year": safe_int(row.get("year")),
                "make": str(row.get("make", "")),
                "model": str(row.get("model", "")),
                "front_diameter": safe_float(row.get("front_diameter")),
                "front_width": safe_float(row.get("front_width")),
                "front_offset": safe_int(row.get("front_offset")),
                "front_backspacing": safe_float(row.get("front_backspacing")),
                "front_spacer": safe_float(
                    row.get("front_wheel_spacers")
                    if str(row.get("front_wheel_spacers", ""))
                    .replace(".", "")
                    .isdigit()
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
                "has_poke": has_poke(row_dict),
                "needs_mods": needs_modifications(row_dict),
                "notes": f"Rubbing: {row.get('rubbing', '')} | Trimming: {row.get('trimming', '')} | Suspension: {row.get('suspension_type', '')}",
                "document": doc_text,
            }
            records.append(record)

        # Insert in batches
        total_inserted = 0
        for i in range(0, len(records), batch_size):
            batch = records[i : i + batch_size]
            self.supabase.table("fitments").insert(batch).execute()
            total_inserted += len(batch)
            print(f"Inserted {total_inserted}/{len(records)} records...")

        return len(records)

    def search(
        self,
        query: str,
        year: int | None = None,
        make: str | None = None,
        model: str | None = None,
        fitment_setup: str | None = None,
        fitment_style: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Search for relevant fitment data using full-text search."""
        # Use the RPC function for full-text search
        result = self.supabase.rpc(
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
                    fitments.append(
                        {
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
                    )

        return fitments

    def find_similar_vehicles(
        self,
        make: str | None,
        model: str | None,
        year: int | None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Find fitments from similar vehicles when exact match not found."""
        similar_results: list[dict[str, Any]] = []

        # Strategy 1: Same make, different years of same model
        if make and model:
            result = (
                self.supabase.table("fitments")
                .select(
                    "year, make, model, document, front_diameter, front_width, front_offset, "
                    "rear_diameter, rear_width, rear_offset, fitment_setup, fitment_style, "
                    "has_poke, needs_mods"
                )
                .eq("make", make)
                .ilike("model", f"%{model}%")
                .limit(limit)
                .execute()
            )

            if result.data and isinstance(result.data, list):
                for row in result.data:
                    if not isinstance(row, dict):
                        continue
                    similar_results.append(
                        {
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
                            "is_similar": True,
                            "similarity_reason": "Same model, different year",
                        }
                    )

        # Strategy 2: Same make, similar model class (if still not enough)
        if len(similar_results) < limit and make:
            # Get other models from same make
            result = (
                self.supabase.table("fitments")
                .select(
                    "year, make, model, document, front_diameter, front_width, front_offset, "
                    "rear_diameter, rear_width, rear_offset, fitment_setup, fitment_style, "
                    "has_poke, needs_mods"
                )
                .eq("make", make)
                .limit(limit - len(similar_results))
                .execute()
            )

            if result.data and isinstance(result.data, list):
                for row in result.data:
                    if not isinstance(row, dict):
                        continue
                    # Skip if we already have this exact vehicle
                    if any(
                        r["metadata"]["model"] == row.get("model")
                        and r["metadata"]["year"] == row.get("year")
                        for r in similar_results
                    ):
                        continue
                    similar_results.append(
                        {
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
                            "is_similar": True,
                            "similarity_reason": f"Same make ({make}), different model",
                        }
                    )

        return similar_results[:limit]

    def save_pending_fitment(
        self,
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
                self.supabase.table("fitments_pending")
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
                    return None
        except Exception:
            pass  # Don't fail the main request if pending save fails
        return None

    def ask(
        self,
        query: str,
        year: int | None = None,
        make: str | None = None,
        model: str | None = None,
        fitment_setup: str | None = None,
        fitment_style: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        """Answer a question using RAG with DSPy."""
        global _dspy_assistant

        # Quick parse to get make/model for search (use cached if available)
        parsed: dict[str, Any] = {}
        if not any([year, make, model, fitment_style]):
            parsed = self.parse_query(query)
            year = parsed.get("year") or year
            make = parsed.get("make") or make
            model = parsed.get("model") or model
            fitment_style = parsed.get("fitment_style") or fitment_style

        # Build search query and get results
        search_query_parts = [p for p in [make, model] if p]
        search_query = " ".join(search_query_parts) if search_query_parts else query

        # Track data source type for response
        data_source = "exact"  # exact, similar, or llm_knowledge

        search_results = self.search(
            search_query, year, make, model, fitment_setup, fitment_style, limit
        )

        # Fallback 1: Broader search without year/style filters
        if not search_results and (year or fitment_style):
            search_results = self.search(
                search_query, None, make, model, fitment_setup, None, limit
            )
            if search_results:
                data_source = "exact"  # Still exact make/model, just different year

        # Fallback 2: Similar vehicles
        if not search_results and make:
            search_results = self.find_similar_vehicles(make, model, year, limit)
            if search_results:
                data_source = "similar"

        # Fallback 3: LLM knowledge (no DB data at all)
        if not search_results:
            data_source = "llm_knowledge"

        # Get bolt pattern (year and model-aware for older vehicles)
        bolt_pattern = self._get_bolt_pattern(make, year, model)

        # Build fitment data context with source info
        if data_source == "exact":
            context = "\n\n".join(
                [
                    f"Fitment {i + 1}:\n{r['document']}"
                    for i, r in enumerate(search_results)
                ]
            )
        elif data_source == "similar":
            context_parts = []
            for i, r in enumerate(search_results):
                reason = r.get("similarity_reason", "Similar vehicle")
                context_parts.append(
                    f"REFERENCE Fitment {i + 1} ({reason}):\n{r['document']}"
                )
            context = "\n\n".join(context_parts)
        else:
            context = ""

        # Get matching Kansei wheels
        kansei_recommendations = format_kansei_recommendations(
            bolt_pattern=bolt_pattern,
            fitment_specs=search_results,
            offset_tolerance=15,
        )

        # Get center bore
        center_bore = self._get_center_bore(make, year, model)
        center_bore_str = f"{center_bore}mm" if center_bore else "check vehicle specs"

        # Build data context description for DSPy
        if data_source == "exact":
            data_description = f"""Bolt Pattern: {bolt_pattern}
Center Bore: {center_bore_str}

COMMUNITY FITMENT DATA (use specs for reference only, DO NOT recommend these wheel brands):
{context if context else "(No community fitment records)"}"""
        elif data_source == "similar":
            data_description = f"""Bolt Pattern: {bolt_pattern}
Center Bore: {center_bore_str}

REFERENCE DATA (from similar vehicles - use specs for reference only, DO NOT recommend these wheel brands):
{context}"""
        else:
            data_description = f"""Bolt Pattern: {bolt_pattern}
Center Bore: {center_bore_str}

(No fitment data in database)
Only recommend Kansei wheels from the KANSEI WHEELS section below."""

        # Add Kansei wheel info to the context
        if kansei_recommendations:
            data_description += f"\n\n{kansei_recommendations}"

        # Use DSPy for response generation
        if self.use_dspy and _dspy_assistant:
            result = _dspy_assistant(
                query=query,
                fitment_data=data_description,
                bolt_pattern=bolt_pattern,
                year=year,
                make=make,
                model=model,
                trim=parsed.get("trim"),
                fitment_style=fitment_style,
            )

            # Append Kansei recommendations to the answer if not already included
            answer = result.response
            if kansei_recommendations and "KANSEI" not in answer.upper():
                answer += f"\n\n{kansei_recommendations}"

            # Auto-save LLM-generated fitment for future reference
            pending_id = None
            if data_source == "llm_knowledge":
                pending_id = self.save_pending_fitment(
                    year=year,
                    make=make,
                    model=model,
                    trim=parsed.get("trim"),
                    fitment_style=fitment_style,
                    bolt_pattern=bolt_pattern,
                    notes=f"Query: {query}",
                )

            return {
                "answer": answer,
                "sources": search_results,
                "parsed": result.parsed,
                "needs_clarification": result.needs_clarification,
                "data_source": data_source,
                "pending_fitment_id": pending_id,
                "kansei_matches": find_matching_kansei_wheels(bolt_pattern)
                if bolt_pattern != "Unknown"
                else [],
            }

        # Fallback to simple response if DSPy not available
        answer_text = "DSPy not initialized. Please check configuration."

        return {
            "answer": answer_text,
            "sources": search_results,
            "parsed": {
                "year": year,
                "make": make,
                "model": model,
                "trim": parsed.get("trim"),
                "fitment_style": fitment_style,
                "bolt_pattern": bolt_pattern,
            },
            "data_source": data_source,
        }

    def get_makes(self) -> list[str]:
        """Get all unique makes."""
        result = self.supabase.rpc("get_makes").execute()
        if not isinstance(result.data, list):
            return []
        return [cast(str, row["make"]) for row in result.data if isinstance(row, dict)]

    def get_models(self, make: str) -> list[str]:
        """Get all models for a make."""
        result = self.supabase.rpc("get_models", {"filter_make": make}).execute()
        if not isinstance(result.data, list):
            return []
        return [cast(str, row["model"]) for row in result.data if isinstance(row, dict)]

    def get_years(self) -> list[int]:
        """Get all unique years."""
        result = self.supabase.rpc("get_years").execute()
        if not isinstance(result.data, list):
            return []
        return [cast(int, row["year"]) for row in result.data if isinstance(row, dict)]

    def get_fitment_styles(self) -> list[str]:
        """Get all fitment styles."""
        return ["aggressive", "flush", "tucked"]

    def get_fitment_setups(self) -> list[str]:
        """Get all fitment setups."""
        return ["square", "staggered"]

    def ask_streaming(
        self,
        query: str,
        year: int | None = None,
        make: str | None = None,
        model: str | None = None,
        fitment_setup: str | None = None,
        fitment_style: str | None = None,
        limit: int = 10,
    ) -> Generator[str, None, dict[str, Any]]:
        """
        Streaming version of ask() - yields SSE events as they come in.
        Returns metadata dict at the end.
        """
        # Parse query to get vehicle info
        parsed: dict[str, Any] = {}
        if not any([year, make, model, fitment_style]):
            parsed = self.parse_query(query)
            year = parsed.get("year") or year
            make = parsed.get("make") or make
            model = parsed.get("model") or model
            fitment_style = parsed.get("fitment_style") or fitment_style

        # Validate vehicle exists (catches invalid combinations like E30 M5)
        trim = parsed.get("trim")
        validation = self._validate_vehicle_exists(query, make, model, year, trim)

        if not validation.get("valid", True):
            # Vehicle doesn't exist - return early with error message
            import uuid

            message_id = f"msg_{uuid.uuid4().hex}"

            error_msg = "**Vehicle Not Found**\n\n"
            error_msg += "The vehicle you specified doesn't appear to exist: "
            error_msg += f"{str(year) + ' ' if year else ''}{make or ''} {model or ''}"
            if trim:
                error_msg += f" ({trim})"
            error_msg += f"\n\n**Reason:** {validation.get('reason', 'Invalid vehicle combination')}"

            if validation.get("suggestion"):
                error_msg += f"\n\n**Did you mean:** {validation['suggestion']}"

            error_msg += "\n\nPlease check your vehicle information and try again."

            yield f"data: {json.dumps({'type': 'start', 'messageId': message_id})}\n\n"
            yield f"data: {json.dumps({'type': 'text-start', 'id': message_id})}\n\n"
            yield f"data: {json.dumps({'type': 'text-delta', 'id': message_id, 'delta': error_msg})}\n\n"
            yield f"data: {json.dumps({'type': 'text-end', 'id': message_id})}\n\n"
            yield f"data: {json.dumps({'type': 'finish', 'finishReason': 'stop'})}\n\n"
            yield "data: [DONE]\n\n"
            return {
                "answer": error_msg,
                "sources": [],
                "parsed": parsed,
                "data_source": "invalid_vehicle",
                "validation": validation,
            }

        # Build search query and get results
        search_query_parts = [p for p in [make, model] if p]
        search_query = " ".join(search_query_parts) if search_query_parts else query

        data_source = "exact"
        search_results = self.search(
            search_query, year, make, model, fitment_setup, fitment_style, limit
        )

        # Fallback chain
        if not search_results and (year or fitment_style):
            search_results = self.search(
                search_query, None, make, model, fitment_setup, None, limit
            )

        if not search_results and make:
            search_results = self.find_similar_vehicles(make, model, year, limit)
            if search_results:
                data_source = "similar"

        if not search_results:
            data_source = "llm_knowledge"

        # Get bolt pattern (year and model-aware)
        bolt_pattern = self._get_bolt_pattern(make, year, model)

        # Build context
        if data_source == "exact":
            context = "\n\n".join(
                [
                    f"Fitment {i + 1}:\n{r['document']}"
                    for i, r in enumerate(search_results)
                ]
            )
        elif data_source == "similar":
            context_parts = []
            for i, r in enumerate(search_results):
                reason = r.get("similarity_reason", "Similar vehicle")
                context_parts.append(
                    f"REFERENCE Fitment {i + 1} ({reason}):\n{r['document']}"
                )
            context = "\n\n".join(context_parts)
        else:
            context = ""

        # Get Kansei recommendations
        kansei_recommendations = format_kansei_recommendations(
            bolt_pattern=bolt_pattern,
            fitment_specs=search_results,
            offset_tolerance=15,
        )

        # Build prompt for OpenAI
        vehicle_info = f"{year or ''} {make or ''} {model or ''}".strip()
        year_note = "" if year else " (year not specified - do NOT make up a year)"
        center_bore = self._get_center_bore(make, year, model)
        center_bore_str = f"{center_bore}mm" if center_bore else "check vehicle specs"

        system_prompt = f"""You are a Kansei Wheels sales assistant. Your ONLY job is to recommend Kansei brand wheels.

**FORMAT YOUR RESPONSE LIKE THIS:**

**[VEHICLE]{year_note}**
Bolt Pattern: [pattern]
Center Bore: [bore]

**VERIFIED COMMUNITY SETUPS:**
[List wheel/tire specs from the FITMENT DATA provided - these show what sizes work on this vehicle]

**KANSEI WHEELS THAT FIT:**
[ONLY list wheels from the KANSEI WHEELS section - include model, size, offset, and price]

**Recommendation:** [Recommend a specific Kansei wheel based on the user's fitment style preference]

*Disclaimer: Verify fitment with a professional before purchase.*

CRITICAL RULES - YOU MUST FOLLOW THESE:
1. ONLY recommend Kansei wheels - NEVER mention competitor brands (JNC, TSW, SSR, Work, Enkei, etc.)
2. The FITMENT DATA shows community setups - use these specs to understand what sizes fit, but DO NOT recommend the wheel brands in that data
3. Match Kansei wheels to the specs shown in FITMENT DATA (diameter, width, offset range)
4. If no Kansei wheels match the bolt pattern, say so clearly
5. If no year was provided, do NOT make up a year
6. Never hallucinate Kansei models - only recommend wheels from the KANSEI WHEELS section
7. Include the Kansei product URL when available"""

        if data_source == "exact":
            user_content = f"""Query: {query}
Vehicle: {vehicle_info}
Bolt Pattern: {bolt_pattern}
Center Bore: {center_bore_str}

FITMENT DATA (community setups - use for reference specs only, DO NOT recommend these wheel brands):
{context}

{kansei_recommendations}"""
        elif data_source == "similar":
            user_content = f"""Query: {query}
Vehicle: {vehicle_info}
Bolt Pattern: {bolt_pattern}
Center Bore: {center_bore_str}

REFERENCE DATA (from similar vehicles - use for reference specs only, DO NOT recommend these wheel brands):
{context}

{kansei_recommendations}"""
        else:
            user_content = f"""Query: {query}
Vehicle: {vehicle_info}
Bolt Pattern: {bolt_pattern}
Center Bore: {center_bore_str}

No verified fitment data available. Only recommend Kansei wheels from the list below.

{kansei_recommendations if kansei_recommendations else "No Kansei wheels match this bolt pattern."}"""

        # Generate unique message ID for Vercel AI SDK protocol
        import uuid

        message_id = f"msg_{uuid.uuid4().hex}"

        # Send start event (Vercel AI SDK protocol)
        yield f"data: {json.dumps({'type': 'start', 'messageId': message_id})}\n\n"

        # Stream from OpenAI using Vercel AI SDK protocol
        client = _get_openai_client()
        stream = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            max_tokens=512,
            stream=True,
        )

        # Send text-start event
        yield f"data: {json.dumps({'type': 'text-start', 'id': message_id})}\n\n"

        full_response = ""
        for chunk in stream:
            if chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
                full_response += content
                # Yield text-delta event (Vercel AI SDK format)
                yield f"data: {json.dumps({'type': 'text-delta', 'id': message_id, 'delta': content})}\n\n"

        # Append Kansei recommendations if not already included
        if kansei_recommendations and "KANSEI" not in full_response.upper():
            yield f"data: {json.dumps({'type': 'text-delta', 'id': message_id, 'delta': '\\n\\n' + kansei_recommendations})}\n\n"
            full_response += "\n\n" + kansei_recommendations

        # Send text-end event
        yield f"data: {json.dumps({'type': 'text-end', 'id': message_id})}\n\n"

        # Auto-save LLM-generated fitment
        pending_id = None
        if data_source == "llm_knowledge":
            pending_id = self.save_pending_fitment(
                year=year,
                make=make,
                model=model,
                trim=parsed.get("trim"),
                fitment_style=fitment_style,
                bolt_pattern=bolt_pattern,
                notes=f"Query: {query}",
            )

        # Send custom data event with metadata (Vercel AI SDK data part)
        metadata = {
            "sources": search_results,
            "parsed": {
                "year": year,
                "make": make,
                "model": model,
                "trim": parsed.get("trim"),
                "fitment_style": fitment_style,
                "bolt_pattern": bolt_pattern,
            },
            "data_source": data_source,
            "pending_fitment_id": pending_id,
            "kansei_matches": find_matching_kansei_wheels(bolt_pattern)
            if bolt_pattern != "Unknown"
            else [],
        }
        yield f"data: {json.dumps({'type': 'data-metadata', 'data': metadata})}\n\n"

        # Send finish event and done marker
        yield f"data: {json.dumps({'type': 'finish'})}\n\n"
        yield "data: [DONE]\n\n"

        return metadata
