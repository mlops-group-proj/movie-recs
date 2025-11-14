# ================================
# Stage 1: Builder
# ================================
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python packages to user directory
RUN pip install --no-cache-dir --user -r requirements.txt

# ================================
# Stage 2: Runtime (Final Image)
# ================================
FROM python:3.11-slim

WORKDIR /app

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local

# Copy the entire repo (not just subfolders)
COPY . .

# Update PATH
ENV PATH=/root/.local/bin:$PATH

# Set environment defaults
ENV PORT=8080

# Expose the API port
EXPOSE 8080

# Health check for ECS Fargate
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8080/healthz || exit 1

# Start FastAPI app
CMD ["uvicorn", "service.app:app", "--host", "0.0.0.0", "--port", "8080"]