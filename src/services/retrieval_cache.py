"""Thread-safe TTL cache for DSPy pipeline retrieval results.

Caches RetrievalResult objects keyed on normalized vehicle info so that
identical vehicle queries skip the expensive pipeline (5-15s per call).
Each uvicorn worker gets its own cache instance (no cross-process sharing).
"""

import logging
import threading
from typing import Any

from cachetools import TTLCache

logger = logging.getLogger(__name__)


class RetrievalCache:
    """TTL cache for pipeline retrieval results.

    Thread-safe via a threading.Lock. Keyed on normalized parsed vehicle
    tuple so that "2020 civic", "2020 Honda Civic", and "honda civic 2020"
    all map to the same cache entry after DSPy parsing.
    """

    def __init__(self, maxsize: int = 256, ttl: int = 1800) -> None:
        """Initialize the cache.

        Args:
            maxsize: Max entries (256 covers most popular vehicles).
            ttl: Time-to-live in seconds (default 30 minutes).
        """
        self._cache: TTLCache[tuple[Any, ...], Any] = TTLCache(
            maxsize=maxsize, ttl=ttl
        )
        self._lock = threading.Lock()

    @staticmethod
    def make_key(parsed: dict[str, Any]) -> tuple[Any, ...]:
        """Build a cache key from parsed vehicle info.

        Keys on (year, make, model, chassis_code, fitment_style, suspension).
        All string values are lowered/stripped for normalization.
        Trim is excluded because it gets merged into model by the pipeline.
        """

        def _norm(val: Any) -> str | None:
            if val is None:
                return None
            s = str(val).lower().strip()
            return s if s else None

        return (
            parsed.get("year"),  # int or None
            _norm(parsed.get("make")),
            _norm(parsed.get("model")),
            _norm(parsed.get("chassis_code")),
            _norm(parsed.get("fitment_style")),
            _norm(parsed.get("suspension")),
        )

    def get(self, key: tuple[Any, ...]) -> Any | None:
        """Get a cached result (thread-safe). Returns None on miss."""
        with self._lock:
            return self._cache.get(key)

    def set(self, key: tuple[Any, ...], value: Any) -> None:
        """Store a result in the cache (thread-safe)."""
        with self._lock:
            self._cache[key] = value
        logger.debug("Retrieval cache set: %s", key)
