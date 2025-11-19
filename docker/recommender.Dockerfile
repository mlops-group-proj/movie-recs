# docker/recommender.Dockerfile
# Multi-stage build for the recommender API
# Builder: install dependencies
FROM python:3.11.7-slim AS builder
WORKDIR /app

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY reqs-recommender.txt .
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir wheel \
    && /opt/venv/bin/pip install --no-cache-dir -r reqs-recommender.txt

# Runtime: copy only what is needed and drop privileges
FROM python:3.11.7-slim AS runtime
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MODEL_REGISTRY=/models \
    PORT=8080
WORKDIR /app

# Non-root user
RUN addgroup --system app && adduser --system --ingroup app app

# Copy virtualenv and application code
COPY --from=builder /opt/venv /opt/venv
COPY service/ service/
COPY recommender/ recommender/

# Model registry is expected to be mounted (volume or env path)
VOLUME ["/models"]

EXPOSE 8080
USER app

CMD ["uvicorn", "service.app:app", "--host", "0.0.0.0", "--port", "8080"]
