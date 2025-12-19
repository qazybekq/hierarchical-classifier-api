# Use Python 3.11 slim image for smaller size
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code and artifacts
COPY hier_flask_api.py .
COPY train_hier_ext_gpu.py .
COPY artifacts_best_gpu/ ./artifacts_best_gpu/

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV ARTIFACTS_ROOT=/app
ENV DEFAULT_ARTIFACTS_DIR=artifacts_best_gpu
ENV FLASK_HOST=0.0.0.0
ENV FLASK_PORT=8001
ENV FLASK_DEBUG=0

# Expose port
EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8001/health', timeout=5)"

# Run with gunicorn for production
# --preload-app loads the app before forking workers (fixes pickle/joblib issues)
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:8001", "--timeout", "120", "--preload-app", "hier_flask_api:app"]



