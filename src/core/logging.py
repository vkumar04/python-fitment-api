"""Structured logging configuration."""

import logging
import sys
from typing import Any


def setup_logging(level: str = "INFO") -> logging.Logger:
    """Configure structured logging for the application."""
    # Create logger
    logger = logging.getLogger("fitment_api")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Avoid duplicate handlers
    if logger.handlers:
        return logger

    # Console handler with structured format
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)

    # Format: timestamp - level - module - message
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger


# Global logger instance
logger = setup_logging()


def log_request(method: str, path: str, **kwargs: Any) -> None:
    """Log an incoming request."""
    extra = " ".join(f"{k}={v}" for k, v in kwargs.items())
    logger.info(f"REQUEST {method} {path} {extra}".strip())


def log_response(method: str, path: str, status: int, duration_ms: float) -> None:
    """Log an outgoing response."""
    logger.info(
        f"RESPONSE {method} {path} status={status} duration_ms={duration_ms:.2f}"
    )


def log_error(message: str, exc: Exception | None = None, **kwargs: Any) -> None:
    """Log an error with optional exception."""
    extra = " ".join(f"{k}={v}" for k, v in kwargs.items())
    if exc:
        logger.error(f"ERROR {message} {extra}".strip(), exc_info=exc)
    else:
        logger.error(f"ERROR {message} {extra}".strip())


def log_db_query(operation: str, table: str, duration_ms: float | None = None) -> None:
    """Log a database operation."""
    duration = f"duration_ms={duration_ms:.2f}" if duration_ms else ""
    logger.debug(f"DB {operation} table={table} {duration}".strip())


def log_external_call(
    service: str, operation: str, success: bool, duration_ms: float | None = None
) -> None:
    """Log an external service call."""
    status = "success" if success else "failed"
    duration = f"duration_ms={duration_ms:.2f}" if duration_ms else ""
    logger.info(f"EXTERNAL {service} {operation} status={status} {duration}".strip())
