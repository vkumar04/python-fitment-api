"""RAG service using Supabase for storage and full-text search."""

import json
import os
from typing import Any, cast

import pandas as pd
from anthropic import Anthropic
from anthropic.types import TextBlock
from dotenv import load_dotenv

from supabase import Client, create_client

load_dotenv()


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
    def __init__(self) -> None:
        self.supabase: Client = create_client(
            os.getenv("SUPABASE_URL", ""),
            os.getenv("SUPABASE_KEY", ""),
        )
        self.anthropic = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    def parse_query(self, query: str) -> dict[str, Any]:
        """Use Claude to extract year, make, model, and fitment style from natural language."""
        response = self.anthropic.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=256,
            system="""Extract vehicle information from the user query. Return JSON only, no explanation.
If a field is not mentioned, use null. Be flexible with spelling/nicknames (e.g., "chevy" = "Chevrolet", "bimmer" = "BMW").

Return format:
{"year": number|null, "make": string|null, "model": string|null, "fitment_style": string|null}

Important rules:
- Chassis codes like E30, E36, E46, FK8, GD, etc. are NOT the model name. Extract the actual model (e.g., "E30 M3" -> model is "M3", "FK8 Civic" -> model is "Civic")
- For model, use just the base model name without trim (e.g., "M3" not "M3 Base", "Civic" not "Civic Si")
- fitment_style should be one of: "aggressive", "flush", "tucked", or null if not specified
- Common aliases: "poke" = aggressive, "flush"/"even" = flush, "tucked"/"stock" = tucked""",
            messages=[{"role": "user", "content": query}],
        )

        try:
            if response.content and isinstance(response.content[0], TextBlock):
                text = response.content[0].text.strip()
                # Handle markdown code blocks
                if text.startswith("```"):
                    text = text.split("```")[1]
                    if text.startswith("json"):
                        text = text[4:]
                    text = text.strip()
                return cast(dict[str, Any], json.loads(text))
        except (json.JSONDecodeError, IndexError):
            pass
        return {"year": None, "make": None, "model": None, "fitment_style": None}

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

    def ask(
        self,
        query: str,
        year: int | None = None,
        make: str | None = None,
        model: str | None = None,
        fitment_setup: str | None = None,
        fitment_style: str | None = None,
        limit: int = 5,
    ) -> dict[str, Any]:
        """Answer a question using RAG with NLP query parsing."""
        # Use NLP to extract vehicle info if not explicitly provided
        if not any([year, make, model, fitment_style]):
            parsed = self.parse_query(query)
            year = parsed.get("year") or year
            make = parsed.get("make") or make
            model = parsed.get("model") or model
            fitment_style = parsed.get("fitment_style") or fitment_style

        # Build a clean search query from parsed values (avoids FTS issues with chassis codes, etc.)
        search_query_parts = [p for p in [make, model, fitment_style] if p]
        search_query = " ".join(search_query_parts) if search_query_parts else query

        search_results = self.search(
            search_query, year, make, model, fitment_setup, fitment_style, limit
        )

        # If no results, progressively broaden the search
        original_year = year
        original_style = fitment_style

        # Try 1: Drop year filter
        if not search_results and year:
            search_results = self.search(
                search_query, None, make, model, fitment_setup, fitment_style, limit
            )
            if search_results:
                year = None

        # Try 2: Drop fitment_style filter too
        if not search_results and fitment_style:
            # Rebuild search query without style
            search_query = " ".join([p for p in [make, model] if p]) or query
            search_results = self.search(
                search_query, None, make, model, fitment_setup, None, limit
            )
            if search_results:
                year = None
                fitment_style = None

        context = "\n\n".join(
            [f"Fitment {i + 1}:\n{r['document']}" for i, r in enumerate(search_results)]
        )

        system_prompt = """You are a helpful wheel and tire fitment expert.
Use the provided fitment data to answer questions about wheel and tire compatibility.
Be specific about sizes, offsets, backspacing, and any modifications needed.

IMPORTANT: Only provide fitment recommendations based on the data provided. Do NOT make up or guess fitment specs.
If no fitment data is provided, clearly state that you don't have data for that specific vehicle.

Terminology:
- Square setup: same wheel size front and rear
- Staggered setup: different wheel sizes front vs rear
- Aggressive fitment: low offset wheels that poke past the fender
- Flush fitment: wheels sit close to the fender line
- Tucked fitment: wheels sit inside the fender
- Offset (ET): distance from wheel centerline to mounting surface (mm)
- Backspacing: distance from back of wheel to mounting surface (inches)"""

        # Build context note about search adjustments
        search_note = ""
        if original_year and year != original_year:
            search_note = f"\nNote: No data for year {original_year}. Showing other years of this model."
        if original_style and fitment_style != original_style:
            search_note += f"\nNote: Limited '{original_style}' fitment data. Showing all available fitments."

        user_prompt = f"""Based on the following fitment data:{search_note}

{context}

Question: {query}

Provide a helpful, accurate answer based on the fitment data above."""

        response = self.anthropic.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )

        answer_text = ""
        if response.content and isinstance(response.content[0], TextBlock):
            answer_text = response.content[0].text

        return {
            "answer": answer_text,
            "sources": search_results,
            "confidence": search_results[0]["rank"] if search_results else 0,
            "parsed": {
                "year": original_year,
                "make": make,
                "model": model,
                "fitment_style": fitment_style,
                "year_adjusted": year != original_year,
            },
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
