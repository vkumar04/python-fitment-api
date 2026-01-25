# Wheel Fitment RAG API

A Python FastAPI application that uses RAG (Retrieval Augmented Generation) to help customers find wheel and tire fitments for their vehicles.

## Tech Stack

- **Python 3.12** with **uv** for package management
- **FastAPI** for the REST API (fully async)
- **Supabase** (PostgreSQL + pgvector) for storage and full-text search
- **OpenAI** for AI responses (async streaming)
- **DSPy** for structured query parsing
- **slowapi** for rate limiting

## Project Structure

```
python-rag/
├── src/
│   ├── app/
│   │   └── main.py              # FastAPI app and endpoints
│   ├── core/
│   │   ├── config.py            # Pydantic settings & env validation
│   │   ├── dependencies.py      # FastAPI dependency injection
│   │   ├── enums.py             # FitmentStyle, SuspensionType enums
│   │   └── logging.py           # Structured logging
│   ├── chat/
│   │   ├── context.py           # Vehicle context parsing (LRU cached)
│   │   └── streaming.py         # Async SSE streaming utilities
│   ├── db/
│   │   └── fitments.py          # Async Supabase operations
│   ├── services/
│   │   ├── rag_service.py       # Async RAG orchestration
│   │   ├── kansei.py            # Kansei wheel matching (indexed lookup)
│   │   ├── dspy_fitment.py      # DSPy query parsing
│   │   ├── validation.py        # Vehicle specs validation
│   │   └── fitment.py           # Fitment classification utilities
│   ├── prompts/
│   │   └── fitment_assistant.py # System prompts for LLM
│   └── utils/
│       └── converters.py        # Type conversion utilities
├── datafiles/
│   ├── Fitment-data-master.csv  # Community fitment data (54k+ records)
│   └── kansei_wheels.json       # Scraped Kansei wheel catalog
├── supabase/
│   └── migrations/              # Database migrations
├── pyproject.toml
├── railway.toml
└── .env
```

## Environment Variables

```bash
# Required
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_anon_key
OPENAI_API_KEY=your_openai_api_key

# Optional
OPENAI_MODEL=gpt-4o-mini          # Model for chat responses
OPENAI_MAX_TOKENS=512             # Max tokens per response
DSPY_MODEL=openai/gpt-4o          # Model for query parsing
API_ADMIN_KEY=your_admin_key      # Required for /api/load-data
ALLOWED_ORIGINS=http://localhost:3000,https://yourapp.com
RATE_LIMIT_REQUESTS=30            # Requests per period
RATE_LIMIT_PERIOD=60              # Period in seconds
```

## Running the App

```bash
# Install dependencies
uv sync

# Run database migrations (requires supabase CLI and login)
supabase link --project-ref your-project-ref
supabase db push

# Run the development server
uv run uvicorn src.app.main:app --reload --port 8000
```

## Database Schema

The `fitments` table stores community fitment data with full-text search:

- `id`, `year`, `make`, `model` - Vehicle identification
- `front_*` / `rear_*` - Wheel specs (diameter, width, offset, backspacing, spacer)
- `tire_front` / `tire_rear` - Tire sizes
- `fitment_setup` - 'square' or 'staggered'
- `fitment_style` - 'aggressive', 'flush', or 'tucked'
- `has_poke`, `needs_mods` - Fitment characteristics
- `document` - Full-text searchable content
- `fts` - Generated tsvector column for PostgreSQL full-text search

### Indexes

Composite indexes for performance:
- `(year, make, model)` - Exact vehicle lookups
- `(make, model)` - Searches without year
- `(make, fitment_style)` - Style-filtered searches
- `(year, fitment_style)` - Year + style filtering

## API Endpoints

### Health Check
- `GET /health` - Basic health check
- `GET /health?detailed=true` - Checks Supabase and OpenAI connectivity

### Chat Endpoint
- `POST /api/chat` - Async streaming chat (Vercel AI SDK compatible)
  - Rate limited: 30 requests/minute per IP
  - Input validation: query 1-1000 chars, max 20 history messages

### Data Endpoints
- `GET /api/makes` - Get all vehicle makes
- `GET /api/models/{make}` - Get models for a make
- `GET /api/years` - Get all years
- `GET /api/fitment-styles` - Get fitment styles
- `POST /api/load-data` - Load CSV data (requires X-Admin-Key header)

## Architecture

### Async Throughout
- All database operations use `asyncio.to_thread()` for non-blocking I/O
- OpenAI streaming uses `AsyncOpenAI` client
- Endpoints are fully async

### Caching
- Query parsing uses `@lru_cache(maxsize=1000)` to avoid redundant LLM calls
- Supabase client is lazily initialized and reused

### Rate Limiting
- slowapi middleware limits `/api/chat` to 30 requests/minute per IP
- Returns 429 on limit exceeded

### Logging
- Structured logging with request/response timing
- Database query logging with duration
- External service call logging (OpenAI, Supabase)

### Security
- CORS restricted to configured origins (not `*`)
- Admin endpoints protected with `X-Admin-Key` header
- Input validation via Pydantic models
- Rate limiting to prevent abuse

## Railway Deployment

### Environment Variables (set in Railway dashboard)
```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_anon_key
OPENAI_API_KEY=your_openai_api_key
API_ADMIN_KEY=your_secret_admin_key
ALLOWED_ORIGINS=https://yourfrontend.com
```

### Deploy Steps
1. Push code to GitHub
2. Create new Railway project from GitHub repo
3. Add environment variables
4. Railway auto-deploys on push to main

### Keep-Alive Cron
A Supabase pg_cron job pings `/health` every 5 minutes to prevent Railway free tier sleep:
```sql
select cron.schedule('ping-railway-health', '*/5 * * * *',
  $$ select net.http_get('https://fitmentbot.up.railway.app/health'); $$
);
```

## Notes for Development

- Run `uv run ruff check src/` and `uv run pyright src/` before committing
- Frontend (Next.js) should set `streamProtocol: 'data'` in useChat()
- Uses PostgreSQL full-text search instead of vector embeddings
- 54,570 community fitment records loaded
