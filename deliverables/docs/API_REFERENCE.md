# API Reference - Movie Recommender System

## Base URL
- **Local**: `http://localhost:8080`
- **AWS EC2**: `http://ec2-54-221-101-86.compute-1.amazonaws.com:8080`

---

## Core Endpoints

### `GET /healthz`
Health check endpoint with version and rollout information.

**Response:**
```json
{
  "status": "ok",
  "version": "v0.3",
  "rollout": {
    "strategy": "fixed",
    "primary_version": "v0.3",
    "canary_version": null,
    "canary_percentage": 0.0,
    "environment": "production"
  }
}
```

---

### `GET /recommend/{user_id}`
Get top-K movie recommendations for a user.

**Parameters:**
- `user_id` (path) - User ID (integer)
- `k` (query, optional) - Number of recommendations (default: 20)
- `model` (query, optional) - Model name (default: current model)

**Example:**
```bash
curl "http://localhost:8080/recommend/42?k=10"
```

**Response:**
```json
{
  "user_id": 42,
  "model": "als",
  "items": [1, 50, 32, ...]
}
```

---

### `GET /metrics`
Prometheus metrics endpoint.

**Example:**
```bash
curl http://localhost:8080/metrics
```

**Key Metrics:**
- `recommend_requests_total{status="200"}` - Request counts
- `recommend_latency_seconds` - Request latency histogram
- `model_version_info{model_name, version, git_sha, data_snapshot}` - Active version
- `model_switches_total{from_version, to_version, status}` - Model switches
- `data_drift_psi{feature}` - Population Stability Index per feature
- `data_drift_kl{feature}` - KL divergence per feature

---

## Model Management

### `GET /switch`
Hot-swap active model version without restarting.

**Parameters:**
- `model` (query, required) - Model version (e.g., "v0.3")

**Example:**
```bash
curl "http://localhost:8080/switch?model=v0.3"
```

**Response:**
```json
{
  "status": "ok",
  "model_name": "als",
  "model_version": "v0.3",
  "previous_version": "v0.2",
  "meta": {
    "version": {
      "version": "v0.3",
      "git_sha": "207521e0d08abb271998cc9790a9d006e1b0f4eb",
      "data_snapshot_id": "9c1de44291dc0a7b0f0354cf256a383cd33ce9ea7adcf8debe3d9bc2786b3175",
      "created_at": "2025-11-19T17:39:29.144403+00:00"
    },
    "model": {
      "type": "ALS",
      "factors": 64,
      "hr": 0.0138,
      "ndcg": 0.0058
    }
  }
}
```

**Error Responses:**
- `400` - Missing model parameter
- `404` - Model version not found
- `500` - Switch failed

---

## Rollout Management

### `GET /rollout/status`
Get current rollout configuration and active version.

**Example:**
```bash
curl http://localhost:8080/rollout/status
```

**Response:**
```json
{
  "rollout": {
    "strategy": "canary",
    "primary_version": "v0.3",
    "canary_version": "v0.4",
    "canary_percentage": 10.0,
    "environment": "production"
  },
  "active_version": "v0.3"
}
```

---

### `POST /rollout/update`
Dynamically update rollout configuration.

**Parameters:**
- `strategy` (query, optional) - Rollout strategy: `fixed`, `canary`, `ab_test`, `shadow`
- `canary_version` (query, optional) - Canary/test version
- `canary_percentage` (query, optional) - Canary traffic percentage (0-100)

**Examples:**

**Start canary deployment:**
```bash
curl -X POST "http://localhost:8080/rollout/update?strategy=canary&canary_version=v0.4&canary_percentage=10"
```

**Increase canary traffic:**
```bash
curl -X POST "http://localhost:8080/rollout/update?canary_percentage=25"
```

**A/B test:**
```bash
curl -X POST "http://localhost:8080/rollout/update?strategy=ab_test&canary_version=v0.4"
```

**Reset to fixed:**
```bash
curl -X POST "http://localhost:8080/rollout/update?strategy=fixed"
```

**Response:**
```json
{
  "status": "ok",
  "rollout": {
    "strategy": "canary",
    "primary_version": "v0.3",
    "canary_version": "v0.4",
    "canary_percentage": 10.0,
    "environment": "production"
  }
}
```

**Error Responses:**
- `400` - Invalid strategy

---

## Rollout Strategies

### `fixed` (Default)
All traffic goes to the primary version.

```bash
ROLLOUT_STRATEGY=fixed
MODEL_VERSION=v0.3
```

### `canary`
Gradual rollout to a percentage of users (deterministic based on user_id).

```bash
ROLLOUT_STRATEGY=canary
MODEL_VERSION=v0.3          # Primary: 90% traffic
CANARY_VERSION=v0.4         # Canary: 10% traffic
CANARY_PERCENTAGE=10
```

**Routing logic:**
```python
if (user_id % 100) < canary_percentage:
    use canary_version
else:
    use primary_version
```

### `ab_test`
50/50 split based on user_id parity.

```bash
ROLLOUT_STRATEGY=ab_test
MODEL_VERSION=v0.3          # Version A (odd user_ids)
CANARY_VERSION=v0.4         # Version B (even user_ids)
```

**Routing logic:**
```python
if user_id % 2 == 0:
    use canary_version  # Version B
else:
    use primary_version  # Version A
```

### `shadow`
Production model serves responses; canary runs in shadow mode (logged only).

```bash
ROLLOUT_STRATEGY=shadow
MODEL_VERSION=v0.3          # Production (served)
CANARY_VERSION=v0.4         # Shadow (logged)
```

---

## Workflow Examples

### 1. Gradual Canary Rollout

```bash
# 1. Start with 5% canary
curl -X POST "http://localhost:8080/rollout/update?strategy=canary&canary_version=v0.4&canary_percentage=5"

# 2. Monitor metrics, then increase
curl -X POST "http://localhost:8080/rollout/update?canary_percentage=10"
curl -X POST "http://localhost:8080/rollout/update?canary_percentage=25"
curl -X POST "http://localhost:8080/rollout/update?canary_percentage=50"

# 3. Full rollout
curl "http://localhost:8080/switch?model=v0.4"
curl -X POST "http://localhost:8080/rollout/update?strategy=fixed"
```

### 2. Emergency Rollback

```bash
# Immediately switch to previous stable version
curl "http://localhost:8080/switch?model=v0.2"

# Verify
curl http://localhost:8080/healthz
```

### 3. A/B Test Setup

```bash
# Setup test
curl -X POST "http://localhost:8080/rollout/update?strategy=ab_test&canary_version=v0.4"

# Run for 1-2 weeks, analyze metrics

# Choose winner
curl "http://localhost:8080/switch?model=v0.4"
curl -X POST "http://localhost:8080/rollout/update?strategy=fixed"
```

---

## Environment Variables

### Model Configuration
```bash
MODEL_NAME=als                      # Model type (als, ncf, itemcf, popularity)
MODEL_VERSION=v0.3                  # Primary version
MODEL_REGISTRY=model_registry       # Registry path
```

### Rollout Configuration
```bash
ROLLOUT_STRATEGY=fixed              # Strategy: fixed, canary, ab_test, shadow
CANARY_VERSION=v0.4                 # Canary version (optional)
CANARY_PERCENTAGE=10                # Canary percentage 0-100 (optional)
ENVIRONMENT=production              # Environment label
```

### Kafka Configuration
```bash
KAFKA_BOOTSTRAP=server:9092
KAFKA_API_KEY=your-key
KAFKA_API_SECRET=your-secret
```

---

## Monitoring

### Grafana Dashboard
- **URL**: http://localhost:3000 (local) or AWS ALB:3000
- **Credentials**: admin / admin

**Key Panels:**
- Request rate & latency (p50, p95, p99)
- Error rate & 4xx/5xx breakdown
- Model version info
- Drift metrics (PSI, KL divergence)

### Prometheus Queries

**Active model version:**
```promql
model_version_info{model_name="als"}
```

**Model switch rate:**
```promql
rate(model_switches_total[5m])
```

**Failed switches:**
```promql
model_switches_total{status!="success"}
```

**Request latency p95:**
```promql
histogram_quantile(0.95, rate(recommend_latency_seconds_bucket[5m]))
```

**Error rate:**
```promql
rate(recommend_requests_total{status="500"}[5m]) / rate(recommend_requests_total[5m])
```

---

## Testing

Run the test suite:
```bash
./scripts/test_rollout.sh
```

Manual testing:
```bash
# Test recommendation
curl "http://localhost:8080/recommend/42?k=10"

# Test switch
curl "http://localhost:8080/switch?model=v0.3"

# Test canary
curl -X POST "http://localhost:8080/rollout/update?strategy=canary&canary_version=v0.4&canary_percentage=10"

# Check metrics
curl http://localhost:8080/metrics | grep model_version
```

---

## A/B Testing & Experimentation

### `GET /experiment/analyze`
Analyze A/B test results with statistical testing.

**Parameters:**
- `time_window_minutes` (query, optional) - Analysis time window in minutes (default: 60)

**Requirements:**
- Rollout strategy must be set to `ab_test`
- Sufficient traffic must have been collected

**Example:**
```bash
curl "http://localhost:8080/experiment/analyze?time_window_minutes=120"
```

**Response:**
```json
{
  "experiment": {
    "strategy": "ab_test",
    "time_window_minutes": 120,
    "variant_A": "v0.2",
    "variant_B": "v0.3"
  },
  "metrics": {
    "variant_A": {
      "requests": 1500,
      "successes": 1275,
      "success_rate": 0.85,
      "latency_p95_ms": 45.2
    },
    "variant_B": {
      "requests": 1500,
      "successes": 1350,
      "success_rate": 0.90,
      "latency_p95_ms": 47.8
    }
  },
  "statistical_analysis": {
    "metric": "success_rate",
    "test": "two_proportion_z_test",
    "results": {
      "z_statistic": 3.87,
      "p_value": 0.0001,
      "confidence_interval": [0.03, 0.07],
      "delta": 0.05,
      "variant_a_rate": 0.85,
      "variant_b_rate": 0.90,
      "sample_size_a": 1500,
      "sample_size_b": 1500,
      "significant": true
    },
    "decision": "ship_variant_b",
    "recommendation": "Variant B is significantly better (+0.0500, p=0.0001). Recommend shipping Variant B."
  },
  "latency_comparison": {
    "variant_A_p95_ms": 45.2,
    "variant_B_p95_ms": 47.8,
    "delta_ms": 2.6,
    "percent_change": 5.8
  }
}
```

**Error Responses:**
- `400` - Not in A/B test mode
- `500` - Failed to query metrics from Prometheus

**Statistical Analysis**:
- **Two-Proportion Z-Test**: Tests if success rates differ significantly between variants
- **P-value < 0.05**: Statistically significant difference
- **Confidence Interval**: 95% CI for effect size (delta)
- **Decision Logic**:
  - `ship_variant_a`: Keep control variant
  - `ship_variant_b`: Ship treatment variant
  - `no_difference`: Either variant acceptable
  - `inconclusive`: Need more data

**Example Workflow:**
```bash
# 1. Start A/B test
curl -X POST "http://localhost:8080/rollout/update?strategy=ab_test&canary_version=v0.3"

# 2. Generate traffic (wait for sufficient samples)

# 3. Analyze results
curl "http://localhost:8080/experiment/analyze?time_window_minutes=120"

# 4. Generate report
python scripts/ab_report.py --time-window 120

# 5. Make decision and ship (if recommended)
curl "http://localhost:8080/switch?model=v0.3"
```

---

## CLI Tools

### A/B Test Report Generator

Generate a comprehensive markdown report for A/B test experiments.

**Usage:**
```bash
python scripts/ab_report.py [OPTIONS]
```

**Options:**
- `--api-url URL` - API base URL (default: http://localhost:8080)
- `--time-window MINUTES` - Analysis time window (default: 60)
- `--output PATH` - Output file path (default: reports/ab_test_YYYY-MM-DD.md)

**Example:**
```bash
python scripts/ab_report.py --time-window 120 --output reports/experiment_v0.3.md
```

**Output**: Markdown report with:
- Experiment summary
- Metrics comparison table
- Statistical test results
- Decision recommendation
- Next steps

---

## Additional Resources

- [A/B Testing Guide](AB_TESTING_GUIDE.md) - Complete guide to running experiments
- [Rollout Guide](ROLLOUT_GUIDE.md) - Comprehensive deployment guide
- [README](../README.md) - Project overview
- [GitHub Workflows](../.github/workflows/) - CI/CD pipelines
