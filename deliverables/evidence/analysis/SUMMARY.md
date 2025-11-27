## Analysis Summary

### Fairness Metrics

| Metric | Value | Threshold | Status |
|--------|-------|-----------|--------|
| Catalog Coverage | 37.2% | >= 40% | FAIL |
| Gini Coefficient | 0.213 | <= 0.35 | PASS |
| Top-10% Share | 21.2% | <= 30% | PASS |
| Tail Share | 78.8% | >= 70% | PASS |

### Feedback Loop Indicators

| Tier | Amplification | Interpretation |
|------|---------------|----------------|
| High | 5.70x | Over-represented |
| Medium | 2.86x | Over-represented |
| Low | 1.94x | Over-represented |
| Tail | 1.94x | Over-represented |

| Starvation Index | 63.5% | Items with zero exposure |

### Security Analysis

| Metric | Value |
|--------|-------|
| Total Events | 1094 |
| Unique Users | 193 |
| Schema Errors | 0 |
| Detection Threshold | 28.7 events |
| Flagged Users | 2 |

**Flagged Accounts:**

| User ID | Event Count | Multiple of Avg | Risk Level |
|---------|-------------|-----------------|------------|
| 9999 | 100 | 17.64x | HIGH |
| 8888 | 50 | 8.82x | MEDIUM |