FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Default port (Railway overrides this with its own PORT)
ENV PORT=8000

# Shell form for variable expansion
CMD uvicorn src.app.main:app --host 0.0.0.0 --port $PORT
