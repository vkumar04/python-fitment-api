import os

import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    workers = int(os.environ.get("WEB_CONCURRENCY", 4))
    uvicorn.run(
        "src.app.main:app",
        host="0.0.0.0",
        port=port,
        workers=workers,
    )
