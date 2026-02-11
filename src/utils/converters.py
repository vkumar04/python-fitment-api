"""Type conversion utilities for safely handling data from CSV/database.

This module is the single source of truth for safe type conversion.
All other modules should import from here instead of defining their own.
"""

from typing import Any


def safe_float(val: Any, default: float = 0.0) -> float:
    """Safely convert a value to float.

    Args:
        val: Value to convert (can be str, int, float, None, etc.)
        default: Value to return if conversion fails

    Returns:
        Converted float or default value

    Examples:
        >>> safe_float("3.14")
        3.14
        >>> safe_float(None)
        0.0
        >>> safe_float("invalid", default=-1.0)
        -1.0
    """
    if val is None or val == "":
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def safe_int(val: Any, default: int = 0) -> int:
    """Safely convert a value to int.

    Args:
        val: Value to convert (can be str, int, float, None, etc.)
        default: Value to return if conversion fails

    Returns:
        Converted int or default value

    Examples:
        >>> safe_int("42")
        42
        >>> safe_int(3.7)
        3
        >>> safe_int(None)
        0
    """
    if val is None or val == "":
        return default
    try:
        return int(float(val))  # Handle "3.0" -> 3
    except (ValueError, TypeError):
        return default
