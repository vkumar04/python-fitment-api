from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
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


class Message(BaseModel):
    role: str  # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    query: str
    messages: list[Message] | None = None  # Conversation history for context


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
        # Convert messages to list of dicts for the service
        history = None
        if request.messages:
            history = [{"role": m.role, "content": m.content} for m in request.messages]

        result = rag_service.ask(query=request.query, history=history)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    Streaming chat endpoint - Vercel AI SDK compatible.

    Uses the Vercel AI SDK Data Stream Protocol with SSE format.
    Set streamProtocol: 'data' in useChat() options.

    Event types:
    - text-start: Start of text response
    - text-delta: Incremental text content
    - text-end: End of text response
    - data-metadata: Custom data (sources, parsed info, kansei matches)
    - finish: Stream complete

    Example with Vercel AI SDK (Next.js):
    ```typescript
    import { useChat } from 'ai/react';

    export default function Chat() {
      const { messages, input, handleInputChange, handleSubmit, data } = useChat({
        api: '/api/chat/stream',
        streamProtocol: 'data',
      });

      return (
        <form onSubmit={handleSubmit}>
          <input value={input} onChange={handleInputChange} />
          <button type="submit">Send</button>
          {messages.map(m => <div key={m.id}>{m.content}</div>)}
        </form>
      );
    }
    ```

    Example with raw fetch:
    ```javascript
    const response = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: 'What wheels fit a 2020 Honda Civic?' })
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const text = decoder.decode(value);
        for (const line of text.split('\\n\\n')) {
            if (line.startsWith('data: ')) {
                const event = JSON.parse(line.slice(6));
                switch (event.type) {
                    case 'text-delta':
                        console.log(event.delta); // Append to display
                        break;
                    case 'data-metadata':
                        console.log('Metadata:', event.data);
                        break;
                    case 'finish':
                        console.log('Stream complete');
                        break;
                }
            }
        }
    }
    ```
    """
    try:
        # Convert messages to list of dicts for the service
        history = None
        if request.messages:
            history = [{"role": m.role, "content": m.content} for m in request.messages]

        return StreamingResponse(
            rag_service.ask_streaming(query=request.query, history=history),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "x-vercel-ai-data-stream": "v1",  # Vercel AI SDK header
            },
        )
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
