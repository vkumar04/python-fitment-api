"""RAG service - orchestrates fitment queries with async streaming responses."""

import uuid
from collections.abc import AsyncGenerator
from typing import Any

from ..chat.context import (
    parse_vehicle_context,
    set_dspy_assistant,
    validate_vehicle_specs,
)
from ..chat.streaming import (
    emit_finish,
    emit_metadata,
    get_error_metadata,
    get_greeting_metadata,
    get_year_clarification_metadata,
    stream_error,
    stream_greeting,
    stream_llm_response,
    stream_year_clarification,
)
from ..core.logging import log_error
from ..db import fitments as db
from .kansei import format_recommendations


class RAGService:
    """Main RAG service for wheel fitment queries."""

    def __init__(self, use_dspy: bool = True) -> None:
        self.use_dspy = use_dspy
        if use_dspy:
            self._init_dspy()

    def _init_dspy(self) -> None:
        """Initialize DSPy and set it for context parsing."""
        from ..core.config import get_settings
        from .dspy_fitment import create_fitment_assistant

        settings = get_settings()
        assistant = create_fitment_assistant(settings.dspy_model)
        set_dspy_assistant(assistant)

    # -------------------------------------------------------------------------
    # Public API - async versions
    # -------------------------------------------------------------------------

    async def load_csv_data(self, csv_path: str, batch_size: int = 500) -> int:
        """Load fitment data from CSV into Supabase."""
        return await db.load_csv_data(csv_path, batch_size)

    async def get_makes(self) -> list[str]:
        """Get all unique makes."""
        return await db.get_makes()

    async def get_models(self, make: str) -> list[str]:
        """Get all models for a make."""
        return await db.get_models(make)

    async def get_years(self) -> list[int]:
        """Get all unique years."""
        return await db.get_years()

    # -------------------------------------------------------------------------
    # Async Streaming Chat
    # -------------------------------------------------------------------------

    async def ask_streaming(
        self,
        query: str,
        year: int | None = None,
        make: str | None = None,
        model: str | None = None,
        fitment_setup: str | None = None,
        fitment_style: str | None = None,
        limit: int = 10,
        history: list[dict[str, str]] | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream SSE events for a fitment query."""
        message_id = f"msg_{uuid.uuid4().hex}"

        try:
            # Parse vehicle context (sync, but fast with cache)
            parsed = parse_vehicle_context(
                query, history, year, make, model, fitment_style
            )

            # No vehicle info - send greeting
            if not any([parsed["year"], parsed["make"], parsed["model"]]):
                async for event in stream_greeting(message_id, query, parsed):
                    yield event
                metadata = get_greeting_metadata(query, parsed)
                yield emit_metadata(metadata)
                yield emit_finish()
                return

            # Validate vehicle and get specs (sync DSPy call)
            specs = validate_vehicle_specs(
                parsed["year"], parsed["make"], parsed["model"], parsed["trim"]
            )

            if not specs["vehicle_exists"]:
                async for event in stream_error(
                    message_id, specs["invalid_reason"], parsed
                ):
                    yield event
                metadata = get_error_metadata(specs["invalid_reason"], parsed)
                yield emit_metadata(metadata)
                yield emit_finish()
                return

            # Check if we need year clarification
            if specs.get("needs_year"):
                async for event in stream_year_clarification(
                    message_id, specs["year_clarification"], parsed
                ):
                    yield event
                metadata = get_year_clarification_metadata(
                    specs["year_clarification"], parsed
                )
                yield emit_metadata(metadata)
                yield emit_finish()
                return

            # Search for fitment data (async)
            search_results, data_source = await self._search_fitments(
                query,
                parsed["year"],
                parsed["make"],
                parsed["model"],
                fitment_setup,
                parsed["fitment_style"],
                parsed.get("suspension"),
                limit,
            )

            # Get Kansei recommendations validated against vehicle specs
            vehicle_specs = {
                "max_diameter": specs["max_diameter"],
                "min_diameter": specs.get("min_diameter", 15),
                "width_range": specs["width_range"],
                "offset_range": specs["offset_range"],
            }
            kansei_recs = format_recommendations(
                bolt_pattern=specs["bolt_pattern"],
                vehicle_specs=vehicle_specs,
                fitment_data=search_results,
            )

            # Build context and stream response
            context = self._build_context(search_results, data_source)

            # Stream LLM response (async)
            async for event, _ in stream_llm_response(
                message_id=message_id,
                query=query,
                parsed=parsed,
                specs=specs,
                context=context,
                kansei_recs=kansei_recs,
                history=history,
            ):
                yield event

            # Save pending fitment if using LLM knowledge (async)
            pending_id = None
            if data_source == "llm_knowledge":
                pending_id = await db.save_pending_fitment(
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
            }

            yield emit_metadata(metadata)
            yield emit_finish()

        except Exception as e:
            log_error("Streaming error", e, query=query[:50])
            yield emit_metadata({"error": "An unexpected error occurred"})
            yield emit_finish()

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    async def _search_fitments(
        self,
        query: str,
        year: int | None,
        make: str | None,
        model: str | None,
        fitment_setup: str | None,
        fitment_style: str | None,
        suspension: str | None,
        limit: int,
    ) -> tuple[list[dict[str, Any]], str]:
        """Search for fitments with progressive fallback (async)."""
        search_query_parts = [p for p in [make, model] if p]
        search_query = " ".join(search_query_parts) if search_query_parts else query

        data_source = "exact"
        search_results = await db.search(
            search_query, year, make, model, fitment_style, limit
        )

        # Fallback 1: Drop year/style filters
        if not search_results and (year or fitment_style):
            search_results = await db.search(
                search_query, None, make, model, None, limit
            )

        # Fallback 2: Similar vehicles
        if not search_results and make:
            search_results = await db.find_similar_vehicles(make, model, year, limit)
            if search_results:
                data_source = "similar"

        # Fallback 3: LLM knowledge only
        if not search_results:
            data_source = "llm_knowledge"

        # Filter/prioritize by suspension if specified
        if suspension and search_results:
            search_results = db.filter_by_suspension(search_results, suspension)

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
