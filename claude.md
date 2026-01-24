# Wheel Fitment RAG API

A Python FastAPI application that uses RAG (Retrieval Augmented Generation) to help customers find wheel and tire fitments for their vehicles.

## Tech Stack

- **Python 3.12** with **uv** for package management
- **FastAPI** for the REST API
- **Supabase** (PostgreSQL + pgvector) for storage and full-text search
- **Anthropic Claude** for AI responses

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
ANTHROPIC_API_KEY=your_anthropic_api_key
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

### Query Endpoints
- `POST /api/ask` - Ask a question about fitments (RAG response with Claude)
- `POST /api/search` - Search for fitments without AI response

### Data Endpoints
- `GET /api/makes` - Get all vehicle makes
- `GET /api/models/{make}` - Get models for a make
- `GET /api/years` - Get all years
- `GET /api/fitment-styles` - Get fitment styles (aggressive, flush, tucked)
- `GET /api/fitment-setups` - Get fitment setups (square, staggered)
- `POST /api/load-data` - Load fitment data from CSV

## Request/Response Examples

### Ask Question with Filters
```json
POST /api/ask
{
  "query": "What aggressive wheel setup works on a Civic?",
  "year": 2025,
  "make": "Honda",
  "model": "Civic Sport",
  "fitment_setup": "square",
  "fitment_style": "aggressive",
  "limit": 5
}
```

### Search for Staggered Setups
```json
POST /api/search
{
  "query": "19 inch wheels BMW M4",
  "make": "BMW",
  "fitment_setup": "staggered",
  "limit": 10
}
```

## Services

### RAGService
Core service for searching fitments and generating AI responses using Supabase full-text search and Claude.

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

## Notes for Development

- Frontend (Next.js) runs on port 3000, CORS configured accordingly
- Uses PostgreSQL full-text search (FTS5 equivalent) instead of vector embeddings
- 54,570 community fitment records loaded
- Supabase free tier: 500MB database, unlimited API requests
- Run `uv run ruff check src/` and `uv run pyright src/` before committing
