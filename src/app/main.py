from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ..services.rag_service import RAGService

app = FastAPI(
    title="Wheel Fitment RAG API",
    description="API for querying wheel and tire fitment data using RAG",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

rag_service = RAGService()


class ChatRequest(BaseModel):
    query: str


class LoadDataRequest(BaseModel):
    csv_path: str


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.post("/api/chat")
async def chat(request: ChatRequest):
    """
    Chat endpoint - just send a query in natural language.

    The API will:
    1. Use NLP to extract year, make, model, fitment style from your query
    2. Search the fitment database with those filters
    3. Return an AI-generated answer based on the data

    Examples:
    - "What wheels fit a 2020 Honda Civic for a flush look?"
    - "I have a 2018 BMW M3, looking for aggressive fitment"
    - "Best setup for a Chevy Camaro SS?"
    """
    try:
        result = rag_service.ask(query=request.query)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/makes")
async def get_makes():
    """Get all available vehicle makes."""
    try:
        makes = rag_service.get_makes()
        return {"makes": makes}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/models/{make}")
async def get_models(make: str):
    """Get all models for a specific make."""
    try:
        models = rag_service.get_models(make)
        return {"models": models}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/years")
async def get_years():
    """Get all available years."""
    try:
        years = rag_service.get_years()
        return {"years": years}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/load-data")
async def load_data(request: LoadDataRequest):
    """Load fitment data from a CSV file."""
    try:
        count = rag_service.load_csv_data(request.csv_path)
        return {"message": f"Loaded {count} fitment records"}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="CSV file not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
