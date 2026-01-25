"""SSE streaming utilities for chat responses."""

import json
import os
from collections.abc import Generator
from typing import Any

from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam

from ..prompts.fitment_assistant import (
    FITMENT_TERMS,
    GREETING_DEFAULT,
    GREETING_FITMENT_FOLLOWUP,
    SYSTEM_PROMPT,
    build_user_prompt,
)

# OpenAI client (lazy loaded)
_openai_client: OpenAI | None = None


def _get_openai_client() -> OpenAI:
    """Get or create OpenAI client."""
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _openai_client


def stream_greeting(
    message_id: str,
    query: str,
    parsed: dict[str, Any],
) -> Generator[str, None, dict[str, Any]]:
    """Stream a greeting response when no vehicle is specified."""
    query_lower = query.lower()
    is_fitment_followup = any(term in query_lower for term in FITMENT_TERMS)
    greeting = GREETING_FITMENT_FOLLOWUP if is_fitment_followup else GREETING_DEFAULT

    yield from _emit_simple_response(message_id, greeting)

    return {
        "answer": greeting,
        "sources": [],
        "parsed": parsed,
        "vehicle_exists": True,
        "data_source": "greeting",
    }


def stream_error(
    message_id: str,
    error_reason: str | None,
    parsed: dict[str, Any],
) -> Generator[str, None, dict[str, Any]]:
    """Stream an error response (e.g., invalid vehicle)."""
    error_msg = f"**Vehicle Not Found**\n\n{error_reason or 'This vehicle combination does not exist.'}"

    yield from _emit_simple_response(message_id, error_msg)

    return {
        "answer": error_msg,
        "sources": [],
        "parsed": parsed,
        "vehicle_exists": False,
        "data_source": "invalid_vehicle",
    }


def stream_year_clarification(
    message_id: str,
    clarification_msg: str,
    parsed: dict[str, Any],
) -> Generator[str, None, dict[str, Any]]:
    """Stream a year clarification request."""
    yield from _emit_simple_response(message_id, clarification_msg)

    return {
        "answer": clarification_msg,
        "sources": [],
        "parsed": parsed,
        "vehicle_exists": True,
        "needs_year": True,
        "data_source": "clarification",
    }


def stream_llm_response(
    message_id: str,
    query: str,
    parsed: dict[str, Any],
    specs: dict[str, Any],
    context: str,
    kansei_recs: str,
    history: list[dict[str, str]] | None = None,
) -> Generator[str, None, str]:
    """Stream the main LLM response and return the full text."""
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

    yield _emit_event("start", {"messageId": message_id})

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
    client = _get_openai_client()
    stream = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=openai_messages,
        max_tokens=512,
        stream=True,
    )

    yield _emit_event("text-start", {"id": message_id})

    full_response = ""
    for chunk in stream:
        if chunk.choices[0].delta.content:
            content = chunk.choices[0].delta.content
            full_response += content
            yield _emit_event("text-delta", {"id": message_id, "delta": content})

    # Append Kansei recommendations if not already included
    if kansei_recs and "KANSEI" not in full_response.upper():
        yield _emit_event(
            "text-delta", {"id": message_id, "delta": "\n\n" + kansei_recs}
        )
        full_response += "\n\n" + kansei_recs

    yield _emit_event("text-end", {"id": message_id})

    return full_response


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


def _emit_simple_response(message_id: str, content: str) -> Generator[str, None, None]:
    """Emit a simple non-streaming response."""
    yield _emit_event("start", {"messageId": message_id})
    yield _emit_event("text-start", {"id": message_id})
    yield _emit_event("text-delta", {"id": message_id, "delta": content})
    yield _emit_event("text-end", {"id": message_id})
    yield _emit_event("finish", {"finishReason": "stop"})
    yield "data: [DONE]\n\n"
