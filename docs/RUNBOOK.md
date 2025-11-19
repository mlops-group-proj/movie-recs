# Movie Recommender System - Operations Runbook

**Last Updated**: 2025-11-19
**Owner**: Team MedicalAI
**Escalation**: [Team contact info]

---

## Table of Contents
1. [Overview](#overview)
2. [SLO Targets](#slo-targets)
3. [Alert Handling](#alert-handling)
4. [Common Issues](#common-issues)
5. [Escalation Procedures](#escalation-procedures)
6. [Useful Commands](#useful-commands)

---

## Overview

This runbook provides operational guidance for the Movie Recommender System. It includes procedures for responding to alerts, diagnosing common issues, and escalating problems.

### Service Architecture
- **API Service**: FastAPI serving recommendations
- **Monitoring**: Prometheus + Grafana
- **Deployment**: AWS ECS Fargate / Docker Compose
- **Model Registry**: Versioned ML models (v0.1, v0.2, v0.3...)

### Quick Links
- **Grafana Dashboard**: http://localhost:3000/d/movie-recs-slo
- **Prometheus**: http://localhost:9090
- **API Health**: http://localhost:8080/healthz
- **Metrics**: http://localhost:8080/metrics

---

## SLO Targets

| Metric | Target | Measurement Window |
|--------|--------|-------------------|
| **Availability** | ≥ 99.9% | Rolling 30 days |
| **Latency (P95)** | ≤ 100ms | Rolling 5 minutes |
| **Latency (P99)** | ≤ 500ms | Rolling 5 minutes |
| **Error Rate** | ≤ 1% | Rolling 5 minutes |

---

## Alert Handling

### High Latency (P95)

**Alert**: `HighLatencyP95`
**Severity**: Warning
**Threshold**: P95 latency > 100ms for 2 minutes

#### Immediate Actions
1. **Check the dashboard**: Verify latency spike in Grafana
2. **Check request rate**: Is there a traffic spike?
   ```bash
   curl http://localhost:9090/api/v1/query?query=rate(recommend_requests_total[5m])
   ```
3. **Check error rate**: Are errors causing slowness?

#### Investigation
```bash
# Check service logs
docker logs movie-recommender --tail 100

# Check resource usage
curl -s http://localhost:8080/metrics | grep process_resident_memory

# Check model version
curl http://localhost:8080/healthz
```

#### Common Causes & Solutions

| Cause | Solution |
|-------|----------|
| **High traffic** | Scale horizontally (add more containers) |
| **Memory pressure** | Restart service, check for memory leaks |
| **Slow model inference** | Switch to lighter model (e.g., v0.2 → popularity) |
| **Cold start** | Wait 30s for model warm-up |

#### Resolution Steps
```bash
# Option 1: Restart service (if memory issue)
docker compose restart api

# Option 2: Switch to faster model
curl "http://localhost:8080/switch?model=v_popularity"

# Option 3: Scale up (if traffic spike)
docker compose up -d --scale api=3
```

#### Escalation
- If latency > 500ms for > 5 minutes → Escalate to ML Lead
- If no improvement after 15 minutes → Page on-call engineer

---

### High Error Rate

**Alert**: `HighErrorRate` or `CriticalErrorRate`
**Severity**: Warning / Critical
**Threshold**: Error rate > 1% (warning) or > 5% (critical)

#### Immediate Actions
1. **Check error types**:
   ```bash
   curl -s http://localhost:8080/metrics | grep recommend_errors_total
   ```
2. **Check recent logs** for stack traces:
   ```bash
   docker logs movie-recommender --tail 50 --since 5m
   ```
3. **Verify model availability**:
   ```bash
   ls -la model_registry/$(cat model_registry/latest.txt)
   ```

#### Common Errors

##### `invalid_model` Errors
**Symptom**: Users requesting unsupported model names

**Fix**:
```bash
# Check which models are being requested
docker logs movie-recommender | grep "Only ALS model supported"

# Update API documentation to clarify supported models
```

##### `internal_error` Errors
**Symptom**: Model inference failures

**Root Causes**:
1. **Model loading failed**: Check model files exist
2. **User not in training data**: Expected behavior (return empty list)
3. **Corrupted model**: Rollback to previous version

**Fix**:
```bash
# Rollback to last known good version
curl "http://localhost:8080/switch?model=v0.2"

# Verify
curl http://localhost:8080/healthz
```

#### Resolution
- **< 2% error rate**: Monitor, investigate root cause
- **2-5% error rate**: Rollback to previous model version
- **> 5% error rate**: Immediate rollback + page on-call

---

### Service Down

**Alert**: `ServiceDown`
**Severity**: Critical
**Threshold**: Service unreachable for 1 minute

#### Immediate Actions
1. **Verify service status**:
   ```bash
   docker ps | grep movie-recommender
   curl http://localhost:8080/healthz
   ```

2. **Check if container is running**:
   ```bash
   docker logs movie-recommender --tail 100
   ```

#### Common Causes

| Symptom | Cause | Solution |
|---------|-------|----------|
| Container restarting | Crash loop | Check logs, fix error, rebuild |
| Container not found | Stopped manually | `docker compose up -d api` |
| Port not accessible | Firewall/network | Check security groups, port binding |
| OOMKilled | Out of memory | Increase memory limit |

#### Resolution Steps
```bash
# Step 1: Check container status
docker ps -a | grep movie-recommender

# Step 2: Check why it stopped
docker logs movie-recommender --tail 200

# Step 3: Restart service
docker compose up -d api

# Step 4: Verify health
curl http://localhost:8080/healthz
```

#### Escalation
- If service doesn't start after restart → Escalate immediately
- If OOMKilled repeatedly → Escalate to Cloud Engineer

---

### Low Availability

**Alert**: `LowAvailability`
**Severity**: Warning
**Threshold**: 30-minute availability < 99.9%

#### Investigation
```bash
# Check error distribution
curl -s http://localhost:8080/metrics | grep recommend_requests_total

# Calculate availability
# Availability = (2xx requests) / (total requests)
```

#### Common Causes
- Intermittent errors (investigate error logs)
- Service restarts (check uptime metric)
- Resource constraints (CPU/memory)

#### Resolution
1. Identify error source (see [High Error Rate](#high-error-rate))
2. Fix root cause
3. Monitor for 30 minutes to confirm recovery

---

### Model Load Failure

**Alert**: `ModelLoadFailure`
**Severity**: Warning
**Threshold**: > 10 model errors in 5 minutes

#### Immediate Actions
1. **Check model files**:
   ```bash
   MODEL_VERSION=$(curl -s http://localhost:8080/healthz | python3 -c "import sys,json; print(json.load(sys.stdin)['version'])")
   ls -lh model_registry/$MODEL_VERSION/als/
   ```

2. **Verify model integrity**:
   ```bash
   # Check file sizes
   du -sh model_registry/$MODEL_VERSION/als/*

   # Compare with previous version
   du -sh model_registry/v0.2/als/*
   ```

#### Resolution
```bash
# Rollback to previous version
curl "http://localhost:8080/switch?model=v0.2"

# If rollback fails, restart service
docker compose restart api
```

#### Prevention
- Always test new models in staging first
- Verify model files after export
- Keep at least 2 previous versions in registry

---

### High Data Drift

**Alert**: `HighDataDrift`
**Severity**: Warning
**Threshold**: PSI > 0.2 for any feature

#### Investigation
```bash
# Check drift metrics
curl -s http://localhost:8080/metrics | grep data_drift_psi

# View drift details in Grafana
# Dashboard: Drift Dashboard
# http://localhost:3000/d/drift
```

#### Response
1. **Document the drift**: Note which features are drifting
2. **Evaluate impact**: Check if model performance is degrading
3. **Plan retraining**: Schedule model retrain with recent data

#### Actions
- **PSI 0.2-0.3**: Plan retrain within 1 week
- **PSI 0.3-0.5**: Retrain within 2-3 days
- **PSI > 0.5**: Immediate retrain required

```bash
# Trigger manual retrain
gh workflow run retrain.yml
```

---

## Common Issues

### Issue: Slow Cold Start

**Symptom**: First requests after deployment are slow (> 1s)

**Cause**: Model loading on first request

**Solution**: Warm-up period is normal. Consider:
```bash
# Pre-warm the model after deployment
for i in {1..10}; do
  curl -s "http://localhost:8080/recommend/42?k=10" > /dev/null
done
```

---

### Issue: Memory Growing Over Time

**Symptom**: Memory usage increases gradually

**Investigation**:
```bash
# Monitor memory over time
curl -s http://localhost:8080/metrics | grep process_resident_memory_bytes

# Check for leaks
docker stats movie-recommender
```

**Solution**:
```bash
# Restart service
docker compose restart api

# If recurring, investigate code for memory leaks
```

---

### Issue: Prometheus Not Scraping

**Symptom**: No metrics in Grafana

**Check**:
```bash
# Verify Prometheus can reach API
docker exec prometheus wget -O- http://api:8080/metrics

# Check Prometheus targets
curl http://localhost:9090/api/v1/targets
```

**Fix**:
```bash
# Restart Prometheus
docker compose restart prometheus
```

---

## Escalation Procedures

### Escalation Levels

| Level | When to Escalate | Contact |
|-------|------------------|---------|
| **L1** | Initial alert, following runbook | On-call engineer |
| **L2** | Issue not resolved in 15 min | Team Lead / ML Lead |
| **L3** | Service down > 30 min | Project Manager + Cloud Engineer |
| **L4** | Business-critical outage | All stakeholders |

### Escalation Template

```
ALERT: [Alert Name]
SEVERITY: [Critical/Warning/Info]
DURATION: [How long has this been happening]
IMPACT: [What's affected]
ACTIONS TAKEN: [What you've tried]
CURRENT STATUS: [Current state]
NEXT STEPS: [What you recommend]
```

### Contact Information

| Role | Name | Contact | Backup |
|------|------|---------|--------|
| Project Manager | Daniel Zimmerman | [contact] | - |
| ML Lead | LakshmiNarayana Latchireddi | [contact] | - |
| Cloud Engineer | Krushal Kalkani | [contact] | - |
| Data Lead | Arvin Nourian | [contact] | - |

---

## Useful Commands

### Health Checks
```bash
# API health
curl http://localhost:8080/healthz

# Detailed metrics
curl http://localhost:8080/metrics

# Rollout status
curl http://localhost:8080/rollout/status
```

### Monitoring
```bash
# View Prometheus alerts
curl http://localhost:9090/api/v1/alerts

# Query specific metric
curl "http://localhost:9090/api/v1/query?query=up"

# Check Grafana dashboards
open http://localhost:3000
```

### Model Management
```bash
# List available models
ls model_registry/

# Switch model version
curl "http://localhost:8080/switch?model=v0.3"

# Check current version
curl http://localhost:8080/healthz | jq '.version'
```

### Container Management
```bash
# View logs
docker logs movie-recommender -f

# Restart service
docker compose restart api

# Check resource usage
docker stats movie-recommender

# Shell into container
docker exec -it movie-recommender /bin/bash
```

### Performance Testing
```bash
# Load test (requires apache-bench)
ab -n 1000 -c 10 http://localhost:8080/recommend/42?k=10

# Check latency percentiles
curl -s http://localhost:8080/metrics | grep recommend_latency_seconds
```

---

## Appendix

### SLO Calculations

**Availability**:
```
Availability = (Successful Requests) / (Total Requests) * 100
             = (2xx responses) / (all responses) * 100
```

**Error Rate**:
```
Error Rate = (Failed Requests) / (Total Requests) * 100
           = (5xx responses) / (all responses) * 100
```

**Error Budget**:
```
Error Budget = (1 - SLO Target) * Total Requests
             = (1 - 0.999) * Total Requests
             = 0.1% of requests can fail
```

### PromQL Queries

**P95 Latency**:
```promql
histogram_quantile(0.95,
  sum(rate(recommend_latency_seconds_bucket[5m])) by (le)
)
```

**Error Rate**:
```promql
sum(rate(recommend_requests_total{status=~"5.."}[5m]))
/
sum(rate(recommend_requests_total[5m]))
```

**Availability**:
```promql
sum(rate(recommend_requests_total{status=~"2.."}[30m]))
/
sum(rate(recommend_requests_total[30m]))
```

---

## Changelog

| Date | Author | Changes |
|------|--------|---------|
| 2025-11-19 | Claude Code | Initial runbook creation |

---

**Remember**: When in doubt, escalate early! It's better to loop in help sooner rather than later.
