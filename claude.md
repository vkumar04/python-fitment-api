# Wheel Fitment RAG API

A Python FastAPI application that uses RAG (Retrieval Augmented Generation) to help customers find wheel and tire fitments for their vehicles.

## Tech Stack

- **Python 3.12** with **uv** for package management
- **FastAPI** for the REST API
- **Supabase** (PostgreSQL + pgvector) for storage and full-text search
- **OpenAI** for AI responses

## Project Structure

```
python-rag/
├── src/
│   ├── app/
│   │   └── main.py              # FastAPI app and endpoints
│   ├── services/
│   │   ├── rag_service.py       # RAG logic with Supabase
│   │   ├── wheel_matcher.py     # Kansei wheel matching service
│   │   ├── kansei_scraper.py    # Scraper for Kansei wheels
│   │   └── wheel_size_lookup.py # OEM specs lookup from wheel-size.com
│   ├── models/
│   └── utils/
├── datafiles/
│   ├── Fitment-data-master.csv  # Community fitment data (54k+ records)
│   └── kansei_wheels.json       # Scraped Kansei wheel catalog
├── supabase/
│   └── migrations/              # Database migrations
├── pyproject.toml
└── .env
```

## Environment Variables

```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_anon_key
OPENAI_API_KEY=your_openai_api_key
```

## Running the App

```bash
# Install dependencies
uv sync

# Run database migrations (requires supabase CLI and login)
supabase link --project-ref your-project-ref
supabase db push

# Load data into Supabase (first time only)
uv run python -c "from src.services.rag_service import RAGService; RAGService().load_csv_data('datafiles/Fitment-data-master.csv')"

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

## Fitment Terminology

### Fitment Setup
- **Square**: Same wheel size front and rear
- **Staggered**: Different wheel sizes front vs rear (common on RWD performance cars)

### Fitment Style
- **Aggressive**: Low offset wheels that poke past the fender (offset < 15, width >= 9")
- **Flush**: Wheels sit close to the fender line (offset 15-40)
- **Tucked**: Wheels sit inside the fender (offset >= 40)

### Key Measurements
- **Offset (ET)**: Distance from wheel centerline to mounting surface (mm)
- **Backspacing**: Distance from back of wheel to mounting surface (inches)
- **Poke**: When the wheel/tire extends past the fender
- **Spacers**: Used to push wheels outward for a more aggressive look

## API Endpoints

### Health Check
- `GET /health` - Check if the API is running

### Chat Endpoint
- `POST /api/chat` - Natural language chat endpoint (main endpoint)

### Data Endpoints
- `GET /api/makes` - Get all vehicle makes
- `GET /api/models/{make}` - Get models for a make
- `GET /api/years` - Get all years
- `GET /api/fitment-styles` - Get fitment styles (aggressive, flush, tucked)
- `GET /api/fitment-setups` - Get fitment setups (square, staggered)
- `POST /api/load-data` - Load fitment data from CSV

## Request/Response Examples

### Chat (Natural Language)
The `/api/chat` endpoint accepts natural language queries. OpenAI extracts vehicle info (year, make, model, fitment style) automatically.

```json
POST /api/chat
{
  "query": "What flush fitment works on a 2020 BMW M3?"
}
```

Response:
```json
{
  "answer": "Based on the fitment data...",
  "sources": [
    {
      "document": "2023 BMW M3 Competition | Setup: staggered flush...",
      "metadata": {
        "year": 2023,
        "make": "BMW",
        "model": "M3 Competition",
        "front_diameter": 20,
        "front_width": 10,
        "front_offset": 22,
        ...
      },
      "rank": 0.25948
    }
  ]
}
```

### Example Queries
- "What wheels fit a Honda Civic?"
- "2020 BMW M3 flush fitment"
- "FK8 Civic Type R aggressive setup"
- "Chevy truck aggressive fitment"
- "E30 M3 flush wheels" (handles chassis codes)

## Services

### RAGService
Core service for searching fitments and generating AI responses using Supabase full-text search and OpenAI.

Key features:
- **NLP Query Parsing**: Uses OpenAI to extract year, make, model, and fitment_style from natural language
- **Chassis Code Handling**: Recognizes E30, FK8, GD, etc. and extracts actual model names
- **Nickname Support**: "chevy" → Chevrolet, "bimmer" → BMW
- **Progressive Fallback**: If exact year not found, drops year filter; if still empty, drops fitment_style
- **Clean Search Queries**: Builds FTS queries from parsed values to avoid issues with chassis codes/years not in DB

### WheelMatcher
Matches vehicles to compatible Kansei wheels based on:
- Bolt pattern compatibility
- Offset ranges for different stances (stock, flush, aggressive, tucked)
- Modification allowances (rolled fenders, coilovers, etc.)
- Falls back to OEM specs when no community data exists

### WheelSizeLookup
On-demand OEM specs lookup from wheel-size.com:
- Fetches bolt pattern, offset range, wheel sizes
- Caches results locally
- Used as fallback when no community fitment data

### KanseiScraper
Scrapes Kansei wheels catalog (457 wheel variants):
- Street and offroad wheels
- Extracts specs from SKUs (diameter, width, offset)
- Saves to JSON for wheel matching

## Railway Deployment

### Environment Variables (set in Railway dashboard)
```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_anon_key
OPENAI_API_KEY=your_openai_api_key
```

### Deploy Steps
1. Push code to GitHub
2. Go to [railway.app](https://railway.app) and create new project
3. Select "Deploy from GitHub repo"
4. Choose this repository
5. Add environment variables in Settings → Variables
6. Railway auto-deploys on push to main

### Files for Railway
- `railway.toml` - Railway-specific config (health checks, restart policy)
- `nixpacks.toml` - Build config (Python 3.12, uv package manager)
- `Procfile` - Start command fallback

### Health Check
Railway pings `/health` endpoint to verify the service is running.

## Notes for Development

- Frontend (Next.js) runs on port 3000, CORS configured accordingly
- Uses PostgreSQL full-text search (FTS5 equivalent) instead of vector embeddings
- 54,570 community fitment records loaded
- Supabase free tier: 500MB database, unlimited API requests
- Run `uv run ruff check src/` and `uv run pyright src/` before committing
