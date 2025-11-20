# Provenance Logging Guide - Movie Recommender System

**Last Updated**: 2025-11-19
**Owner**: MLOps Team

---

## Table of Contents
1. [Overview](#overview)
2. [Provenance Fields](#provenance-fields)
3. [Usage Examples](#usage-examples)
4. [Trace Retrieval](#trace-retrieval)
5. [Request ID Tracking](#request-id-tracking)
6. [Structured Logging](#structured-logging)
7. [Avro Schema](#avro-schema)
8. [Best Practices](#best-practices)

---

## Overview

The Movie Recommender System implements comprehensive provenance logging to track the complete lineage of every prediction. This enables:

- **Reproducibility**: Trace exactly which model version and data generated each prediction
- **Debugging**: Investigate issues by examining the full context of failed requests
- **Auditing**: Maintain a complete audit trail for compliance and quality assurance
- **Performance Analysis**: Track latency and identify bottlenecks per request

### Key Features

✅ **Automatic Request ID injection** via middleware
✅ **Complete provenance metadata** in every response
✅ **Structured logging** with full context
✅ **Trace storage and retrieval** via `/trace` endpoint
✅ **Avro schema compliance** for stream processing

---

## Provenance Fields

Every prediction response includes the following provenance fields:

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| **request_id** | string | Unique identifier for the request | `"7c9e6679-7425-40de-944b-e07fc1f90ae7"` |
| **timestamp** | long | Unix timestamp in milliseconds | `1700419200000` |
| **model_name** | string | Name of the model algorithm | `"als"` |
| **model_version** | string | Semantic version of the model | `"v0.3"` |
| **git_sha** | string | Git commit SHA of training pipeline | `"207521e0d08a"` |
| **data_snapshot_id** | string | SHA256 hash of training data snapshot | `"9c1de44291dc..."` |
| **container_image_digest** | string\|null | OCI image digest (sha256) | `"sha256:abc123..."` |
| **latency_ms** | int | Request latency in milliseconds | `45` |

---

## Usage Examples

### Basic Recommendation Request

```bash
curl http://localhost:8080/recommend/123?k=10
```

**Response**:
```json
{
  "user_id": 123,
  "model": "v0.3",
  "items": [1, 50, 260, 527, 588, 592, 593, 594, 595, 596],
  "variant": null,
  "provenance": {
    "request_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
    "timestamp": 1700419234567,
    "model_name": "als",
    "model_version": "v0.3",
    "git_sha": "207521e0d08abb271998cc9790a9d006e1b0f4eb",
    "data_snapshot_id": "9c1de44291dc0a7b0f0354cf256a383cd33ce9ea7adcf8debe3d9bc2786b3175",
    "container_image_digest": null,
    "latency_ms": 45
  }
}
```

### With Custom Request ID

You can provide your own request ID via the `X-Request-ID` header:

```bash
curl -H "X-Request-ID: my-custom-id-12345" \
     http://localhost:8080/recommend/456?k=5
```

The response will use your custom ID:
```json
{
  "provenance": {
    "request_id": "my-custom-id-12345",
    ...
  }
}
```

### Response Headers

Every response includes the `X-Request-ID` header:

```bash
curl -v http://localhost:8080/recommend/789?k=10
```

```
< HTTP/1.1 200 OK
< x-request-id: 8d7a6e5f-4c3b-2a1d-0e9f-8c7b6a5d4e3f
< content-type: application/json
...
```

---

## Trace Retrieval

Retrieve the complete trace for any request using its `request_id`:

### Endpoint

```
GET /trace/{request_id}
```

### Example

```bash
# Step 1: Make a recommendation request and capture the request_id
REQUEST_ID=$(curl -s http://localhost:8080/recommend/100?k=5 | jq -r '.provenance.request_id')

# Step 2: Retrieve the full trace
curl "http://localhost:8080/trace/$REQUEST_ID" | jq
```

**Response**:
```json
{
  "request_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "trace": {
    "request_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
    "timestamp": 1700419234567,
    "model_name": "als",
    "model_version": "v0.3",
    "git_sha": "207521e0d08abb271998cc9790a9d006e1b0f4eb",
    "data_snapshot_id": "9c1de44291dc0a7b0f0354cf256a383cd33ce9ea7adcf8debe3d9bc2786b3175",
    "container_image_digest": null,
    "latency_ms": 45,
    "user_id": 100,
    "k": 5,
    "num_items": 5,
    "status": 200,
    "variant": null,
    "path": "/recommend/{user_id}",
    "method": "GET",
    "stored_at": 1700419234.612
  }
}
```

### Trace Not Found

If the trace doesn't exist (e.g., too old and evicted from LRU cache):

```bash
curl http://localhost:8080/trace/nonexistent-id
```

```json
{
  "detail": "Trace not found for request_id=nonexistent-id. Traces are kept for the last 1000 requests only."
}
```

### Trace Storage Limits

- **Capacity**: Last 1,000 requests
- **Eviction**: LRU (Least Recently Used)
- **Production**: Use distributed tracing (Jaeger, Zipkin) for larger scale

---

## Request ID Tracking

### Automatic Generation

If no `X-Request-ID` header is provided, a UUID is automatically generated:

```python
request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
```

### Custom IDs

Provide your own request ID for correlation across services:

```bash
curl -H "X-Request-ID: frontend-trace-xyz-789" \
     http://localhost:8080/recommend/555?k=10
```

### ID Format

- **Auto-generated**: UUID v4 format (`xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`)
- **Custom**: Any string (recommended: include service name for distributed tracing)

---

## Structured Logging

All requests are logged with complete provenance context.

### Success Logs

```
INFO [7c9e6679-7425-40de-944b-e07fc1f90ae7] Recommendation success for user 123
```

**Log Context** (available via `logging.extra`):
```python
{
    "request_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
    "timestamp": 1700419234567,
    "model_name": "als",
    "model_version": "v0.3",
    "git_sha": "207521e0d08abb271998cc9790a9d006e1b0f4eb",
    "data_snapshot_id": "9c1de44291dc0a7b0f0354cf256a383cd33ce9ea7adcf8debe3d9bc2786b3175",
    "latency_ms": 45,
    "user_id": 123,
    "k": 10,
    "num_items": 10,
    "status": 200,
    "variant": None
}
```

### Error Logs

Errors include the same provenance context:

```
ERROR [7c9e6679-7425-40de-944b-e07fc1f90ae7] Recommendation error for user 999
```

**Error Context**:
```python
{
    "request_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
    "user_id": 999,
    "model_version": "v0.3",
    "git_sha": "207521e0d08abb271998cc9790a9d006e1b0f4eb",
    "data_snapshot_id": "9c1de44291dc0a7b0f0354cf256a383cd33ce9ea7adcf8debe3d9bc2786b3175",
    "status": 500,
    "latency_ms": 12,
    "error_type": "ValueError",
    "variant": None
}
```

### Querying Logs

Filter logs by request_id:

```bash
# View all logs for a specific request
docker compose logs api | grep "7c9e6679-7425-40de-944b-e07fc1f90ae7"
```

---

## Avro Schema

The provenance fields align with the updated `reco_response.avsc` Avro schema for stream processing.

### Schema Definition

**File**: `stream/schemas/reco_response.avsc`

```json
{
  "type": "record",
  "name": "RecoResponse",
  "namespace": "mlprod",
  "fields": [
    {"name": "request_id", "type": "string"},
    {"name": "ts", "type": "long"},
    {"name": "user_id", "type": "int"},
    {"name": "status", "type": "int"},
    {"name": "latency_ms", "type": "int"},
    {"name": "k", "type": "int"},
    {"name": "movie_ids", "type": {"type": "array", "items": "int"}},
    {"name": "model_version", "type": "string"},
    {"name": "model_name", "type": "string"},
    {"name": "git_sha", "type": "string"},
    {"name": "data_snapshot_id", "type": "string"},
    {"name": "container_image_digest", "type": ["null", "string"], "default": null}
  ]
}
```

### Validation

Validate responses against the schema:

```python
from stream.validate_avro import validate_record

record = {
    "request_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
    "ts": 1700419234567,
    "user_id": 123,
    "status": 200,
    "latency_ms": 45,
    "k": 10,
    "movie_ids": [1, 50, 260, 527, 588],
    "model_version": "v0.3",
    "model_name": "als",
    "git_sha": "207521e0d08abb271998cc9790a9d006e1b0f4eb",
    "data_snapshot_id": "9c1de44291dc0a7b0f0354cf256a383cd33ce9ea7adcf8debe3d9bc2786b3175",
    "container_image_digest": None
}

is_valid = validate_record("reco_response", record)
assert is_valid
```

---

## Best Practices

### 1. Always Use Request IDs for Debugging

When investigating issues, use request IDs to trace the complete flow:

```bash
# User reports issue with recommendation
# Step 1: Get request_id from logs or user
REQUEST_ID="problematic-request-id"

# Step 2: Retrieve full trace
curl "http://localhost:8080/trace/$REQUEST_ID"

# Step 3: Check logs for that request
docker compose logs api | grep "$REQUEST_ID"
```

### 2. Include Request ID in Frontend

Pass request IDs from frontend to backend for end-to-end tracing:

```javascript
const requestId = generateClientRequestId();  // e.g., "web-user-123-timestamp"

fetch(`/recommend/123?k=10`, {
  headers: {
    'X-Request-ID': requestId
  }
});
```

### 3. Monitor Container Digest

Set `CONTAINER_IMAGE_DIGEST` during deployment:

```dockerfile
# In Dockerfile
ARG IMAGE_DIGEST
ENV CONTAINER_IMAGE_DIGEST=$IMAGE_DIGEST
```

```bash
# During build
docker build --build-arg IMAGE_DIGEST=$(docker images --digests | ...) .
```

### 4. Export Traces for Long-Term Storage

The in-memory trace store is limited to 1,000 requests. For production:

**Option A: Integrate distributed tracing**
- Jaeger
- Zipkin
- AWS X-Ray

**Option B: Export to structured logging**
- Elasticsearch + Kibana
- Splunk
- Datadog

### 5. Correlate with Metrics

Use provenance fields to correlate logs and metrics:

```promql
# Latency by model version
histogram_quantile(0.95,
  sum(rate(recommend_latency_seconds_bucket[5m])) by (le)
)

# Filter traces by model version in logs
model_version="v0.3" AND status=500
```

### 6. Document Provenance in Incident Reports

When documenting incidents, always include:
- Request ID
- Timestamp
- Model version
- Git SHA
- Data snapshot ID

This ensures reproducibility and helps prevent regression.

---

## Example Workflows

### Debugging a Failed Prediction

```bash
# 1. User reports error at 2025-11-19 14:30:00
# 2. Find the request in logs
docker compose logs api | grep "2025-11-19.*14:30" | grep "ERROR"

# Sample log:
# ERROR [abc-123-def] Recommendation error for user 789

# 3. Get full trace
curl http://localhost:8080/trace/abc-123-def

# 4. Check what model version was used
# trace.model_version = "v0.2"

# 5. Check if v0.2 has known issues
git log --grep "v0.2"

# 6. Reproduce locally using the same model
export MODEL_VERSION=v0.2
curl http://localhost:8080/recommend/789?k=10
```

### Investigating Performance Regression

```bash
# 1. Query traces for slow requests
# (In production, query from Elasticsearch/logging backend)

# 2. Group by model_version and git_sha
# Identify which version introduced the regression

# 3. Compare provenance fields
curl http://localhost:8080/trace/slow-request-id > slow.json
curl http://localhost:8080/trace/fast-request-id > fast.json
diff slow.json fast.json

# 4. Check if data_snapshot_id differs
# Different data may cause performance changes
```

### Model Version Rollback Verification

```bash
# 1. Before rollback, capture current provenance
curl http://localhost:8080/recommend/100?k=5 | jq '.provenance'
# git_sha: "207521e0"
# model_version: "v0.3"

# 2. Perform rollback
curl -X POST "http://localhost:8080/rollout/update?strategy=fixed"
curl "http://localhost:8080/switch?model=v0.2"

# 3. Verify new provenance
curl http://localhost:8080/recommend/100?k=5 | jq '.provenance'
# git_sha: "abc123de"  (v0.2's git SHA)
# model_version: "v0.2"
```

---

## API Reference

### `GET /recommend/{user_id}`

**Returns**: Recommendations with full provenance

**Response Fields**:
- `user_id`: User identifier
- `model`: Model version used
- `items`: List of recommended item IDs
- `variant`: A/B test variant (if applicable)
- **`provenance`**: Complete provenance metadata

### `GET /trace/{request_id}`

**Returns**: Complete trace for a specific request

**Parameters**:
- `request_id` (path): Unique request identifier

**Response**:
- `request_id`: Requested ID
- `trace`: Full trace object with all provenance and request metadata

**Errors**:
- `404`: Trace not found (request too old or never existed)

---

## Further Reading

- [API Reference](API_REFERENCE.md)
- [A/B Testing Guide](AB_TESTING_GUIDE.md)
- [Runbook](RUNBOOK.md)
- [OpenTelemetry Documentation](https://opentelemetry.io/docs/)

---

**Generated by**: MLOps Team
**Last Updated**: 2025-11-19
