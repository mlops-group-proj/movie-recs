# Model Rollout & Deployment Guide

This guide explains how to use the automated retraining, hot-swap, and rollout features of the Movie Recommender System.

---

## Table of Contents
1. [Automated Retraining](#automated-retraining)
2. [Model Registry Versioning](#model-registry-versioning)
3. [Hot-Swap Endpoint](#hot-swap-endpoint)
4. [Rollout Strategies](#rollout-strategies)
5. [Prometheus Metrics](#prometheus-metrics)
6. [Examples & Workflows](#examples--workflows)

---

## Automated Retraining

### Schedule
The retraining workflow ([.github/workflows/retrain.yml](../.github/workflows/retrain.yml)) runs:
- **Automatically**: Every Monday & Thursday at 05:30 UTC
- **Manually**: Via GitHub Actions `workflow_dispatch`

### What It Does
1. Trains an ALS recommender on the latest data
2. Exports artifacts to the model registry with version increment
3. Commits the new version to the repository
4. Uploads artifacts as GitHub workflow artifacts
5. Generates a summary with version and metrics

### Trigger Manual Retrain
```bash
# Via GitHub UI: Actions → Automated Retrain → Run workflow

# Or via GitHub CLI:
gh workflow run retrain.yml
```

### Output
- New version created (e.g., `v0.4`)
- Model artifacts in `model_registry/v0.4/als/`
- Updated `model_registry/latest.txt`
- Commit message: `automated retrain: v0.4`

---

## Model Registry Versioning

### Structure
```
model_registry/
├── latest.txt          # Points to current version (e.g., "v0.3")
├── v0.1/
│   └── als/
│       ├── meta.json   # Model metadata & metrics
│       └── ...
├── v0.2/
│   └── als/
└── v0.3/
    ├── meta.json       # Version-level metadata
    └── als/
        ├── meta.json   # Model-specific metadata
        ├── user_factors.npy
        ├── item_factors.npy
        └── ...
```

### Metadata Schema
Version metadata (`model_registry/vX.Y/meta.json`):
```json
{
  "version": "v0.3",
  "created_at": "2025-11-19T17:39:29.144403+00:00",
  "model_name": "als",
  "git_sha": "207521e0...",
  "data_snapshot_id": "9c1de44291dc0a7b...",
  "image_digest": "",
  "exported_by": "github-actions[bot]",
  "artifact_sha": "b9ff55f2...",
  "artifact_size": 726586,
  "metrics": {
    "hr": 0.0138,
    "ndcg": 0.0058
  }
}
```

### Manual Export
```bash
python scripts/train_als.py \
    --ratings_csv data/ml1m_prepared/ratings.csv \
    --output_dir artifacts/latest/als

python scripts/export_model.py \
    --source artifacts/latest/als \
    --registry model_registry \
    --model-name als \
    --data-path data/ml1m_prepared/ratings.csv
```

---

## Hot-Swap Endpoint

### Switch Model Version
Change the active model version without restarting the service:

```bash
# Switch to v0.3
curl "http://localhost:8080/switch?model=v0.3"

# Response
{
  "status": "ok",
  "model_name": "als",
  "model_version": "v0.3",
  "previous_version": "v0.2",
  "meta": {
    "version": { "version": "v0.3", "git_sha": "207521e0...", ... },
    "model": { "type": "ALS", "factors": 64, ... }
  }
}
```

### Check Current Version
```bash
curl http://localhost:8080/healthz

# Response
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

## Rollout Strategies

The system supports multiple deployment strategies for gradual rollouts and A/B testing.

### 1. Fixed (Default)
All traffic goes to a single version.

```bash
# Configuration
ROLLOUT_STRATEGY=fixed
MODEL_VERSION=v0.3
```

### 2. Canary Deployment
Gradually route a percentage of traffic to a new version.

```bash
# Configuration
ROLLOUT_STRATEGY=canary
MODEL_VERSION=v0.3        # Primary (90%)
CANARY_VERSION=v0.4       # Canary (10%)
CANARY_PERCENTAGE=10
```

**How it works:**
- User IDs are hashed to determine routing
- `user_id % 100 < canary_percentage` → canary version
- Deterministic routing (same user always gets same version)

**Update canary percentage:**
```bash
curl -X POST "http://localhost:8080/rollout/update?strategy=canary&canary_version=v0.4&canary_percentage=25"
```

### 3. A/B Testing
Split traffic 50/50 between two versions based on user_id parity.

```bash
# Configuration
ROLLOUT_STRATEGY=ab_test
MODEL_VERSION=v0.3        # Version A (odd user_ids)
CANARY_VERSION=v0.4       # Version B (even user_ids)
```

**How it works:**
- Even user_ids → Version B (canary)
- Odd user_ids → Version A (primary)

### 4. Shadow Mode
Serve production model while logging canary predictions.

```bash
# Configuration
ROLLOUT_STRATEGY=shadow
MODEL_VERSION=v0.3        # Production (served)
CANARY_VERSION=v0.4       # Shadow (logged only)
```

### Dynamic Rollout Updates

```bash
# Start with 10% canary
curl -X POST "http://localhost:8080/rollout/update?strategy=canary&canary_version=v0.4&canary_percentage=10"

# Increase to 25%
curl -X POST "http://localhost:8080/rollout/update?strategy=canary&canary_version=v0.4&canary_percentage=25"

# Increase to 50%
curl -X POST "http://localhost:8080/rollout/update?strategy=canary&canary_version=v0.4&canary_percentage=50"

# Full rollout (switch to fixed)
curl "http://localhost:8080/switch?model=v0.4"
curl -X POST "http://localhost:8080/rollout/update?strategy=fixed"
```

### Check Rollout Status
```bash
curl http://localhost:8080/rollout/status

# Response
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

## Prometheus Metrics

### Model Version Metrics
```prometheus
# Current model version info
model_version_info{model_name="als", version="v0.3", git_sha="207521e0", data_snapshot="9c1de442"} 1

# Model switches
model_switches_total{from_version="v0.2", to_version="v0.3", status="success"} 1
model_switches_total{from_version="v0.3", to_version="v0.5", status="not_found"} 1
```

### Query Examples
```promql
# Current active version
model_version_info{model_name="als"}

# Model switch rate
rate(model_switches_total[5m])

# Failed switches
model_switches_total{status!="success"}
```

### Grafana Dashboard
Add these panels to your dashboard:
1. **Active Version**: `model_version_info` (stat panel)
2. **Switch History**: `model_switches_total` (time series)
3. **Rollout Strategy**: Custom variable from `/rollout/status`

---

## Examples & Workflows

### Example 1: Gradual Canary Rollout

```bash
# 1. Train new model (automated or manual)
gh workflow run retrain.yml
# Creates v0.4

# 2. Start with 5% canary
curl -X POST "http://localhost:8080/rollout/update?strategy=canary&canary_version=v0.4&canary_percentage=5"

# 3. Monitor metrics in Grafana
# - Error rates
# - Latency p95/p99
# - User engagement

# 4. Increase gradually
curl -X POST "http://localhost:8080/rollout/update?canary_percentage=25"
curl -X POST "http://localhost:8080/rollout/update?canary_percentage=50"

# 5. Full rollout
curl "http://localhost:8080/switch?model=v0.4"
curl -X POST "http://localhost:8080/rollout/update?strategy=fixed"
```

### Example 2: A/B Test for Model Comparison

```bash
# 1. Setup A/B test
curl -X POST "http://localhost:8080/rollout/update?strategy=ab_test&canary_version=v0.4"

# 2. Run for 1-2 weeks, collecting metrics

# 3. Analyze results
# - Compare HR@K, NDCG@K per version
# - Compare user engagement metrics
# - Statistical significance testing

# 4. Choose winner
curl "http://localhost:8080/switch?model=v0.4"  # If v0.4 wins
```

### Example 3: Emergency Rollback

```bash
# Immediately rollback to previous version
curl "http://localhost:8080/switch?model=v0.2"

# Verify
curl http://localhost:8080/healthz
```

### Example 4: Multi-Environment Deployment

**Staging:**
```bash
ENVIRONMENT=staging
MODEL_VERSION=v0.4
ROLLOUT_STRATEGY=fixed
```

**Production (canary):**
```bash
ENVIRONMENT=production
MODEL_VERSION=v0.3
ROLLOUT_STRATEGY=canary
CANARY_VERSION=v0.4
CANARY_PERCENTAGE=10
```

---

## Best Practices

1. **Always test in staging first** before production rollout
2. **Start with small canary percentages** (5-10%) and increase gradually
3. **Monitor metrics closely** during rollouts (error rates, latency, engagement)
4. **Keep rollback plan ready** - know the last stable version
5. **Document version changes** in commit messages and release notes
6. **Set up alerts** for anomalies during canary deployments
7. **Use deterministic routing** (canary strategy) for consistent user experience
8. **Track provenance** - git SHA, data snapshot, metrics for each version

---

## Troubleshooting

### Version Not Found
```bash
# Error: Model als version v0.5 not found
# Solution: Check available versions
ls model_registry/
cat model_registry/latest.txt
```

### Switch Failed
```bash
# Check Prometheus metrics
model_switches_total{status="error"}

# Check API logs
docker logs movie-recommender
```

### Rollout Not Working
```bash
# Verify rollout config
curl http://localhost:8080/rollout/status

# Check environment variables
docker exec movie-recommender env | grep ROLLOUT
```

---

## References
- [GitHub Actions Workflow](../.github/workflows/retrain.yml)
- [Export Script](../scripts/export_model.py)
- [API Implementation](../service/app.py)
- [Rollout Module](../service/rollout.py)
- [README](../README.md)
