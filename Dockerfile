FROM python:3.11-slim-bookworm AS builder

WORKDIR /app
COPY requirements.txt .

# Install build dependencies and compile wheels
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc python3-dev && \
    pip wheel --no-cache-dir --wheel-dir=/app/wheels -r requirements.txt && \
    rm -rf /var/lib/apt/lists/*

# Create final image
FROM python:3.11-slim-bookworm

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg curl && \
    rm -rf /var/lib/apt/lists/*

# Copy wheels and install dependencies
COPY --from=builder /app/wheels /app/wheels
RUN pip install --no-cache-dir --no-index --find-links=/app/wheels /app/wheels/* && \
    rm -rf /app/wheels

# Copy application code
COPY . /app/

# Set environment variables
ENV PORT=8000
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV DEV_SERVER=uvicorn
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]