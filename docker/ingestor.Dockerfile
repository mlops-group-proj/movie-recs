# Multi-stage build for stream ingestor
FROM python:3.11.7-slim AS builder
WORKDIR /app

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY reqs-ingestor.txt .
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --no-cache-dir wheel \
    && /opt/venv/bin/pip install --no-cache-dir -r reqs-ingestor.txt

FROM python:3.11.7-slim AS runtime
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MODEL_REGISTRY=/models
WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

COPY --from=builder /opt/venv /opt/venv
COPY stream/ stream/
COPY recommender/ recommender/

# Model registry is expected to be mounted (volume or env path)
VOLUME ["/models"]

USER app
CMD ["python", "-m", "stream.consumer"]
