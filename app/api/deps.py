"""FastAPI dependency injection."""

from app.services.nhtsa import nhtsa_client


async def get_nhtsa():
    """Dependency for NHTSA client."""
    return nhtsa_client
