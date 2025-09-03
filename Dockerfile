# syntax=docker/dockerfile:1

# --- Base image ---
FROM python:3.11-slim AS base

# --- Builder stage ---
# This stage installs build-time dependencies and Python packages
FROM base AS builder
WORKDIR /app

# Install only the dependencies needed to BUILD python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python requirements
COPY --link requirements.txt ./
RUN python -m venv .venv \
    && .venv/bin/pip install --upgrade pip
RUN --mount=type=cache,target=/root/.cache/pip .venv/bin/pip install -r requirements.txt

# --- Final stage ---
# This stage creates the final, lean image for running the application
FROM base AS final

# Install only the RUNTIME dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libgobject-2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Security: create non-root user
RUN useradd -m -u 1000 appuser

WORKDIR /app

# Copy application code
COPY --link . .

# Copy the virtual environment from the builder stage
COPY --from=builder /app/.venv /app/.venv

# === THIS IS THE FIX ===
# Create the directories for static and media files, then change their ownership
# to the non-root user. This must be done BEFORE switching to the user.
RUN mkdir -p /app/staticfiles /app/media \
    && chown -R appuser:appuser /app/staticfiles /app/media
# === END OF FIX ===

# Set user
USER appuser

# Set PATH to use the venv
ENV PATH="/app/.venv/bin:$PATH"

# Expose Daphne port
EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD curl -f http://localhost:8000/ || exit 1

# Default command (will be overridden by docker-compose's entrypoint)
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "magictale.asgi:application"]