# Quality Gates Documentation

## Overview

Quality gates are automated checkpoints that enforce quality standards before code can be merged or deployed. This project implements three critical quality gates:

1. **Unit Tests Gate** - All tests must pass
2. **Schema Validation Gate** - Kafka message schemas must be valid
3. **Backpressure Handling Gate** - System must handle load correctly

---

## Quick Start

### Run All Quality Gates

```bash
# Run all gates
python scripts/quality_gate.py

# Run with verbose output
python scripts/quality_gate.py --verbose
```

### Run Individual Gates

```bash
# Unit tests only
python scripts/quality_gate.py --gate unit-tests

# Schema validation only
python scripts/quality_gate.py --gate schema-validation

# Backpressure handling only
python scripts/quality_gate.py --gate backpressure

# Multiple gates
python scripts/quality_gate.py --gate unit-tests --gate schema-validation --verbose
```

---

## Quality Gate Details

### 1. Unit Tests Gate

**Purpose:** Ensures all unit tests pass before code can be merged.

**Criteria:**
- ✅ 100% pass rate required
- ✅ 0 test failures allowed
- ✅ All tests in `tests/` directory must execute

**What it validates:**
- Core functionality (StreamIngestor, schemas, consumer)
- Data integrity (parquet writes, batch processing)
- Error handling (invalid messages, timeouts)

**Threshold Configuration:**
```python
"unit_tests": {
    "min_pass_rate": 100,  # All tests must pass
    "max_failures": 0,
}
```

**Example Output:**
```
[✓ PASS] Unit Tests Gate
Tests Run: 25
Passed: 25
Failed: 0
Pass Rate: 100.0%
Threshold: ≥ 100% pass rate, ≤ 0 failures
```

---

### 2. Schema Validation Gate

**Purpose:** Ensures Kafka message schemas are correctly defined and validated.

**Criteria:**
- ✅ 100% schema validation tests pass
- ✅ All 4 schemas tested: watch, rate, reco_requests, reco_responses
- ✅ Valid and invalid message handling verified

**What it validates:**
- Avro schema definitions (WATCH_SCHEMA, RATE_SCHEMA, etc.)
- Message validation logic (validate_message, validate_schema)
- Required field presence (user_id, movie_id, timestamps)
- Data type enforcement (int, float, arrays)
- Array length constraints (movie_ids.length == scores.length)

**Threshold Configuration:**
```python
"schema_validation": {
    "min_pass_rate": 100,
    "max_failures": 0,
    "required_schemas": ["watch", "rate", "reco_requests", "reco_responses"],
}
```

**Schemas Validated:**

| Schema | Fields | Validation Rules |
|--------|--------|------------------|
| `WatchEvent` | user_id (int), movie_id (int), timestamp (string) | All required, timestamp auto-added |
| `RateEvent` | user_id (int), movie_id (int), rating (float), timestamp (string) | Rating must be numeric |
| `RecoRequest` | user_id (int), timestamp (string) | Minimal request schema |
| `RecoResponse` | user_id (int), movie_ids (array[int]), scores (array[float]), timestamp (string) | Arrays must match length |

**Example Output:**
```
[✓ PASS] Schema Validation Gate
Schema Tests Run: 18
Passed: 18
Failed: 0
Pass Rate: 100.0%
Required Schemas Covered: ✓
  - watch, rate, reco_requests, reco_responses
Threshold: 100% pass rate, all 4 schemas validated
```

---

### 3. Backpressure Handling Gate

**Purpose:** Ensures system can handle high load without data loss.

**Criteria:**
- ✅ 100% backpressure tests pass
- ✅ Minimum 5 test cases covering different scenarios
- ✅ Zero data loss under load verified

**What it validates:**
- **Batch Size Flushing:** Automatic flush at 1000 messages
- **Time-Based Flushing:** Automatic flush every 5 minutes
- **Multi-Topic Handling:** Independent buffering per topic
- **Data Integrity:** No message loss during backpressure
- **Metrics Tracking:** Accurate batch and message counts

**Required Test Cases:**
1. `test_batch_size_triggers_flush` - 100+ messages trigger automatic flush
2. `test_time_based_flush` - Time-based flush works without batch size
3. `test_multiple_topics_under_load` - Topics process independently
4. `test_no_data_loss_during_backpressure` - All messages preserved
5. `test_backpressure_metrics` - Accurate tracking under variable load

**Threshold Configuration:**
```python
"backpressure": {
    "min_pass_rate": 100,
    "max_failures": 0,
    "required_tests": 5,  # Must have at least 5 test cases
}
```

**Example Output:**
```
[✓ PASS] Backpressure Handling Gate
Backpressure Tests Run: 5 ✓
Passed: 5
Failed: 0
Pass Rate: 100.0%
Required Tests: ≥ 5 (batch size, time-based, data loss, etc.)
Threshold: 100% pass rate, ≥ 5 test cases
```

---

## CI/CD Integration

### GitHub Actions

Quality gates run automatically on:
- Pull requests to any branch
- Pushes to `main` and `Arvin` branches

**Workflow:** `.github/workflows/ci.yml`

Each gate runs as a separate step:
1. Unit Tests Gate
2. Schema Validation Gate
3. Backpressure Gate

**Status Checks:**
- ✅ All gates must pass to merge
- ❌ Any gate failure blocks the PR
- 📊 Results visible in GitHub Actions summary

### Local Pre-Commit Hook

Install the pre-commit hook to run gates before every commit:

```bash
# Install hook
cp scripts/pre-commit-hook.sh .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit

# Now gates run automatically on 'git commit'
git commit -m "Your message"
# 🔍 Running pre-commit quality gates...
# ✓ All quality gates passed
```

**Bypass (emergency only):**
```bash
git commit --no-verify -m "Emergency fix"
```

---

## Configuration

### Modifying Thresholds

Edit `scripts/quality_gate.py`:

```python
QUALITY_GATES = {
    "unit_tests": {
        "min_pass_rate": 100,  # Change to 95 for 95% pass rate
        "max_failures": 0,      # Change to 2 to allow 2 failures
    },
    "schema_validation": {
        "min_pass_rate": 100,
        "max_failures": 0,
        "required_schemas": ["watch", "rate", "reco_requests", "reco_responses"],
    },
    "backpressure": {
        "min_pass_rate": 100,
        "max_failures": 0,
        "required_tests": 5,    # Change to require more/fewer tests
    }
}
```

### Adding New Gates

1. Create a new gate class in `scripts/quality_gate.py`:

```python
class NewGate(QualityGate):
    def __init__(self, verbose: bool = False):
        super().__init__("New Gate Name", verbose)
    
    def run(self) -> bool:
        # Your validation logic
        self.passed = True  # or False
        self.message = "Gate results..."
        return self.passed
```

2. Add to `run_quality_gates()`:

```python
all_gates = {
    "unit-tests": UnitTestGate(verbose),
    "schema-validation": SchemaValidationGate(verbose),
    "backpressure": BackpressureGate(verbose),
    "new-gate": NewGate(verbose),  # Add here
}
```

3. Update CI workflow to include the new gate.

---

## Troubleshooting

### Gate Fails Locally But Not in CI

**Cause:** Different Python versions or dependencies.

**Solution:**
```bash
# Match CI environment (Python 3.11)
python --version  # Should be 3.11.x

# Reinstall dependencies
pip install -r requirements.txt --force-reinstall
```

### Schema Validation Fails

**Common Issues:**
- Missing timestamp fields (auto-added by validation)
- Wrong data types (string instead of int)
- Array length mismatch (movie_ids vs scores)

**Debug:**
```bash
# Run schema tests with verbose output
python scripts/quality_gate.py --gate schema-validation --verbose
```

### Backpressure Tests Timeout

**Cause:** Tests generate large amounts of data.

**Solution:**
- Reduce test data size in `tests/test_backpressure.py`
- Increase timeout in quality_gate.py (default: 180 seconds)

### All Tests Pass But Gate Fails

**Cause:** Parsing error in quality gate script.

**Solution:**
```bash
# Run pytest directly to see actual output
pytest tests/ -v

# Check for non-standard pytest output
pytest --version
```

---

## Best Practices

### 1. Run Gates Before Pushing

```bash
# Always run locally first
python scripts/quality_gate.py

# If passing, then push
git push origin your-branch
```

### 2. Fix Failures Immediately

Don't bypass gates unless it's an emergency. Fix the root cause:

```bash
# Identify failing tests
python scripts/quality_gate.py --verbose

# Fix the code
# ...

# Verify fix
python scripts/quality_gate.py
```

### 3. Keep Tests Fast

- Unit tests should run in < 30 seconds
- Schema validation in < 20 seconds
- Backpressure tests in < 60 seconds
- Total gate time: < 2 minutes

### 4. Monitor Gate Trends

Track metrics over time:
- Average test execution time
- Failure frequency by gate
- Most common failure reasons

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All gates passed ✅ |
| 1 | One or more gates failed ❌ |

**Usage in CI:**
```bash
if python scripts/quality_gate.py; then
    echo "Deploy to production"
else
    echo "Block deployment"
    exit 1
fi
```

---

## Metrics & Reporting

### Gate Success Rates

Track in your monitoring system:

```promql
# Gate pass rate over time
quality_gate_pass_rate{gate="unit-tests"} 
quality_gate_pass_rate{gate="schema-validation"}
quality_gate_pass_rate{gate="backpressure"}
```

### Test Execution Time

Monitor performance:

```bash
# Time each gate
time python scripts/quality_gate.py --gate unit-tests
time python scripts/quality_gate.py --gate schema-validation
time python scripts/quality_gate.py --gate backpressure
```

---

## Related Documentation

- **Testing Guide:** `README.md` (section: Testing)
- **Schema Documentation:** `recommender/schemas.py`
- **Backpressure Tests:** `tests/test_backpressure.py`
- **CI/CD Pipeline:** `.github/workflows/ci.yml`

---

## Summary

Quality gates ensure code quality through automated enforcement:

✅ **Unit Tests Gate** - All tests pass (100%)  
✅ **Schema Validation Gate** - All 4 Kafka schemas validated  
✅ **Backpressure Gate** - System handles load without data loss  

Run locally before every commit:
```bash
python scripts/quality_gate.py
```

Automatic enforcement in CI/CD prevents bad code from reaching production.

---

**Last Updated:** November 2, 2025
