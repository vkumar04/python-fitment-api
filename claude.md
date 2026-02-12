# Kansei Fitment Assistant API

AI-powered wheel fitment recommendation engine for Kansei Wheels. Uses DSPy ReAct agent for conversational queries, NHTSA vPIC API for VIN decoding, and a fitment scoring engine for structured recommendations.

## Quick Reference

```bash
uv sync                                          # Install dependencies
uv run uvicorn app.main:app --reload --port 8000  # Dev server
uv run pytest tests/                              # Run tests
uv run ruff check app/                            # Lint
uv run pyright app/                               # Type check
```

## Tech Stack

- **Python 3.12** with **uv** for package management
- **FastAPI** (async endpoints)
- **Supabase** (PostgreSQL) for Kansei wheel catalog, vehicle specs, community fitments
- **DSPy** ReAct agent for conversational fitment assistance
- **NHTSA vPIC API** for VIN decoding and make/model lookups
- **httpx** for async HTTP

## Project Structure

```
python-rag/
├── app/
│   ├── main.py                      # FastAPI app entry point
│   ├── config.py                    # Pydantic settings & env vars
│   ├── models/
│   │   ├── vehicle.py               # VehicleIdentification, VehicleSpecs
│   │   ├── wheel.py                 # KanseiWheel
│   │   └── fitment.py               # FitmentResult, FitmentResponse
│   ├── services/
│   │   ├── db.py                    # Supabase client singleton
│   │   ├── kansei_db.py             # Kansei wheel + vehicle spec queries
│   │   ├── nhtsa.py                 # NHTSA vPIC async client
│   │   └── fitment_engine.py        # Scoring engine + vehicle knowledge base
│   ├── dspy_modules/
│   │   ├── signatures.py            # IdentifyVehicle, RecommendWheels, FitmentQA
│   │   └── conversational.py        # KanseiFitmentAgent (ReAct)
│   ├── api/
│   │   ├── routes.py                # All API route definitions
│   │   └── deps.py                  # Dependency injection
│   └── tools/
│       └── nhtsa_tools.py           # Sync tool wrappers for DSPy
├── tests/
│   └── test_fitment_engine.py       # Knowledge base + scoring tests
├── supabase/
│   └── migrations/                  # Database schema (canonical)
├── run.py                           # Production entry point
├── pyproject.toml
├── Dockerfile
├── nixpacks.toml
└── railway.toml
```

## Architecture

### Request Flow

```
POST /api/v1/chat     → DSPy ReAct agent (tools: VIN decode, wheel search)
POST /api/v1/fitment  → Knowledge base → Kansei DB query → Score wheels → AI summary
POST /api/v1/decode-vin → NHTSA vPIC API
GET  /api/v1/makes     → NHTSA API
GET  /api/v1/models/{make}/{year} → NHTSA API
GET  /api/v1/catalog/bolt-patterns → Supabase
```

### Key Design Decisions

- **Spec resolution order**: hardcoded knowledge base (300+ vehicles) → Supabase DB → NHTSA API
- **Fitment scoring**: 0.0–1.0 score based on offset delta, diameter delta, width, hub bore
- **Supabase client** is a lazy singleton (`app/services/db.py`)
- **DSPy ReAct agent** uses tools for VIN decode, model lookup, and wheel search
- **Knowledge base** in `fitment_engine.py` covers BMW (E21–G82), Honda, Subaru, Toyota, Nissan, Mazda, Mitsubishi, VW, Audi, Mercedes, Porsche, Ford, Chevy, Dodge, Ram, Tesla, Datsun

## Environment Variables

```bash
# Required
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_anon_key

# LLM (at least one required)
OPENAI_API_KEY=your_openai_api_key
ANTHROPIC_API_KEY=your_anthropic_key    # Optional

# Optional
DSPY_MODEL=openai/gpt-4o               # Or anthropic/claude-sonnet-4-20250514
NHTSA_BASE_URL=https://vpic.nhtsa.dot.gov/api
ALLOWED_ORIGINS=*
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/api/v1/chat` | Conversational fitment assistant (DSPy ReAct) |
| `POST` | `/api/v1/fitment` | Structured fitment with scoring |
| `POST` | `/api/v1/decode-vin` | VIN decode via NHTSA |
| `GET` | `/api/v1/makes` | All vehicle makes (NHTSA) |
| `GET` | `/api/v1/models/{make}/{year}` | Models for make+year (NHTSA) |
| `GET` | `/api/v1/catalog/bolt-patterns` | Kansei catalog bolt patterns |

## Database (Supabase)

Three tables in PostgreSQL:

- **`kansei_wheels`** (484 rows) — Kansei product catalog (model, finish, sku, diameter, width, bolt_pattern, wheel_offset, price, category, url, in_stock, weight)
- **`vehicle_specs`** (50+ rows) — Verified vehicle specs with bolt pattern, center bore, offset/diameter/width ranges
- **`fitments`** (54k+ rows) — Community fitment data with full-text search

PostgreSQL functions: `search_fitments`, `find_vehicle_specs`, `upsert_vehicle_specs`, `get_makes`, `get_models`, `get_years`

Schema in `supabase/migrations/`.

## Testing

```bash
uv run pytest tests/                            # All tests
uv run pytest tests/test_fitment_engine.py -v   # Knowledge base + scoring (no API key needed)
```

## Deployment (Railway)

- `nixpacks.toml` configures build (`uv sync --frozen`)
- `run.py` reads `PORT` from environment
- `Dockerfile` available as alternative
- Health check at `/health`
