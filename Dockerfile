FROM python:3.12

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Run via Python script that reads PORT from environment
EXPOSE 8000
CMD ["python", "run.py"]
