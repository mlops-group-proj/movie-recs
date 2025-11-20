# A/B Testing Guide - Movie Recommender System

**Last Updated**: 2025-11-19
**Owner**: MLOps Team

---

## Table of Contents
1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Setting Up an A/B Test](#setting-up-an-ab-test)
4. [Running the Experiment](#running-the-experiment)
5. [Analyzing Results](#analyzing-results)
6. [Making Decisions](#making-decisions)
7. [Statistical Methods](#statistical-methods)
8. [Best Practices](#best-practices)

---

## Overview

The Movie Recommender System supports A/B testing to compare different model versions in production. This guide covers how to:

- Set up A/B experiments
- Collect metrics automatically
- Run statistical tests (two-proportion z-test, bootstrap CIs)
- Generate experiment reports
- Make data-driven ship/no-ship decisions

### Routing Logic

**A/B Test Strategy**: `user_id % 2`
- **Variant A** (Control): Even `user_id`s → Primary version
- **Variant B** (Treatment): Odd `user_id`s → Canary version

This ensures a **deterministic 50/50 split** based on user ID.

---

## Quick Start

### 1. Start A/B Test

```bash
# Set environment variables
export ROLLOUT_STRATEGY=ab_test
export MODEL_VERSION=v0.2          # Variant A (control)
export CANARY_VERSION=v0.3         # Variant B (treatment)

# Or update via API
curl -X POST "http://localhost:8080/rollout/update?strategy=ab_test&canary_version=v0.3"
```

### 2. Generate Traffic

```bash
# Simulate user requests
for user_id in {1..1000}; do
    curl -s "http://localhost:8080/recommend/$user_id?k=10" > /dev/null
done
```

### 3. Analyze Results

```bash
# Generate experiment report
python scripts/ab_report.py --time-window 60 --output reports/experiment.md
```

### 4. View Report

```bash
cat reports/experiment.md
```

---

## Setting Up an A/B Test

### Step 1: Define Hypothesis

**Example Hypothesis**:
> "Model v0.3 (with updated hyperparameters) will improve recommendation success rate by at least 2 percentage points compared to v0.2."

### Step 2: Choose Metric

Common metrics:
- **Success Rate**: Proportion of 200 vs 500 status codes
- **Latency (P95)**: 95th percentile response time
- **Error Rate**: Proportion of failed requests

**Primary Metric**: Success rate (used for statistical testing)
**Secondary Metrics**: Latency, error rate (monitored but not gating)

### Step 3: Calculate Sample Size

```python
from service.ab_analysis import calculate_sample_size

# Calculate required sample size
n = calculate_sample_size(
    baseline_rate=0.85,    # Current success rate: 85%
    mde=0.02,              # Minimum detectable effect: 2pp
    alpha=0.05,            # Significance level: 5%
    power=0.80             # Statistical power: 80%
)
print(f"Required sample size per variant: {n}")
# Output: Required sample size per variant: 2435
```

### Step 4: Configure Rollout

```bash
curl -X POST "http://localhost:8080/rollout/update" \
  -d "strategy=ab_test" \
  -d "canary_version=v0.3"
```

Verify:
```bash
curl http://localhost:8080/rollout/status
```

---

## Running the Experiment

### Monitor Real-Time Metrics

**Prometheus Metrics**:
```promql
# Request counts by variant
ab_test_requests_total{variant="variant_A"}
ab_test_requests_total{variant="variant_B"}

# Latency by variant
histogram_quantile(0.95, rate(ab_test_latency_seconds_bucket{variant="variant_A"}[5m]))
histogram_quantile(0.95, rate(ab_test_latency_seconds_bucket{variant="variant_B"}[5m]))
```

**Grafana Dashboard**:
- URL: http://localhost:3000
- Look for A/B test panels (if added to SLO dashboard)

### Check Experiment Status

```bash
curl "http://localhost:8080/experiment/analyze?time_window_minutes=60"
```

---

## Analyzing Results

### Option 1: API Analysis

```bash
curl "http://localhost:8080/experiment/analyze?time_window_minutes=120" | python -m json.tool
```

**Response**:
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
      "success_rate": 0.85
    },
    "variant_B": {
      "requests": 1500,
      "successes": 1350,
      "success_rate": 0.90
    }
  },
  "statistical_analysis": {
    "metric": "success_rate",
    "test": "two_proportion_z_test",
    "results": {
      "z_statistic": 3.87,
      "p_value": 0.0001,
      "delta": 0.05,
      "significant": true
    },
    "decision": "ship_variant_b",
    "recommendation": "Variant B is significantly better (+0.0500, p=0.0001). Recommend shipping Variant B."
  }
}
```

### Option 2: CLI Report

```bash
python scripts/ab_report.py --time-window 120
```

**Output**: `reports/ab_test_2025-11-19.md`

---

## Making Decisions

The system automatically recommends one of four decisions:

### 1. *  Ship Variant B

**Criteria**:
- Sample size ≥ 1,000 per variant * 
- P-value < 0.05 (statistically significant) * 
- Effect size > 1 percentage point (practically significant) * 
- Variant B performs **better** than Variant A

**Action**:
```bash
# Full rollout to Variant B
curl "http://localhost:8080/switch?model=v0.3"
curl -X POST "http://localhost:8080/rollout/update?strategy=fixed"

# Update environment
echo "MODEL_VERSION=v0.3" >> .env
```

### 2. *  Keep Variant A

**Criteria**:
- Sample size ≥ 1,000 per variant * 
- P-value < 0.05 * 
- Effect size > 1pp * 
- Variant A performs **better** than Variant B

**Action**:
```bash
# Keep current version, stop experiment
curl -X POST "http://localhost:8080/rollout/update?strategy=fixed"
```

### 3. ⚖️ No Difference

**Criteria**:
- Sample size sufficient * 
- P-value ≥ 0.05 (not statistically significant) OR
- Effect size ≤ 1 percentage point (too small to matter)

**Action**:
- Safe to ship either variant
- Choose based on other criteria (cost, maintainability, etc.)

### 4. ⏳ Inconclusive

**Criteria**:
- Sample size < 1,000 per variant XX

**Action**:
```bash
# Continue experiment, collect more data
# Check again after more traffic
python scripts/ab_report.py --time-window 240  # Try 4 hours
```

---

## Statistical Methods

### Two-Proportion Z-Test

**Purpose**: Test if success rates differ between variants

**Hypotheses**:
- **H0** (Null): `p_A = p_B` (no difference)
- **H1** (Alternative): `p_A ≠ p_B` (there is a difference)

**Test Statistic**:
```
z = (p_B - p_A) / SE
```

where `SE = sqrt(p_pooled * (1 - p_pooled) * (1/n_A + 1/n_B))`

**Decision Rule**:
- If `p-value < 0.05`: Reject H0 (significant difference)
- If `p-value ≥ 0.05`: Fail to reject H0 (no significant difference)

**Confidence Interval**:
95% CI for effect size: `delta ± 1.96 * SE_diff`

### Bootstrap Confidence Intervals

**Purpose**: Estimate uncertainty in metric deltas (e.g., latency difference)

**Method**:
1. Resample data with replacement (10,000 times)
2. Compute metric for each bootstrap sample
3. Calculate 95% CI using percentile method

**Use Cases**:
- Non-normal metrics (e.g., P95 latency)
- Small sample sizes
- Robustness checks

---

## Best Practices

### 1. Sample Size Planning

*  **Always calculate required sample size** before starting
```python
from service.ab_analysis import calculate_sample_size
n = calculate_sample_size(baseline_rate=0.85, mde=0.02)
```

XX Don't run experiments with insufficient data

### 2. Experiment Duration

*  **Run for multiple days** to account for:
- Day-of-week effects
- Time-of-day variations
- User behavior changes

XX Don't make decisions based on <24 hours of data

### 3. Multiple Testing Correction

*  **Decide on primary metric beforehand**
- Primary: Success rate (gating decision)
- Secondary: Latency, error rate (guardrail metrics)

XX Don't cherry-pick metrics post-hoc

### 4. Guardrail Metrics

*  **Monitor secondary metrics** even if not used for decision:
```json
"latency_comparison": {
  "delta_ms": +5.2,
  "percent_change": +8.5
}
```

XX Don't ignore significant latency regressions

### 5. Rollback Plan

*  **Always have a rollback ready**:
```bash
# Instant rollback to previous version
curl "http://localhost:8080/switch?model=v0.2"
```

XX Don't ship without ability to revert

### 6. Documentation

*  **Document every experiment**:
- Hypothesis
- Metrics chosen
- Sample size calculation
- Results and decision
- Post-ship monitoring plan

Use the auto-generated reports as starting point.

---

## Example Experiment Workflow

### Complete End-to-End Example

```bash
# 1. Calculate sample size
python -c "from service.ab_analysis import calculate_sample_size; print(calculate_sample_size(0.85, 0.02))"
# Output: 2435 samples per variant needed

# 2. Start A/B test
curl -X POST "http://localhost:8080/rollout/update?strategy=ab_test&canary_version=v0.3"

# 3. Generate traffic (in production or via load test)
# Wait for 2435+ requests per variant

# 4. Check progress
curl "http://localhost:8080/experiment/analyze?time_window_minutes=120" | jq '.metrics'

# 5. Generate report when ready
python scripts/ab_report.py --time-window 240

# 6. Make decision based on report
# If recommendation is "ship_variant_b":
curl "http://localhost:8080/switch?model=v0.3"
curl -X POST "http://localhost:8080/rollout/update?strategy=fixed"

# 7. Monitor post-ship for 48 hours
# Check Grafana SLO dashboard for regressions
```

---

## Troubleshooting

### "Insufficient Data" Message

**Problem**: Not enough samples collected

**Solution**:
```bash
# Check current sample size
curl "http://localhost:8080/experiment/analyze?time_window_minutes=60" | jq '.metrics'

# Generate more traffic
./scripts/generate_traffic.sh  # If you have a load testing script
```

### No Metrics in Prometheus

**Problem**: A/B test metrics not appearing

**Checks**:
1. Verify A/B test mode is active:
   ```bash
   curl http://localhost:8080/rollout/status
   ```
2. Send test requests:
   ```bash
   curl "http://localhost:8080/recommend/10?k=5"  # Even user_id → Variant A
   curl "http://localhost:8080/recommend/11?k=5"  # Odd user_id → Variant B
   ```
3. Check metrics endpoint:
   ```bash
   curl http://localhost:8080/metrics | grep ab_test
   ```

### API Returns "Not in A/B test mode"

**Problem**: Rollout strategy not set to `ab_test`

**Solution**:
```bash
curl -X POST "http://localhost:8080/rollout/update?strategy=ab_test&canary_version=v0.3"
```

---

## API Reference

See [API_REFERENCE.md](API_REFERENCE.md) for complete endpoint documentation.

**Key Endpoints**:
- `POST /rollout/update` - Configure A/B test
- `GET /rollout/status` - Check current config
- `GET /recommend/{user_id}` - Get recommendations (with A/B routing)
- `GET /experiment/analyze` - Analyze experiment results

---

## Further Reading

- [API Reference](API_REFERENCE.md)
- [Runbook](RUNBOOK.md)
- [Statistical Testing Theory](https://en.wikipedia.org/wiki/Two-proportion_z-test)
- [Bootstrap Methods](https://en.wikipedia.org/wiki/Bootstrapping_(statistics))

---

**Generated by**: MLOps Team
**Last Updated**: 2025-11-19
