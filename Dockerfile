# Multi-stage Dockerfile for MiniPOS Django Application
# Stage 1: Builder - Install dependencies and build assets
FROM python:3.14-slim AS builder

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PIP_NO_CACHE_DIR=1

# Install system dependencies required for building
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set work directory
WORKDIR /app

# Copy dependency files first for better layer caching
COPY pyproject.toml uv.lock ./

# Install dependencies using uv (frozen for reproducible builds)
RUN uv sync --frozen --no-dev --no-install-project

# Copy project source code
COPY . .

# Install the project itself
RUN uv sync --frozen --no-dev

# Stage 2: Runtime - Minimal production image
FROM python:3.14-slim AS runtime

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DJANGO_SETTINGS_MODULE=config.settings

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user for security
RUN groupadd -r appgroup && useradd -r -g appgroup -d /app -s /bin/bash appuser

# Set work directory
WORKDIR /app

# Copy virtual environment from builder stage
COPY --from=builder --chown=appuser:appgroup /app/.venv /app/.venv

# Copy application code
COPY --from=builder --chown=appuser:appgroup /app /app

# Create staticfiles directory and set permissions
RUN mkdir -p /app/staticfiles && chown -R appuser:appgroup /app/staticfiles

# Switch to non-root user
USER appuser

# Add virtual environment to PATH
ENV PATH="/app/.venv/bin:$PATH"

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health/ || exit 1

# Run gunicorn with optimized settings
CMD ["gunicorn", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--worker-class", "gthread", \
     "--threads", "2", \
     "--timeout", "60", \
     "--keep-alive", "5", \
     "--max-requests", "1000", \
     "--max-requests-jitter", "50", \
     "--preload", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "config.wsgi:application"]