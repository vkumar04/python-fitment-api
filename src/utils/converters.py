"""Type conversion utilities for safely handling data from CSV/database."""

from typing import Any


def safe_float(val: Any) -> float:
    """Safely convert a value to float."""
    try:
        return float(val) if val != "" else 0.0
    except (ValueError, TypeError):
        return 0.0


def safe_int(val: Any) -> int:
    """Safely convert a value to int."""
    try:
        return int(float(val)) if val != "" else 0
    except (ValueError, TypeError):
        return 0
