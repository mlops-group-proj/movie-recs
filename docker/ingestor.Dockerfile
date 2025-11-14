# ================================
# Stage 1: Builder
# ================================
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies for Kafka and other packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    librdkafka-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (better layer caching)
COPY requirements.txt .

# Install Python packages to user directory
RUN pip install --no-cache-dir --user -r requirements.txt

# ================================
# Stage 2: Runtime (Final Image)
# ================================
FROM python:3.11-slim

WORKDIR /app

# Install only runtime Kafka library (not the -dev version)
RUN apt-get update && apt-get install -y --no-install-recommends \
    librdkafka1 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder stage
COPY --from=builder /root/.local /root/.local

# Copy application code
COPY stream/ stream/

# Make sure scripts in .local are usable
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1

# Run the stream consumer
CMD ["python", "-m", "stream.consumer"]