"""SSE streaming utilities for chat responses - async version."""

import json
from collections.abc import AsyncGenerator
from typing import Any

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessageParam

from ..core.config import get_settings
from ..core.logging import log_error, log_external_call
from ..prompts.fitment_assistant import (
    FITMENT_TERMS,
    GREETING_DEFAULT,
    GREETING_FITMENT_FOLLOWUP,
    SYSTEM_PROMPT,
    build_user_prompt,
)

# Async OpenAI client (lazy loaded)
_openai_client: AsyncOpenAI | None = None


def _get_openai_client() -> AsyncOpenAI:
    """Get or create async OpenAI client."""
    global _openai_client
    if _openai_client is None:
        settings = get_settings()
        _openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _openai_client


async def stream_greeting(
    message_id: str,
    query: str,
    parsed: dict[str, Any],
) -> AsyncGenerator[str, None]:
    """Stream a greeting response when no vehicle is specified."""
    query_lower = query.lower()
    is_fitment_followup = any(term in query_lower for term in FITMENT_TERMS)
    greeting = GREETING_FITMENT_FOLLOWUP if is_fitment_followup else GREETING_DEFAULT

    async for event in _emit_simple_response(message_id, greeting):
        yield event


def get_greeting_metadata(
    query: str,
    parsed: dict[str, Any],
) -> dict[str, Any]:
    """Get metadata for a greeting response."""
    query_lower = query.lower()
    is_fitment_followup = any(term in query_lower for term in FITMENT_TERMS)
    greeting = GREETING_FITMENT_FOLLOWUP if is_fitment_followup else GREETING_DEFAULT

    return {
        "answer": greeting,
        "sources": [],
        "parsed": parsed,
        "vehicle_exists": True,
        "data_source": "greeting",
    }


async def stream_error(
    message_id: str,
    error_reason: str | None,
    parsed: dict[str, Any],
) -> AsyncGenerator[str, None]:
    """Stream an error response (e.g., invalid vehicle)."""
    error_msg = f"**Vehicle Not Found**\n\n{error_reason or 'This vehicle combination does not exist.'}"

    async for event in _emit_simple_response(message_id, error_msg):
        yield event


def get_error_metadata(
    error_reason: str | None,
    parsed: dict[str, Any],
) -> dict[str, Any]:
    """Get metadata for an error response."""
    error_msg = f"**Vehicle Not Found**\n\n{error_reason or 'This vehicle combination does not exist.'}"
    return {
        "answer": error_msg,
        "sources": [],
        "parsed": parsed,
        "vehicle_exists": False,
        "data_source": "invalid_vehicle",
    }


async def stream_year_clarification(
    message_id: str,
    clarification_msg: str,
    parsed: dict[str, Any],
) -> AsyncGenerator[str, None]:
    """Stream a year clarification request."""
    async for event in _emit_simple_response(message_id, clarification_msg):
        yield event


def get_year_clarification_metadata(
    clarification_msg: str,
    parsed: dict[str, Any],
) -> dict[str, Any]:
    """Get metadata for a year clarification response."""
    return {
        "answer": clarification_msg,
        "sources": [],
        "parsed": parsed,
        "vehicle_exists": True,
        "needs_year": True,
        "data_source": "clarification",
    }


async def stream_llm_response(
    message_id: str,
    query: str,
    parsed: dict[str, Any],
    specs: dict[str, Any],
    context: str,
    kansei_recs: str,
    history: list[dict[str, str]] | None = None,
) -> AsyncGenerator[tuple[str, str | None], None]:
    """Stream the main LLM response. Yields (event, full_response) tuples.

    The full_response is None until the final yield, which contains the complete text.
    """
    vehicle_info = (
        f"{parsed['year'] or ''} {parsed['make'] or ''} {parsed['model'] or ''}".strip()
    )
    user_content = build_user_prompt(
        query=query,
        vehicle_info=vehicle_info,
        bolt_pattern=specs["bolt_pattern"],
        center_bore=specs["center_bore"],
        max_diameter=specs["max_diameter"],
        width_range=specs["width_range"],
        offset_range=specs["offset_range"],
        context=context,
        kansei_recommendations=kansei_recs,
        trim=parsed.get("trim"),
        suspension=parsed.get("suspension"),
    )

    yield (_emit_event("start", {"messageId": message_id}), None)

    # Build messages
    openai_messages: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]

    if history:
        for msg in history[-6:]:
            if msg["role"] == "user":
                openai_messages.append({"role": "user", "content": msg["content"]})
            elif msg["role"] == "assistant":
                openai_messages.append({"role": "assistant", "content": msg["content"]})

    openai_messages.append({"role": "user", "content": user_content})

    # Stream from OpenAI
    settings = get_settings()
    client = _get_openai_client()

    try:
        stream = await client.chat.completions.create(
            model=settings.openai_model,
            messages=openai_messages,
            max_tokens=settings.openai_max_tokens,
            stream=True,
        )
        log_external_call("openai", "chat.completions.create", True)
    except Exception as e:
        log_error("OpenAI streaming failed", e)
        yield (_emit_event("error", {"message": "Failed to generate response"}), "")
        return

    yield (_emit_event("text-start", {"id": message_id}), None)

    full_response = ""
    async for chunk in stream:
        if chunk.choices[0].delta.content:
            content = chunk.choices[0].delta.content
            full_response += content
            yield (
                _emit_event("text-delta", {"id": message_id, "delta": content}),
                None,
            )

    # Append Kansei recommendations if not already included
    if kansei_recs and "KANSEI" not in full_response.upper():
        yield (
            _emit_event(
                "text-delta", {"id": message_id, "delta": "\n\n" + kansei_recs}
            ),
            None,
        )
        full_response += "\n\n" + kansei_recs

    yield (_emit_event("text-end", {"id": message_id}), full_response)


def emit_metadata(metadata: dict[str, Any]) -> str:
    """Emit metadata event."""
    return _emit_event("data-metadata", {"data": metadata})


def emit_finish() -> str:
    """Emit finish event and done marker."""
    return _emit_event("finish", {}) + "data: [DONE]\n\n"


# -----------------------------------------------------------------------------
# Private helpers
# -----------------------------------------------------------------------------


def _emit_event(event_type: str, data: dict[str, Any]) -> str:
    """Format an SSE event."""
    payload = {"type": event_type, **data}
    return f"data: {json.dumps(payload)}\n\n"


async def _emit_simple_response(
    message_id: str, content: str
) -> AsyncGenerator[str, None]:
    """Emit a simple non-streaming response."""
    yield _emit_event("start", {"messageId": message_id})
    yield _emit_event("text-start", {"id": message_id})
    yield _emit_event("text-delta", {"id": message_id, "delta": content})
    yield _emit_event("text-end", {"id": message_id})
    yield _emit_event("finish", {"finishReason": "stop"})
    yield "data: [DONE]\n\n"
