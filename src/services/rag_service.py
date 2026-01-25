"""RAG service - orchestrates fitment queries using DSPy pipeline.

This service provides the main entry point for wheel fitment queries.
It uses the DSPy v2 pipeline for all AI processing.
"""

import uuid
from collections.abc import AsyncGenerator
from typing import Any

from ..core.logging import log_error, log_external_call
from ..db import fitments as db
from .dspy_v2 import FitmentPipeline, create_pipeline


class RAGService:
    """Main RAG service for wheel fitment queries.

    Uses the DSPy v2 pipeline for:
    - Parsing user input
    - Resolving vehicle specs
    - Validating fitment matches
    - Generating responses
    """

    def __init__(self, model: str = "openai/gpt-4o") -> None:
        """Initialize the RAG service.

        Args:
            model: LLM model to use for the pipeline
        """
        self._pipeline: FitmentPipeline | None = None
        self._model = model

    def _get_pipeline(self) -> FitmentPipeline:
        """Lazy-load the pipeline."""
        if self._pipeline is None:
            self._pipeline = create_pipeline(self._model)
        return self._pipeline

    # -------------------------------------------------------------------------
    # Public API - Data Operations (unchanged)
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
    # Main Query Method - Non-Streaming
    # -------------------------------------------------------------------------

    async def ask(self, query: str) -> dict[str, Any]:
        """Process a fitment query and return the response.

        This is the main entry point for fitment queries.

        Args:
            query: User's natural language query (e.g., "2020 Honda Civic")

        Returns:
            Dictionary with:
            - response: The conversational response text
            - parsed: Parsed vehicle information
            - specs: Vehicle specifications
            - kansei_wheels: Matching Kansei wheel options
            - community_fitments: Community fitment data
            - validation: Validation results
        """
        try:
            pipeline = self._get_pipeline()
            log_external_call("dspy", "FitmentPipeline.forward", True)

            result = await pipeline.forward(query)

            return {
                "response": result.response,
                "parsed": result.parsed,
                "specs": result.specs,
                "kansei_wheels": result.kansei_wheels,
                "community_fitments": result.community_fitments,
                "validation": result.validation,
            }

        except Exception as e:
            log_error("Pipeline error", e, query=query[:100])
            return {
                "response": "Sorry, I encountered an error processing your request. Please try again.",
                "parsed": None,
                "specs": None,
                "kansei_wheels": [],
                "community_fitments": [],
                "validation": {"valid": False, "reason": str(e)},
            }

    # -------------------------------------------------------------------------
    # Streaming Method (for SSE responses)
    # -------------------------------------------------------------------------

    async def ask_streaming(
        self,
        query: str,
        history: list[dict[str, str]] | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream SSE events for a fitment query.

        This method wraps the pipeline and streams the response
        in Vercel AI SDK compatible format.

        Args:
            query: User's natural language query
            history: Optional conversation history (not currently used by pipeline)

        Yields:
            SSE event strings
        """
        import json

        message_id = f"msg_{uuid.uuid4().hex}"

        def emit_event(event_type: str, data: dict[str, Any]) -> str:
            payload = {"type": event_type, **data}
            return f"data: {json.dumps(payload)}\n\n"

        try:
            # Start event
            yield emit_event("start", {"messageId": message_id})

            # Run the pipeline
            result = await self.ask(query)

            # Stream the response
            yield emit_event("text-start", {"id": message_id})

            response = result.get("response", "")

            # Stream response in chunks for better UX
            chunk_size = 50
            for i in range(0, len(response), chunk_size):
                chunk = response[i : i + chunk_size]
                yield emit_event("text-delta", {"id": message_id, "delta": chunk})

            yield emit_event("text-end", {"id": message_id})

            # Emit metadata
            metadata = {
                "sources": result.get("community_fitments", [])[:5],
                "parsed": result.get("parsed"),
                "specs": result.get("specs"),
                "kansei_wheels": [
                    {
                        "model": w.get("model"),
                        "diameter": w.get("diameter"),
                        "width": w.get("width"),
                        "offset": w.get("offset"),
                        "price": w.get("price"),
                        "url": w.get("url"),
                    }
                    for w in (result.get("kansei_wheels") or [])[:10]
                ],
                "validation": result.get("validation"),
            }
            yield emit_event("data-metadata", {"data": metadata})

            # Finish
            yield emit_event("finish", {"finishReason": "stop"})
            yield "data: [DONE]\n\n"

        except Exception as e:
            log_error("Streaming error", e, query=query[:50])
            yield emit_event("error", {"message": "An unexpected error occurred"})
            yield emit_event("finish", {"finishReason": "error"})
            yield "data: [DONE]\n\n"


# -----------------------------------------------------------------------------
# Singleton instance for backward compatibility
# -----------------------------------------------------------------------------

_rag_service: RAGService | None = None


def get_rag_service() -> RAGService:
    """Get the singleton RAG service instance."""
    global _rag_service
    if _rag_service is None:
        from ..core.config import get_settings

        settings = get_settings()
        _rag_service = RAGService(model=settings.dspy_model)
    return _rag_service
