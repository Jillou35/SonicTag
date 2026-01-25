FROM python:3.11-slim

# Install system dependencies (libsndfile for soundfile)
RUN apt-get update && apt-get install -y \
    libsndfile1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy uv from the official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install Python requirements
COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

# Environment setup
ENV PYTHONUNBUFFERED=1

# Create a non-root user
RUN useradd -m -u 1000 appuser

# Set permissions for the app directory
RUN chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Default command (can be overridden)
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000"]
