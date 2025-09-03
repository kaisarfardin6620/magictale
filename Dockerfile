# syntax=docker/dockerfile:1

# --- Stage 1: Builder ---
# This stage installs build-time dependencies and our Python packages into a virtual environment.
FROM python:3.11-slim AS builder

WORKDIR /app

# Install system packages needed to build Python libraries (like psycopg2)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python requirements
COPY --link requirements.txt ./
RUN python -m venv .venv \
    && .venv/bin/pip install --upgrade pip

# === THIS IS THE FIX ===
# Added 'id=pip-cache,' to the mount instruction to make it compatible with Railway.
RUN --mount=type=cache,id=pip-cache,target=/root/.cache/pip .venv/bin/pip install -r requirements.txt
# === END OF FIX ===


# --- Stage 2: Final Image ---
# This stage builds the final, lean image for running the application.
FROM python:3.11-slim AS final

# Install only the system packages needed at RUNTIME
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libgobject-2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Create a secure, non-root user to run the application
RUN useradd -m -u 1000 appuser

WORKDIR /app

# Copy the application code and the virtual environment from the builder stage
COPY --link . .
COPY --from=builder /app/.venv /app/.venv

# Create directories for static and media files
RUN mkdir -p /app/staticfiles /app/media

# Change ownership of the entire application directory to the non-root user.
RUN chown -R appuser:appuser /app

# Switch to the non-root user
USER appuser

# Add the virtual environment's bin to the PATH
ENV PATH="/app/.venv/bin:$PATH"

# Expose the port the app runs on
EXPOSE 8000

# Default command to run the server (will be overridden by Railway's start command)
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "magictale.asgi:application"]