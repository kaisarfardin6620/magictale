# Dockerfile

# Use an official Python image. 'slim-bookworm' is a modern, minimal Debian-based image.
FROM python:3.11-slim-bookworm

# Set environment variables for a clean Python environment
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# === THIS IS THE CRUCIAL FIX ===
# Use the Linux package manager 'apt-get' to install the system libraries
# that WeasyPrint depends on. This command runs *inside* the container.
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

# Copy the requirements file first to leverage Docker's layer caching
COPY requirements.txt .
# Install Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Copy your application code into the container
COPY . .

# Expose the port the app will run on
EXPOSE 8001

# Note: The 'command' in docker-compose.yml will override this CMD,
# which is perfect for separating development and production commands.
CMD ["daphne", "-b", "0.0.0.0", "-p", "8001", "magictale.asgi:application"]