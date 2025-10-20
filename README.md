# Cloud-Native Recommender

## Quickstart

1. **Python setup**
   ```bash
   python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. **Environment**
   - Copy `.env.example` → `.env` and set values.
3. **Run API locally**
   ```bash
   uvicorn service.app:app --reload --port 8080
   curl http://localhost:8080/healthz
   ```
4. **Docker build**
   ```bash
   docker build -f docker/recommender.Dockerfile -t reco-api:dev .
   docker run -p 8080:8080 --env-file .env reco-api:dev
   ```
5. **Kafka sanity (kcat)**
   ```bash
   # example (adjust flags for your cluster)
   set -a && source .env && set +a && docker run --rm \
   -e KAFKA_BOOTSTRAP \
   -e KAFKA_API_KEY \
   -e KAFKA_API_SECRET \
   edenhill/kcat:1.7.0 -L \
   -b "$KAFKA_BOOTSTRAP" \
   -X security.protocol=SASL_SSL \
   -X sasl.mechanisms=PLAIN \
   -X sasl.username="$KAFKA_API_KEY" \
   -X sasl.password="$KAFKA_API_SECRET"
   ```
6. **CI/CD** (GitHub Actions)
   - Push to main → CI runs tests, builds/pushes image, CD deploys to cloud.

## Endpoints

- `GET /healthz` → `{ "status": "ok", "version": "vX.Y" }`
- `GET /recommend/{user_id}?k=20&model=A` → comma-separated movie IDs
- `GET /metrics` → Prometheus exposition

## Project Structure

See repo tree; components updated as progress is made.

## Kafka Configuration

### Consumer Configuration
The project uses Confluent Kafka with SASL_SSL authentication. The consumer configuration includes:

```python
{
    "bootstrap.servers": "pkc-xxxxx.us-east-2.aws.confluent.cloud:9092",
    "security.protocol": "SASL_SSL",
    "sasl.mechanisms": "PLAIN",
    "sasl.username": "your-api-key",
    "sasl.password": "your-api-secret",
    "group.id": "ingestor",
    "auto.offset.reset": "earliest"
}
```

### Schema Validation
All Kafka messages are validated against Avro schemas:
- **WatchEvent**: `{user_id: int, movie_id: int, timestamp: string}`
- **RateEvent**: `{user_id: int, movie_id: int, rating: float, timestamp: string}`
- **RecoRequest**: `{user_id: int, timestamp: string}`
- **RecoResponse**: `{user_id: int, movie_ids: [int], scores: [float], timestamp: string}`

### Stream Ingestor
The stream ingestor (`stream/ingestor.py`) consumes from all topics, validates messages, and writes to parquet:
```bash
# Run the ingestor
python -m stream.ingestor

# Or with Docker
docker build -f docker/ingestor.Dockerfile -t movie-ingestor:latest .
docker run --env-file .env movie-ingestor:latest
```

**Output Structure:**
```
data/snapshots/
  ├── watch/2025-10-20/batch_20251020_120000.parquet
  ├── rate/2025-10-20/batch_20251020_120000.parquet
  ├── reco_requests/2025-10-20/batch_20251020_120000.parquet
  └── reco_responses/2025-10-20/batch_20251020_120000.parquet
```

### Testing
```bash
# Run all tests
pytest tests/ -v

# Run specific test suites
pytest tests/test_schemas.py -v      # Schema validation tests
pytest tests/test_consumer.py -v     # Consumer integration tests
pytest tests/test_ingestor.py -v     # Ingestor tests (17 tests)
```

## Secrets & Safety

- Use **GitHub Environments/Secrets**. Never commit secrets. Rotate if leaked.
- Follow team contract’s Definition of Done. Lint and tests must pass before merge.

---

## Metrics and Monitoring

The service exposes **Prometheus-compatible metrics** for observability.

### Endpoint

- **URL:** `http://<host>:8080/metrics`
- **Method:** `GET`
- **Content-Type:** `text/plain; version=0.0.4`

### Key Metrics

| Metric                          | Type      | Description                           |
| ------------------------------- | --------- | ------------------------------------- |
| `http_requests_total`           | Counter   | Total HTTP requests processed         |
| `http_request_duration_seconds` | Histogram | Request latency in seconds            |
| `recommend_requests_total`      | Counter   | Recommendation requests processed     |
| `recommend_latency_seconds`     | Histogram | Latency for recommendation generation |

Example output:

```text
# HELP http_requests_total Total HTTP requests
# TYPE http_requests_total counter
http_requests_total{method="GET",path="/metrics",status="200"} 1.0
```
