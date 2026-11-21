FROM python:3.12-slim-bookworm

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8000 \
    HOST=0.0.0.0

# Install system audio, codec, and compilation packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libportaudio2 \
    portaudio19-dev \
    libsndfile1 \
    curl \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency definition and install
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code, static UI assets, and knowledge base
COPY app/ ./app/
COPY data/ ./data/
COPY scripts/ ./scripts/
COPY pyproject.toml .env.example ./

# Expose HTTP and WebSocket port
EXPOSE 8000

# Docker native healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Start FastAPI application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
