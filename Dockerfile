# Dockerfile

# --- Stage 1: The "Builder" Stage ---
FROM python:3.11-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Install system dependencies for WeasyPrint
RUN apt-get update && apt-get install -y \
    build-essential \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz0b \
    libgirepository1.0-dev \
    gcc \
    pkg-config \
    libcairo2-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Securely run collectstatic with a dummy key
RUN SECRET_KEY="dummy-key-for-collectstatic" python manage.py collectstatic --noinput


# --- Stage 2: The Final Production Image ---
FROM python:3.11-slim-bookworm AS final

# Create a non-root user
RUN useradd --create-home --shell /bin/bash appuser
WORKDIR /home/appuser/app

# Install only runtime dependencies
RUN apt-get update && apt-get install -y \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz0b \
    libgirepository1.0-dev \
    libcairo2-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages and static files from the builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /app/staticfiles /home/appuser/app/staticfiles

# Copy application code
COPY . .

# Change ownership
RUN chown -R appuser:appuser /home/appuser

USER appuser

EXPOSE 8000

# Default command for production
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "magictale.asgi:application"]