# Multi-stage build for AnO - Affairs and Order

# Stage 1: Builder
FROM python:3.10-slim as builder

WORKDIR /tmp
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Runtime
FROM python:3.10-slim

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy Python packages from builder
COPY --from=builder /root/.local /root/.local

# Copy application code
COPY . .

# Set Python path
ENV PATH=/root/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=5000

# Health check - use /health endpoint that Railway also checks
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Default to web service
# --preload loads the Flask app BEFORE forking workers so they can
# immediately serve Railway's /health healthcheck on startup.
# Shell form so $PORT expands at runtime (Railway injects PORT env var).
CMD gunicorn --bind 0.0.0.0:${PORT:-5000} --preload --workers 4 --threads 4 --worker-class gthread --timeout 120 --graceful-timeout 15 --keep-alive 30 --max-requests 1000 --max-requests-jitter 100 --access-logfile - --error-logfile - --log-level info wsgi:app
