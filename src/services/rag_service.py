"""RAG service - orchestrates fitment queries with streaming responses."""

import uuid
from collections.abc import Generator
from typing import Any

from ..chat.context import (
    parse_vehicle_context,
    set_dspy_assistant,
    validate_vehicle_specs,
)
from ..chat.streaming import (
    emit_finish,
    emit_metadata,
    stream_error,
    stream_greeting,
    stream_llm_response,
)
from ..db import fitments as db
from .kansei import find_matching_wheels, format_recommendations


class RAGService:
    """Main RAG service for wheel fitment queries."""

    def __init__(self, use_dspy: bool = True) -> None:
        self.use_dspy = use_dspy
        if use_dspy:
            self._init_dspy()

    def _init_dspy(self) -> None:
        """Initialize DSPy and set it for context parsing."""
        from .dspy_fitment import create_fitment_assistant

        assistant = create_fitment_assistant("openai/gpt-4o")
        set_dspy_assistant(assistant)

    # -------------------------------------------------------------------------
    # Public API - delegated to db module
    # -------------------------------------------------------------------------

    def load_csv_data(self, csv_path: str, batch_size: int = 500) -> int:
        """Load fitment data from CSV into Supabase."""
        return db.load_csv_data(csv_path, batch_size)

    def get_makes(self) -> list[str]:
        """Get all unique makes."""
        return db.get_makes()

    def get_models(self, make: str) -> list[str]:
        """Get all models for a make."""
        return db.get_models(make)

    def get_years(self) -> list[int]:
        """Get all unique years."""
        return db.get_years()

    # -------------------------------------------------------------------------
    # Streaming Chat
    # -------------------------------------------------------------------------

    def ask_streaming(
        self,
        query: str,
        year: int | None = None,
        make: str | None = None,
        model: str | None = None,
        fitment_setup: str | None = None,
        fitment_style: str | None = None,
        limit: int = 10,
        history: list[dict[str, str]] | None = None,
    ) -> Generator[str, None, dict[str, Any]]:
        """Stream SSE events for a fitment query."""
        message_id = f"msg_{uuid.uuid4().hex}"

        # Parse vehicle context
        parsed = parse_vehicle_context(query, history, year, make, model, fitment_style)

        # No vehicle info - send greeting
        if not any([parsed["year"], parsed["make"], parsed["model"]]):
            return (yield from stream_greeting(message_id, query, parsed))

        # Validate vehicle and get specs
        specs = validate_vehicle_specs(
            parsed["year"], parsed["make"], parsed["model"], parsed["trim"]
        )

        if not specs["vehicle_exists"]:
            return (
                yield from stream_error(message_id, specs["invalid_reason"], parsed)
            )

        # Search for fitment data
        search_results, data_source = self._search_fitments(
            query,
            parsed["year"],
            parsed["make"],
            parsed["model"],
            fitment_setup,
            parsed["fitment_style"],
            limit,
        )

        # Get Kansei recommendations
        kansei_recs = format_recommendations(
            bolt_pattern=specs["bolt_pattern"],
            fitment_specs=search_results,
            offset_tolerance=15,
        )

        # Build context and stream response
        context = self._build_context(search_results, data_source)

        # Stream LLM response
        for event in stream_llm_response(
            message_id=message_id,
            query=query,
            parsed=parsed,
            specs=specs,
            context=context,
            kansei_recs=kansei_recs,
            history=history,
        ):
            if isinstance(event, str):
                yield event

        # Save pending fitment if using LLM knowledge
        pending_id = None
        if data_source == "llm_knowledge":
            pending_id = db.save_pending_fitment(
                year=parsed["year"],
                make=parsed["make"],
                model=parsed["model"],
                trim=parsed.get("trim"),
                fitment_style=parsed.get("fitment_style"),
                bolt_pattern=specs["bolt_pattern"],
                notes=f"Query: {query}",
            )

        # Build and emit metadata
        metadata = {
            "sources": search_results,
            "parsed": parsed,
            "specs": {
                "bolt_pattern": specs["bolt_pattern"],
                "center_bore": specs["center_bore"],
                "max_wheel_diameter": specs["max_diameter"],
                "typical_width_range": specs["width_range"],
                "typical_offset_range": specs["offset_range"],
            },
            "vehicle_exists": True,
            "data_source": data_source,
            "pending_fitment_id": pending_id,
            "kansei_matches": find_matching_wheels(specs["bolt_pattern"])
            if specs["bolt_pattern"] != "Unknown"
            else [],
        }

        yield emit_metadata(metadata)
        yield emit_finish()

        return metadata

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    def _search_fitments(
        self,
        query: str,
        year: int | None,
        make: str | None,
        model: str | None,
        fitment_setup: str | None,
        fitment_style: str | None,
        limit: int,
    ) -> tuple[list[dict[str, Any]], str]:
        """Search for fitments with progressive fallback."""
        search_query_parts = [p for p in [make, model] if p]
        search_query = " ".join(search_query_parts) if search_query_parts else query

        data_source = "exact"
        search_results = db.search(
            search_query, year, make, model, fitment_style, limit
        )

        # Fallback 1: Drop year/style filters
        if not search_results and (year or fitment_style):
            search_results = db.search(search_query, None, make, model, None, limit)

        # Fallback 2: Similar vehicles
        if not search_results and make:
            search_results = db.find_similar_vehicles(make, model, year, limit)
            if search_results:
                data_source = "similar"

        # Fallback 3: LLM knowledge only
        if not search_results:
            data_source = "llm_knowledge"

        return search_results, data_source

    def _build_context(
        self, search_results: list[dict[str, Any]], data_source: str
    ) -> str:
        """Build context string from search results."""
        if data_source == "exact":
            return "\n\n".join(
                [
                    f"Fitment {i + 1}:\n{r['document']}"
                    for i, r in enumerate(search_results)
                ]
            )
        elif data_source == "similar":
            return "\n\n".join(
                [
                    f"REFERENCE Fitment {i + 1} ({r.get('similarity_reason', 'Similar vehicle')}):\n{r['document']}"
                    for i, r in enumerate(search_results)
                ]
            )
        return ""
