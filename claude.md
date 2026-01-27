# Wheel Fitment RAG API

Python FastAPI app using RAG to help customers find wheel/tire fitments. DSPy pipeline parses queries and retrieves context, OpenAI streams the final response.

## Quick Reference

```bash
uv sync                                              # Install dependencies
uv run uvicorn src.app.main:app --reload --port 8000  # Dev server
uv run pytest tests/                                  # Run tests (needs OPENAI_API_KEY)
uv run ruff check src/                                # Lint
uv run pyright src/                                   # Type check
```

## Tech Stack

- **Python 3.12** with **uv** for package management
- **FastAPI** (fully async endpoints)
- **Supabase** (PostgreSQL + pgvector) for storage and full-text search
- **OpenAI** for streaming chat responses (`AsyncOpenAI`)
- **DSPy** for structured query parsing and vehicle spec resolution
- **slowapi** for rate limiting

## Project Structure

```
python-rag/
├── src/
│   ├── app/
│   │   └── main.py                  # FastAPI app, endpoints, request models
│   ├── core/
│   │   ├── config.py                # Pydantic settings & env validation
│   │   ├── dependencies.py          # FastAPI dependency injection
│   │   ├── enums.py                 # FitmentStyle, SuspensionType enums
│   │   └── logging.py              # Structured logging
│   ├── db/
│   │   ├── client.py               # Supabase client singleton
│   │   └── fitments.py             # Async Supabase queries
│   ├── models/
│   │   └── fitment.py              # Pydantic models (FitmentData, FitmentQuery, etc.)
│   ├── services/
│   │   ├── rag_service.py          # Orchestrates DSPy retrieval + OpenAI streaming
│   │   ├── fitment.py              # Fitment classification utilities
│   │   ├── kansei_scraper.py       # Kansei wheel catalog scraping
│   │   ├── wheel_size_lookup.py    # OEM specs from wheel-size.com
│   │   └── dspy_v2/               # Core DSPy pipeline
│   │       ├── pipeline.py         # FitmentPipeline: parse → resolve → validate → fetch
│   │       ├── signatures.py       # DSPy signatures (ParseVehicleInput, etc.)
│   │       ├── tools.py            # Knowledge base + web scraping for vehicle specs
│   │       └── db.py               # Database queries used by pipeline
│   ├── prompts/
│   │   └── fitment_assistant.py    # System prompts for OpenAI
│   └── utils/
│       └── converters.py           # Type conversion utilities
├── tests/
│   ├── test_fitment_queries.py     # Integration tests (requires running server)
│   ├── test_dspy_pipeline.py       # Unit tests for DSPy pipeline
│   └── test_bolt_patterns.py       # Bolt pattern validation tests
├── datafiles/
│   ├── Fitment-data-master.csv     # Community fitment data (54k+ records)
│   ├── kansei_wheels.json          # Scraped Kansei wheel catalog
│   └── wheel_size_cache.json       # Cached OEM specs from wheel-size.com
├── supabase/
│   └── migrations/                 # Database migrations
├── supabase_setup.sql              # Database schema + indexes
├── run.py                          # Production entry point (reads PORT env)
├── pyproject.toml
├── Dockerfile
├── nixpacks.toml                   # Railway build config
└── railway.toml
```

## Architecture

### Request Flow

```
POST /api/chat → RAGService.ask_streaming()
  1. DSPy pipeline (sync, runs in asyncio.to_thread):
     ParseVehicleInput → ResolveSpecs → ValidateSpecs → FetchData
  2. OpenAI streams response using retrieved context (AsyncOpenAI)
  3. SSE events sent to client (Vercel AI SDK Data Stream Protocol)
```

### Key Design Decisions

- **DSPy pipeline is synchronous** — runs inside `asyncio.to_thread()` since DSPy doesn't support async
- **Spec resolution order**: hardcoded knowledge base → wheel-size.com scraping → LLM fallback
- **Supabase client** is a lazy singleton (`src/db/client.py`)
- **LRU caching** on query parsing to avoid redundant LLM calls
- **Full-text search** via PostgreSQL tsvector (not vector embeddings)

## Environment Variables

```bash
# Required
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_anon_key
OPENAI_API_KEY=your_openai_api_key

# Optional
OPENAI_MODEL=gpt-4o-mini          # Model for chat responses
OPENAI_MAX_TOKENS=512             # Max tokens per response
DSPY_MODEL=openai/gpt-4o          # Model for DSPy pipeline
API_ADMIN_KEY=your_admin_key      # Required for /api/load-data
ALLOWED_ORIGINS=http://localhost:3000,https://yourapp.com
RATE_LIMIT_REQUESTS=30            # Per period per IP
RATE_LIMIT_PERIOD=60              # Period in seconds
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Basic health check (`?detailed=true` checks Supabase + OpenAI) |
| `POST` | `/api/chat` | Streaming chat (SSE, Vercel AI SDK compatible, 30 req/min) |
| `GET` | `/api/makes` | All vehicle makes |
| `GET` | `/api/models/{make}` | Models for a make |
| `GET` | `/api/years` | All years |
| `GET` | `/api/fitment-styles` | Fitment style enum values |
| `POST` | `/api/load-data` | Load CSV data (requires `X-Admin-Key` header) |

## Database

The `fitments` table uses PostgreSQL full-text search:

- Vehicle ID: `year`, `make`, `model`
- Wheel specs: `front_*` / `rear_*` (diameter, width, offset, backspacing, spacer)
- Tires: `tire_front`, `tire_rear`
- Classification: `fitment_setup` (square/staggered), `fitment_style` (aggressive/flush/tucked)
- Flags: `has_poke`, `needs_mods`
- Search: `fts` generated tsvector column

Composite indexes on `(year, make, model)`, `(make, model)`, `(make, fitment_style)`, `(year, fitment_style)`.

Schema defined in `supabase_setup.sql`. Migrations in `supabase/migrations/`.

## Testing

Tests require `OPENAI_API_KEY`. Integration tests in `test_fitment_queries.py` make HTTP calls to a running server.

```bash
uv run pytest tests/                        # All tests
uv run pytest tests/test_bolt_patterns.py   # Just bolt pattern tests (no API key needed)
uv run pytest tests/test_dspy_pipeline.py   # Pipeline unit tests
```

## Deployment (Railway)

- `nixpacks.toml` configures the build (`uv sync --frozen`)
- `run.py` is the entry point, reads `PORT` from environment
- `Dockerfile` available as alternative build path
- Auto-deploys on push to main
- Supabase `pg_cron` pings `/health` every 5 minutes to prevent free tier sleep

## Development Notes

- Run `uv run ruff check src/` and `uv run pyright src/` before committing
- Frontend (Next.js) should set `streamProtocol: 'data'` in `useChat()`
- 54,570 community fitment records in the database
- `wheel_size_cache.json` caches OEM specs to avoid repeated scraping
