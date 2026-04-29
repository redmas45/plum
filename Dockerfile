FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Create necessary directories
RUN mkdir -p data uploads

# Expose port
EXPOSE 8000

# Run uvicorn (Using shell form so $PORT is evaluated correctly by Railway)
CMD uvicorn app.main:app --host 0.0.0.0 --port $PORT
