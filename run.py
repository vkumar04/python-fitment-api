import os

import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    # Single worker: FastAPI is fully async so concurrency comes from the
    # event loop, not from forking.  Multiple workers cause fork-safety
    # issues with asyncio primitives (Semaphore, event loops) and
    # singleton state (Supabase client, DSPy pipeline) on Linux.
    workers = int(os.environ.get("WEB_CONCURRENCY", 1))
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        workers=workers,
    )
