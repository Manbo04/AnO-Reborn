# Use Python 3.8 as specified in runtime.txt
FROM python:3.8-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create directory for logs
RUN mkdir -p /app/logs

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV FLASK_APP=app.py

# Expose port 5000 for Flask
EXPOSE 5000

# Default command (can be overridden in docker-compose.yml)
CMD ["gunicorn", "wsgi:app", "--workers", "4", "--timeout", "120", "--bind", "0.0.0.0:5000"]
