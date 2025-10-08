# syntax=docker/dockerfile:1

# Builder stage to install build dependencies and Python packages
FROM python:3.11-slim AS builder

WORKDIR /opt
RUN python -m venv venv
ENV PATH="/opt/venv/bin:$PATH"

# Install build-time dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


# Final stage for the application
FROM python:3.11-slim AS final

# Install runtime dependencies and gosu for user switching
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libgobject-2.0-0 \
    gettext \
    gosu \
    && rm -rf /var/lib/apt/lists/*

# Copy the virtual environment from the builder stage
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create the non-root user that the application will run as
RUN useradd -m -u 1000 appuser

# Set the working directory
WORKDIR /app