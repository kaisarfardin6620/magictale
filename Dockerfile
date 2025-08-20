# Dockerfile

# Use an official Python image. 'slim-bookworm' is a modern, minimal Debian-based image.
FROM python:3.11-slim-bookworm

# Set environment variables for a clean Python environment
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# --- System Dependencies ---
# Install libraries required by Python packages like WeasyPrint
RUN apt-get update && apt-get install -y \
    build-essential \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz0b \
    gir1.2-gobject-2.0 \
    libcairo2 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory inside the container
WORKDIR /app

# --- Python Package Installation ---
# Copy and install requirements first to leverage Docker's layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Application Code ---
# Copy the rest of your application code
COPY . .

# --- Django-Specific Deployment Steps ---
# This command finds all static files from your apps and collects them
# into the STATIC_ROOT directory (/app/staticfiles) for WhiteNoise to serve.
# This fixes the "No directory at: /app/staticfiles/" warning.
RUN python manage.py collectstatic --noinput

# --- Port Configuration ---
# Expose a default port. Railway will override this, but it's good practice.
EXPOSE 8001

# --- Final Startup Command ---
# This is the key to making it work everywhere.
# 1. 'sh -c "..."' allows us to run multiple commands.
# 2. 'python manage.py migrate' runs database migrations on every startup.
# 3. 'daphne ... -p ${PORT:-8001}' starts the server.
#    - On Railway, it uses the PORT variable provided by the platform (e.g., 8080).
#    - Locally, if PORT is not set, it defaults to 8001.
CMD ["sh", "-c", "python manage.py migrate && daphne -b 0.0.0.0 -p ${PORT:-8001} magictale.asgi:application"]