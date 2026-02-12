"""FastAPI app entry point for the Kansei Fitment Assistant."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import get_settings
from app.services.nhtsa import nhtsa_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup / shutdown."""
    yield
    await nhtsa_client.close()


app = FastAPI(
    title="Kansei Fitment Assistant API",
    description="AI-powered wheel fitment recommendations for Kansei Wheels",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "kansei-fitment-assistant"}
