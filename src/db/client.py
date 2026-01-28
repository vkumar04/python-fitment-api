"""Shared Supabase client - single lazy-loaded instance for the entire app."""

import threading

from supabase import Client, create_client

from ..core.config import get_settings

_supabase: Client | None = None
_client_lock = threading.Lock()


def get_supabase_client() -> Client:
    """Get or create the shared Supabase client (thread-safe)."""
    global _supabase
    if _supabase is None:
        with _client_lock:
            if _supabase is None:
                settings = get_settings()
                _supabase = create_client(settings.supabase_url, settings.supabase_key)
    return _supabase
