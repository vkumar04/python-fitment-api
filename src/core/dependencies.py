"""FastAPI dependency injection for services."""

import time
from functools import lru_cache
from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException, Request
from openai import OpenAI

from supabase import Client, create_client

from .config import Settings, get_settings
from .logging import log_db_query, log_external_call, logger

# -----------------------------------------------------------------------------
# Supabase Client
# -----------------------------------------------------------------------------

# Cached client instance
_supabase_client: Client | None = None


def get_supabase(
    settings: Annotated[Settings, Depends(get_settings)],
) -> Client:
    """Dependency for Supabase client."""
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = create_client(settings.supabase_url, settings.supabase_key)
    return _supabase_client


# -----------------------------------------------------------------------------
# OpenAI Client
# -----------------------------------------------------------------------------


@lru_cache
def get_openai_client(api_key: str) -> OpenAI:
    """Get cached OpenAI client."""
    return OpenAI(api_key=api_key)


def get_openai(
    settings: Annotated[Settings, Depends(get_settings)],
) -> OpenAI:
    """Dependency for OpenAI client."""
    return get_openai_client(settings.openai_api_key)


# -----------------------------------------------------------------------------
# Admin Authentication
# -----------------------------------------------------------------------------


async def verify_admin_key(
    request: Request,
    x_admin_key: Annotated[str | None, Header()] = None,
    settings: Settings = Depends(get_settings),
) -> bool:
    """Verify admin API key for protected endpoints."""
    if not settings.api_admin_key:
        logger.warning("API_ADMIN_KEY not set - admin endpoints unprotected")
        raise HTTPException(
            status_code=503,
            detail="Admin endpoints not configured. Set API_ADMIN_KEY environment variable.",
        )

    if not x_admin_key:
        raise HTTPException(
            status_code=401,
            detail="Missing X-Admin-Key header",
        )

    if x_admin_key != settings.api_admin_key:
        logger.warning(f"Invalid admin key attempt from {request.client}")
        raise HTTPException(
            status_code=403,
            detail="Invalid admin key",
        )

    return True


# -----------------------------------------------------------------------------
# Health Check Helpers
# -----------------------------------------------------------------------------


async def check_supabase_health(supabase: Client) -> dict[str, Any]:
    """Check Supabase connectivity."""
    start = time.time()
    try:
        supabase.table("fitments").select("id").limit(1).execute()
        duration_ms = (time.time() - start) * 1000
        log_db_query("health_check", "fitments", duration_ms)
        return {
            "status": "healthy",
            "latency_ms": round(duration_ms, 2),
        }
    except Exception as e:
        duration_ms = (time.time() - start) * 1000
        log_external_call("supabase", "health_check", False, duration_ms)
        return {
            "status": "unhealthy",
            "error": str(e),
            "latency_ms": round(duration_ms, 2),
        }


async def check_openai_health(openai_client: OpenAI) -> dict[str, Any]:
    """Check OpenAI API connectivity."""
    start = time.time()
    try:
        # Simple models list call to verify API key
        openai_client.models.list()
        duration_ms = (time.time() - start) * 1000
        log_external_call("openai", "health_check", True, duration_ms)
        return {
            "status": "healthy",
            "latency_ms": round(duration_ms, 2),
        }
    except Exception as e:
        duration_ms = (time.time() - start) * 1000
        log_external_call("openai", "health_check", False, duration_ms)
        return {
            "status": "unhealthy",
            "error": str(e),
            "latency_ms": round(duration_ms, 2),
        }
