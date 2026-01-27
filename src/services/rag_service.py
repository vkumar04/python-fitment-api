"""RAG service - orchestrates fitment queries with real OpenAI streaming.

Flow:
1. DSPy pipeline retrieves context (parse → resolve specs → validate → fetch data)
2. OpenAI streams the final response using the retrieved context
"""

import asyncio
import json
import uuid
from collections.abc import AsyncGenerator
from typing import Any

from openai import AsyncOpenAI

from ..core.config import get_settings
from ..core.logging import log_error, log_external_call
from ..db import fitments as db
from ..prompts.fitment_assistant import SYSTEM_PROMPT, build_user_prompt
from .dspy_v2 import FitmentPipeline, RetrievalResult, create_pipeline


class RAGService:
    """Main RAG service for wheel fitment queries.

    Uses the DSPy v2 pipeline for retrieval and validation,
    then streams the final response via OpenAI.
    """

    def __init__(self, model: str = "openai/gpt-4o") -> None:
        self._pipeline: FitmentPipeline | None = None
        self._model = model
        self._openai_client: AsyncOpenAI | None = None

    def _get_pipeline(self) -> FitmentPipeline:
        """Lazy-load the DSPy pipeline."""
        if self._pipeline is None:
            self._pipeline = create_pipeline(self._model)
        return self._pipeline

    def _get_openai_client(self) -> AsyncOpenAI:
        """Lazy-load the async OpenAI client."""
        if self._openai_client is None:
            settings = get_settings()
            self._openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
        return self._openai_client

    # -------------------------------------------------------------------------
    # Data Operations
    # -------------------------------------------------------------------------

    async def load_csv_data(self, csv_path: str, batch_size: int = 500) -> int:
        return await db.load_csv_data(csv_path, batch_size)

    async def get_makes(self) -> list[str]:
        return await db.get_makes()

    async def get_models(self, make: str) -> list[str]:
        return await db.get_models(make)

    async def get_years(self) -> list[int]:
        return await db.get_years()

    # -------------------------------------------------------------------------
    # Non-Streaming Query
    # -------------------------------------------------------------------------

    async def ask(self, query: str) -> dict[str, Any]:
        """Process a fitment query and return the complete response."""
        try:
            pipeline = self._get_pipeline()
            result = await asyncio.to_thread(pipeline.forward, query)
            log_external_call("dspy", "FitmentPipeline.forward", True)

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
    # Streaming Query (real token-by-token OpenAI streaming)
    # -------------------------------------------------------------------------

    async def ask_streaming(
        self,
        query: str,
        history: list[dict[str, str]] | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream SSE events for a fitment query.

        Phase 1: DSPy pipeline retrieves context (vehicle specs, community
                 fitments, matching Kansei wheels).
        Phase 2: OpenAI streams the response using that context.

        Emits Vercel AI SDK compatible SSE events.
        """
        message_id = f"msg_{uuid.uuid4().hex}"

        try:
            # Phase 1: Retrieval via DSPy pipeline (sync, runs in thread)
            pipeline = self._get_pipeline()
            retrieval: RetrievalResult = await asyncio.to_thread(
                pipeline.retrieve, query
            )

            yield _emit_event("start", {"messageId": message_id})

            # Early return (clarification, error, invalid vehicle)
            if retrieval.early_response:
                yield _emit_event("text-start", {"id": message_id})
                yield _emit_event(
                    "text-delta",
                    {"id": message_id, "delta": retrieval.early_response},
                )
                yield _emit_event("text-end", {"id": message_id})
                yield _emit_event(
                    "data-metadata",
                    {
                        "data": {
                            "parsed": retrieval.parsed,
                            "specs": retrieval.specs,
                            "validation": retrieval.validation,
                        }
                    },
                )
                yield _emit_event("finish", {"finishReason": "stop"})
                yield "data: [DONE]\n\n"
                return

            # Phase 2: Stream response via OpenAI
            specs = retrieval.specs or {}
            user_content = build_user_prompt(
                query=query,
                vehicle_info=retrieval.vehicle_summary,
                bolt_pattern=specs.get("bolt_pattern", "Unknown"),
                center_bore=float(specs.get("center_bore", 0)),
                max_diameter=int(specs.get("max_diameter", 20)),
                width_range=f"{specs.get('min_width', 6.0)}-{specs.get('max_width', 10.0)}",
                offset_range=f"+{specs.get('min_offset', -10)} to +{specs.get('max_offset', 50)}",
                context=retrieval.community_str,
                kansei_recommendations=retrieval.kansei_str,
                trim=retrieval.parsed.get("trim"),
                suspension=retrieval.parsed.get("suspension"),
            )

            messages: list[dict[str, str]] = [
                {"role": "system", "content": SYSTEM_PROMPT}
            ]
            if history:
                for msg in history[-6:]:
                    messages.append(
                        {"role": msg["role"], "content": msg["content"]}
                    )
            messages.append({"role": "user", "content": user_content})

            settings = get_settings()
            client = self._get_openai_client()

            stream = await client.chat.completions.create(
                model=settings.openai_model,
                messages=messages,  # type: ignore[arg-type]
                max_tokens=settings.openai_max_tokens,
                stream=True,
            )
            log_external_call("openai", "chat.completions.create", True)

            yield _emit_event("text-start", {"id": message_id})

            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    yield _emit_event(
                        "text-delta", {"id": message_id, "delta": content}
                    )

            yield _emit_event("text-end", {"id": message_id})

            # Metadata with retrieval context
            yield _emit_event(
                "data-metadata",
                {
                    "data": {
                        "sources": retrieval.community_fitments[:5],
                        "parsed": retrieval.parsed,
                        "specs": retrieval.specs,
                        "kansei_wheels": [
                            {
                                "model": w.get("model"),
                                "diameter": w.get("diameter"),
                                "width": w.get("width"),
                                "offset": w.get("offset"),
                                "price": w.get("price"),
                                "url": w.get("url"),
                            }
                            for w in retrieval.kansei_wheels[:10]
                        ],
                        "validation": retrieval.validation,
                    }
                },
            )

            yield _emit_event("finish", {"finishReason": "stop"})
            yield "data: [DONE]\n\n"

        except Exception as e:
            log_error("Streaming error", e, query=query[:50])
            yield _emit_event("start", {"messageId": message_id})
            yield _emit_event(
                "error", {"message": "An unexpected error occurred"}
            )
            yield _emit_event("finish", {"finishReason": "error"})
            yield "data: [DONE]\n\n"


def _emit_event(event_type: str, data: dict[str, Any]) -> str:
    """Format an SSE event in Vercel AI SDK format."""
    payload = {"type": event_type, **data}
    return f"data: {json.dumps(payload)}\n\n"


# -----------------------------------------------------------------------------
# Singleton
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
