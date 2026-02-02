"""RAG service - orchestrates fitment queries with real OpenAI streaming.

Flow:
1. DSPy pipeline retrieves context (parse → resolve specs → validate → fetch data)
2. OpenAI streams the final response using the retrieved context
"""

import asyncio
import json
import re
import uuid
from collections.abc import AsyncGenerator
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from openai import AsyncOpenAI

from ..core.config import get_settings
from ..core.logging import log_error, log_external_call, logger
from ..db import fitments as db
from ..prompts.fitment_assistant import SYSTEM_PROMPT, build_user_prompt
from .dspy_v2 import FitmentPipeline, create_pipeline
from .retrieval_cache import RetrievalCache


class RAGService:
    """Main RAG service for wheel fitment queries.

    Uses the DSPy v2 pipeline for retrieval and validation,
    then streams the final response via OpenAI.
    """

    def __init__(self, model: str = "openai/gpt-4o") -> None:
        self._pipeline: FitmentPipeline | None = None
        self._model = model
        self._openai_client: AsyncOpenAI | None = None
        self._retrieval_cache = RetrievalCache(maxsize=256, ttl=1800)
        self._pipeline_semaphore = asyncio.Semaphore(12)

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
    # Conversation Context
    # -------------------------------------------------------------------------

    @staticmethod
    def _has_vehicle_info(text: str) -> bool:
        """Check if text contains vehicle identifiers (year, make, or chassis code)."""
        text_lower = text.lower()
        words = set(text_lower.split())

        # Year pattern (4-digit number between 1950-2030)
        if re.search(r"\b(19[5-9]\d|20[0-3]\d)\b", text):
            return True

        # Known chassis codes
        chassis_codes = {
            # BMW
            "e21", "e24", "e28", "e30", "e34", "e36", "e38", "e39",
            "e46", "e53", "e60", "e82", "e90", "e92", "f10", "f30",
            "f80", "f82", "g20", "g80", "g82",
            # Honda
            "fk2", "fk7", "fk8", "fl5", "dc2", "dc5",
            # Nissan
            "s13", "s14", "s15", "z32", "z33", "z34",
            "r32", "r33", "r34", "r35",
            # Subaru
            "gc8", "va", "vb",
            # Toyota
            "ae86", "jza80", "a80", "a90",
        }
        if words & chassis_codes:
            return True

        # Common makes
        makes = {
            "acura", "audi", "bmw", "buick", "cadillac", "chevrolet", "chevy",
            "chrysler", "dodge", "ford", "genesis", "gmc", "honda", "hyundai",
            "infiniti", "jaguar", "jeep", "kia", "lexus", "lincoln", "mazda",
            "mercedes", "mini", "mitsubishi", "nissan", "pontiac", "porsche",
            "ram", "scion", "subaru", "tesla", "toyota", "volkswagen", "vw",
            "volvo",
        }
        if words & makes:
            return True

        return False

    def _augment_query_with_history(
        self,
        query: str,
        history: list[dict[str, str]] | None,
    ) -> str:
        """Prepend vehicle context from history if the current query lacks it.

        Scans previous user messages for vehicle info (year, make, model, chassis).
        If found and the current query doesn't already contain vehicle info,
        prepends it so the DSPy pipeline can resolve the vehicle.
        """
        if not history:
            return query

        # If the query already has vehicle info, it's a fresh query
        if self._has_vehicle_info(query):
            return query

        # Find the most recent user message that had vehicle info
        for msg in reversed(history):
            if msg["role"] == "user" and self._has_vehicle_info(msg["content"]):
                vehicle_query = msg["content"].strip()
                return f"{vehicle_query} — {query}"

        return query

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
        executor: ThreadPoolExecutor | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream SSE events for a fitment query.

        Phase 1: DSPy pipeline retrieves context (vehicle specs, community
                 fitments, matching Kansei wheels). Results are cached so
                 identical vehicle queries skip the pipeline.
        Phase 2: OpenAI streams the response using that context.

        Emits Vercel AI SDK compatible SSE events.

        Args:
            query: User's natural language query.
            history: Conversation history for follow-up context.
            executor: Optional ThreadPoolExecutor for pipeline calls.
        """
        message_id = f"msg_{uuid.uuid4().hex}"

        async def _run_in_thread(fn: Any, *args: Any) -> Any:
            """Run a sync function in the thread pool."""
            if executor:
                loop = asyncio.get_running_loop()
                return await loop.run_in_executor(executor, fn, *args)
            return await asyncio.to_thread(fn, *args)

        started = False
        text_id = f"text_{uuid.uuid4().hex[:8]}"

        try:
            # Phase 1: Retrieval via DSPy pipeline
            # Augment query with vehicle context from history for follow-ups
            pipeline = self._get_pipeline()
            augmented_query = self._augment_query_with_history(query, history)

            # Step 1a: Quick parse to build cache key (~2s, one LLM call)
            def _parse_input() -> Any:
                return pipeline.parse_input(user_input=augmented_query)

            parsed_raw = await _run_in_thread(_parse_input)

            if not parsed_raw.is_valid_input or str(parsed_raw.is_valid_input).lower() == "false":
                # Invalid input — return clarification directly
                clarification = (
                    parsed_raw.clarification_needed
                    or "What vehicle are you working with?"
                )
                parsed_info = pipeline._extract_parsed(parsed_raw)

                yield _emit_event("start", {"messageId": message_id})
                yield _emit_event("text-start", {"id": text_id})
                yield _emit_event(
                    "text-delta",
                    {"id": text_id, "delta": clarification},
                )
                yield _emit_event("text-end", {"id": text_id})
                yield _emit_event(
                    "data-fitment",
                    {
                        "data": {
                            "parsed": parsed_info,
                            "specs": None,
                            "validation": {"valid": False, "reason": "insufficient_input"},
                        }
                    },
                )
                yield _emit_event("finish", {})
                yield "data: [DONE]\n\n"
                return

            parsed_info = pipeline._extract_parsed(parsed_raw)

            # Step 1b: Check retrieval cache
            cache_key = RetrievalCache.make_key(parsed_info)
            cached = self._retrieval_cache.get(cache_key)

            if cached is not None:
                retrieval = cached
                logger.info("Retrieval cache hit: %s", cache_key)
            else:
                # Step 1c: Full retrieval (expensive, gated by semaphore)
                async with self._pipeline_semaphore:
                    retrieval = await _run_in_thread(
                        pipeline.retrieve, augmented_query
                    )

                # Cache successful retrievals (not early_response errors)
                if not retrieval.early_response:
                    self._retrieval_cache.set(cache_key, retrieval)

            yield _emit_event("start", {"messageId": message_id})
            started = True

            # Early return (clarification, error, invalid vehicle)
            if retrieval.early_response:
                yield _emit_event("text-start", {"id": text_id})
                yield _emit_event(
                    "text-delta",
                    {"id": text_id, "delta": retrieval.early_response},
                )
                yield _emit_event("text-end", {"id": text_id})
                yield _emit_event(
                    "data-fitment",
                    {
                        "data": {
                            "parsed": retrieval.parsed,
                            "specs": retrieval.specs,
                            "validation": retrieval.validation,
                        }
                    },
                )
                yield _emit_event("finish", {})
                yield "data: [DONE]\n\n"
                return

            # Phase 2: Stream response via OpenAI
            specs = retrieval.specs or {}
            user_content = build_user_prompt(
                query=query,
                vehicle_info=retrieval.vehicle_summary,
                bolt_pattern=specs.get("bolt_pattern", "Unknown"),
                center_bore=float(specs.get("center_bore") or 0),
                max_diameter=int(specs.get("max_diameter") or 20),
                width_range=f"{specs.get('min_width', 6.0)}-{specs.get('max_width', 10.0)}",
                offset_range=f"+{specs.get('min_offset', -10)} to +{specs.get('max_offset', 50)}",
                context=retrieval.community_str,
                kansei_recommendations=retrieval.kansei_str,
                trim=retrieval.parsed.get("trim"),
                suspension=retrieval.parsed.get("suspension"),
                recommended_setups=retrieval.recommended_setups_str,
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

            yield _emit_event("text-start", {"id": text_id})

            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    yield _emit_event(
                        "text-delta", {"id": text_id, "delta": content}
                    )

            yield _emit_event("text-end", {"id": text_id})

            # Metadata with retrieval context
            yield _emit_event(
                "data-fitment",
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

            yield _emit_event("finish", {})
            yield "data: [DONE]\n\n"

        except Exception as e:
            log_error("Streaming error", e, query=query[:50])
            if not started:
                yield _emit_event("start", {"messageId": message_id})
            error_id = f"error_{uuid.uuid4().hex[:8]}"
            yield _emit_event("text-start", {"id": error_id})
            yield _emit_event(
                "text-delta",
                {"id": error_id, "delta": "An unexpected error occurred. Please try again."},
            )
            yield _emit_event("text-end", {"id": error_id})
            yield _emit_event("finish", {})
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
