# ================================
# Stage 1: Builder
# ================================
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies for ML packages (numpy, scipy, sklearn, pytorch)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    gfortran \
    libopenblas-dev \
    liblapack-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install ML packages (this is heavy - can take 5-10 minutes)
RUN pip install --no-cache-dir --user -r requirements.txt

# ================================
# Stage 2: Runtime (Final Image)
# ================================
FROM python:3.11-slim

WORKDIR /app

# Install only runtime math libraries (not -dev versions)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libopenblas0 \
    liblapack3 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local

# Copy recommender code and model registry
COPY recommender/ recommender/
COPY model_registry/ model_registry/

# Update PATH
ENV PATH=/root/.local/bin:$PATH

# Run the trainer
CMD ["python", "-m", "recommender.train"]