"""FastAPI route definitions for the Kansei Fitment Assistant API."""

import json
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.dspy_modules.conversational import get_fitment_agent
from app.models.fitment import FitmentResponse
from app.models.vehicle import VehicleSpecs
from app.services.fitment_engine import (
    lookup_known_specs,
    lookup_vehicle_specs,
    score_fitment,
)
from app.services.kansei_db import (
    find_wheels_by_bolt_pattern,
    get_unique_bolt_patterns,
)
from app.services.nhtsa import nhtsa_client

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------


class _ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    # Accept both "message" (new) and "query" (legacy frontend) field names
    message: Optional[str] = None
    query: Optional[str] = None
    conversation_history: Optional[str] = ""
    messages: Optional[list[_ChatMessage]] = None

    @property
    def user_message(self) -> str:
        """Return the user message from whichever field was provided."""
        msg = self.message or self.query
        if not msg:
            raise ValueError("Either 'message' or 'query' must be provided")
        return msg

    @property
    def history_str(self) -> str:
        """Build a conversation history string from either field."""
        if self.conversation_history:
            return self.conversation_history
        if self.messages:
            return "\n".join(f"{m.role}: {m.content}" for m in self.messages)
        return ""


class ChatResponse(BaseModel):
    response: str


class VINDecodeRequest(BaseModel):
    vin: str


class FitmentRequest(BaseModel):
    year: int
    make: str
    model: str
    trim: Optional[str] = None
    bolt_pattern: Optional[str] = None
    oem_offset: Optional[int] = None
    oem_diameter: Optional[float] = None
    hub_bore: Optional[float] = None
    category: Optional[str] = None


# ---------------------------------------------------------------------------
# Chat (DSPy-powered)
# ---------------------------------------------------------------------------


@router.post("/chat")
async def chat(req: ChatRequest):
    """Conversational fitment assistant powered by DSPy ReAct.

    Returns SSE with text-delta events that the Next.js frontend
    parses via ReadableStream:
        data: {"type": "text-delta", "delta": "chunk"}\n\n
        data: [DONE]\n\n
    """
    try:
        agent = get_fitment_agent()
        result = agent(
            user_message=req.user_message,
            conversation_history=req.history_str,
        )
        text = result.response or ""
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    async def generate():
        # Stream the full response as a single text-delta event
        # (DSPy agent returns the complete response, not chunks)
        yield f"data: {json.dumps({'type': 'text-delta', 'delta': text})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# VIN Decode
# ---------------------------------------------------------------------------


@router.post("/decode-vin")
async def decode_vin_endpoint(req: VINDecodeRequest):
    """Decode a VIN using NHTSA vPIC API."""
    try:
        return await nhtsa_client.decode_vin(req.vin)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Structured Fitment
# ---------------------------------------------------------------------------


@router.post("/fitment", response_model=FitmentResponse)
async def get_fitment(req: FitmentRequest):
    """Get Kansei wheel recommendations for a vehicle."""

    # --- Resolve bolt pattern + hub bore ---
    bolt_pattern = req.bolt_pattern
    hub_bore = req.hub_bore

    # Try the quick-lookup table first (has both bolt_pattern and hub_bore)
    quick_specs = lookup_vehicle_specs(req.make, req.model, req.year, trim=req.trim)
    if quick_specs:
        if not bolt_pattern:
            bolt_pattern = quick_specs["bolt_pattern"]
        if hub_bore is None:
            hub_bore = quick_specs.get("hub_bore")

    # Fall back to the full knowledge base
    kb_specs: dict[str, Any] | None = None
    if not bolt_pattern:
        kb_specs = lookup_known_specs(req.make, req.model, year=req.year)
        if kb_specs:
            bolt_pattern = kb_specs.get("bolt_pattern")
            if hub_bore is None:
                hub_bore = kb_specs.get("center_bore")

    if not bolt_pattern:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Could not determine bolt pattern for {req.year} {req.make} {req.model}. "
                "Please provide bolt_pattern manually."
            ),
        )

    # --- Early rejection: bolt pattern not in catalog ---
    available_patterns = get_unique_bolt_patterns()
    if bolt_pattern.upper() not in [p.upper() for p in available_patterns]:
        raise HTTPException(
            status_code=422,
            detail=(
                f"No Kansei wheels available in bolt pattern {bolt_pattern}. "
                f"Available patterns: {', '.join(sorted(available_patterns))}"
            ),
        )

    # Build vehicle specs — use quick_specs first, then knowledge base for defaults
    if kb_specs is None:
        kb_specs = lookup_known_specs(req.make, req.model, year=req.year)

    vehicle_kwargs: dict[str, Any] = {
        "year": req.year,
        "make": req.make,
        "model": req.model,
        "trim": req.trim,
        "bolt_pattern": bolt_pattern,
        "hub_bore": hub_bore,
        "oem_diameter": req.oem_diameter
        or (quick_specs.get("oem_diameter_front") if quick_specs else None)
        or (kb_specs.get("oem_diameter") if kb_specs else 17.0),
        "oem_width": (quick_specs.get("oem_width_front") if quick_specs else None)
        or (kb_specs.get("oem_width") if kb_specs else None),
        "oem_offset": req.oem_offset
        or (quick_specs.get("oem_offset_front") if quick_specs else None)
        or (kb_specs.get("oem_offset") if kb_specs else None),
    }

    # Populate new fields from quick_specs if available
    if quick_specs:
        vehicle_kwargs.update(
            {
                "chassis_code": quick_specs.get("chassis_code"),
                "oem_diameter_front": quick_specs.get("oem_diameter_front"),
                "oem_diameter_rear": quick_specs.get("oem_diameter_rear"),
                "oem_width_front": quick_specs.get("oem_width_front"),
                "oem_width_rear": quick_specs.get("oem_width_rear"),
                "oem_offset_front": quick_specs.get("oem_offset_front"),
                "oem_offset_rear": quick_specs.get("oem_offset_rear"),
                "oem_tire_front": quick_specs.get("oem_tire_front"),
                "oem_tire_rear": quick_specs.get("oem_tire_rear"),
                "front_brake_size": quick_specs.get("front_brake_size"),
                "min_wheel_diameter": quick_specs.get("min_wheel_diameter"),
                "is_staggered_stock": quick_specs.get("is_staggered_stock", False),
                "is_performance_trim": quick_specs.get("is_performance_trim", False),
            }
        )

    vehicle = VehicleSpecs(**vehicle_kwargs)

    # Query Kansei catalog
    wheels = find_wheels_by_bolt_pattern(
        bolt_pattern=bolt_pattern,
        category=req.category,
    )

    if not wheels:
        raise HTTPException(
            status_code=404,
            detail=f"No Kansei wheels found for bolt pattern {bolt_pattern}",
        )

    # Score each wheel
    results = [score_fitment(w, vehicle) for w in wheels]
    results.sort(key=lambda r: r.fitment_score, reverse=True)

    # Generate AI summary
    agent = get_fitment_agent()
    top_5 = results[:5]
    summary_result = agent(
        user_message=(
            f"Summarize the top wheel recommendations for a "
            f"{req.year} {req.make} {req.model} with bolt pattern {bolt_pattern}. "
            f"Top options: {json.dumps([r.wheel.model_dump() for r in top_5], default=str)}"
        ),
    )

    # Determine hub ring status (per-wheel bore varies by product line,
    # so we report status for the most common street bore 73.1mm as a summary)
    hub_ring_status: str | None = None
    if hub_bore is not None and results:
        # Use the first wheel's bore as representative for the summary
        representative_bore = results[0].wheel.center_bore
        if representative_bore == hub_bore:
            hub_ring_status = "not needed — perfect hub-centric fit"
        elif representative_bore > hub_bore:
            hub_ring_status = f"required — {hub_bore}mm to {representative_bore}mm"
        else:
            hub_ring_status = (
                f"incompatible — wheel bore ({representative_bore}mm) smaller "
                f"than hub ({hub_bore}mm); see per-wheel details"
            )

    return FitmentResponse(
        vehicle_year=req.year,
        vehicle_make=req.make,
        vehicle_model=req.model,
        vehicle_trim=req.trim,
        bolt_pattern=bolt_pattern,
        chassis_code=vehicle.chassis_code,
        hub_bore_mm=hub_bore,
        hub_ring_status=hub_ring_status,
        suspension_type=vehicle.suspension_type,
        is_staggered_stock=vehicle.is_staggered_stock,
        recommendations=results[:20],
        total_options=len(results),
        ai_summary=summary_result.response,
    )


# ---------------------------------------------------------------------------
# Makes / Models / Catalog
# ---------------------------------------------------------------------------


@router.get("/makes")
async def get_makes():
    """Get all vehicle makes from NHTSA."""
    try:
        makes = await nhtsa_client.get_all_makes()
        return {"makes": [m.get("Make_Name") for m in makes]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/models/{make}/{year}")
async def get_models(make: str, year: int):
    """Get models for a make and year from NHTSA."""
    try:
        models = await nhtsa_client.get_models_for_make_year(make, year)
        return {"models": [m.get("Model_Name") for m in models]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/catalog/bolt-patterns")
async def get_bolt_patterns():
    """Get all bolt patterns available in the Kansei catalog."""
    patterns = get_unique_bolt_patterns()
    return {"bolt_patterns": patterns}
