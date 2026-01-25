"""FastAPI application for Wheel Fitment RAG API."""

import asyncio
import time
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from ..core.config import Settings, get_settings, validate_settings
from ..core.dependencies import (
    check_openai_health,
    check_supabase_health,
    get_openai,
    get_supabase,
    verify_admin_key,
)
from ..core.enums import FitmentStyle
from ..core.logging import log_error, log_request, log_response, logger
from ..services.rag_service import RAGService

# Validate settings on startup
try:
    validate_settings()
except ValueError as e:
    logger.error(f"Configuration error: {e}")
    raise

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

# RAG service singleton
_rag_service: RAGService | None = None


def get_rag_service() -> RAGService:
    """Get or create RAG service instance."""
    global _rag_service
    if _rag_service is None:
        _rag_service = RAGService()
    return _rag_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - initialize services on startup."""
    logger.info("Starting Wheel Fitment RAG API...")
    # Pre-initialize RAG service
    get_rag_service()
    logger.info("RAG service initialized")
    yield
    logger.info("Shutting down...")


app = FastAPI(
    title="Wheel Fitment RAG API",
    description="API for querying wheel and tire fitment data using RAG",
    version="1.0.0",
    lifespan=lifespan,
)

# State for limiter
app.state.limiter = limiter


# Add rate limit error handler
@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    log_error("Rate limit exceeded", client=get_remote_address(request))
    raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again later.")


# CORS middleware - add on startup
@app.on_event("startup")
async def setup_cors():
    settings = get_settings()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-Admin-Key"],
    )


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    log_request(request.method, request.url.path)

    response = await call_next(request)

    duration_ms = (time.time() - start) * 1000
    log_response(request.method, request.url.path, response.status_code, duration_ms)

    return response


# -----------------------------------------------------------------------------
# Request/Response Models
# -----------------------------------------------------------------------------


class Message(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1, max_length=10000)


class ChatRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Natural language query about wheel fitments",
    )
    messages: list[Message] | None = Field(
        default=None,
        max_length=20,
        description="Conversation history for context",
    )


class LoadDataRequest(BaseModel):
    csv_path: str = Field(..., min_length=1)


class HealthResponse(BaseModel):
    status: str
    supabase: dict[str, Any] | None = None
    openai: dict[str, Any] | None = None


# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse)
async def health_check(
    detailed: bool = False,
    supabase=Depends(get_supabase),
    openai_client=Depends(get_openai),
):
    """
    Health check endpoint.

    - Basic: Returns {"status": "healthy"}
    - Detailed (?detailed=true): Checks Supabase and OpenAI connectivity
    """
    if not detailed:
        return {"status": "healthy"}

    # Run health checks concurrently
    supabase_health, openai_health = await asyncio.gather(
        check_supabase_health(supabase),
        check_openai_health(openai_client),
    )

    overall = "healthy"
    if supabase_health["status"] != "healthy" or openai_health["status"] != "healthy":
        overall = "degraded"

    return {
        "status": overall,
        "supabase": supabase_health,
        "openai": openai_health,
    }


@app.post("/api/chat")
@limiter.limit("30/minute")
async def chat_stream(
    request: Request,
    chat_request: ChatRequest,
    settings: Annotated[Settings, Depends(get_settings)],
):
    """
    Streaming chat endpoint - Vercel AI SDK compatible.

    Uses the Vercel AI SDK Data Stream Protocol with SSE format.
    Set streamProtocol: 'data' in useChat() options.

    Rate limited to 30 requests per minute per IP.
    """
    try:
        rag_service = get_rag_service()

        # Convert messages to list of dicts for the service
        history = None
        if chat_request.messages:
            history = [
                {"role": m.role, "content": m.content} for m in chat_request.messages
            ]

        # Create async generator wrapper for StreamingResponse
        async def generate():
            try:
                async for event in rag_service.ask_streaming(
                    query=chat_request.query, history=history
                ):
                    yield event
            except Exception as e:
                log_error("Streaming error", e, query=chat_request.query[:50])
                yield 'data: {"type": "error", "message": "An error occurred"}\n\n'

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "x-vercel-ai-data-stream": "v1",
            },
        )
    except Exception as e:
        log_error("Chat endpoint error", e, query=chat_request.query[:50])
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/makes")
async def get_makes():
    """Get all available vehicle makes."""
    try:
        rag_service = get_rag_service()
        makes = await rag_service.get_makes()
        return {"makes": makes}
    except Exception as e:
        log_error("Failed to get makes", e)
        raise HTTPException(status_code=500, detail="Failed to retrieve makes")


@app.get("/api/models/{make}")
async def get_models(make: str):
    """Get all models for a specific make."""
    try:
        rag_service = get_rag_service()
        models = await rag_service.get_models(make)
        return {"models": models}
    except Exception as e:
        log_error("Failed to get models", e, make=make)
        raise HTTPException(status_code=500, detail="Failed to retrieve models")


@app.get("/api/years")
async def get_years():
    """Get all available years."""
    try:
        rag_service = get_rag_service()
        years = await rag_service.get_years()
        return {"years": years}
    except Exception as e:
        log_error("Failed to get years", e)
        raise HTTPException(status_code=500, detail="Failed to retrieve years")


@app.get("/api/fitment-styles")
async def get_fitment_styles():
    """Get available fitment styles."""
    return {"styles": [style.value for style in FitmentStyle]}


@app.post("/api/load-data")
async def load_data(
    request: LoadDataRequest,
    _admin: Annotated[bool, Depends(verify_admin_key)],
):
    """
    Load fitment data from a CSV file.

    Requires X-Admin-Key header for authentication.
    """
    try:
        rag_service = get_rag_service()
        count = await rag_service.load_csv_data(request.csv_path)
        logger.info(f"Loaded {count} fitment records from {request.csv_path}")
        return {"message": f"Loaded {count} fitment records"}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="CSV file not found")
    except Exception as e:
        log_error("Failed to load data", e, path=request.csv_path)
        raise HTTPException(status_code=500, detail="Failed to load data")
