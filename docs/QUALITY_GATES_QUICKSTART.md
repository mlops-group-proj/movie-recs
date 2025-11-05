# Quality Gates Quick Guide

## Setup

Your project now has automated quality gates that enforce:
1. ✅ **Unit Tests** - All tests must pass
2. ✅ **Schema Validation** - Kafka schemas must be valid
3. ✅ **Backpressure Handling** - System handles load correctly

## Running Quality Gates

### All Gates
```bash
python scripts/quality_gate.py
```

### Individual Gates
```bash
# Unit tests only
python scripts/quality_gate.py --gate unit-tests

# Schema validation only
python scripts/quality_gate.py --gate schema-validation

# Backpressure handling only
python scripts/quality_gate.py --gate backpressure
```

### With Verbose Output
```bash
python scripts/quality_gate.py --verbose
python scripts/quality_gate.py --gate unit-tests --verbose
```

## Important: Test Environment Setup

**Before running quality gates, disable S3 for tests:**

```bash
# Option 1: Temporarily rename .env
mv .env .env.backup

# Option 2: Set USE_S3=false in .env
# Edit .env and change:
USE_S3=false

# Run quality gates
python scripts/quality_gate.py

# Restore .env
mv .env.backup .env  # if you renamed it
```

**Why?** Tests expect local file system writes, but your `.env` has `USE_S3=true` which writes to S3 instead.

## Quick Fix for Current Test Failures

```bash
# 1. Disable S3 temporarily
export USE_S3=false  # Linux/Mac
set USE_S3=false     # Windows CMD
$env:USE_S3="false"  # Windows PowerShell

# 2. Run quality gates
python scripts/quality_gate.py

# 3. Re-enable S3 for production
unset USE_S3  # Linux/Mac - will use .env value
```

## CI/CD Integration

Quality gates run automatically in GitHub Actions:
- On every pull request
- On pushes to `main` and `Arvin` branches
- All gates must pass before merge

View results: GitHub → Actions → CI Pipeline

## Local Pre-Commit Hook (Optional)

Run quality gates before every commit:

```bash
# Install hook
cp scripts/pre-commit-hook.sh .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit

# Now gates run on every commit
git commit -m "Your message"
# 🔍 Running pre-commit quality gates...
```

## What Each Gate Checks

### 1. Unit Tests Gate
- All tests in `tests/` directory pass
- Zero failures allowed
- 100% pass rate required

### 2. Schema Validation Gate
- All 4 Kafka schemas validated: watch, rate, reco_requests, reco_responses
- Message validation logic works correctly
- Invalid messages properly rejected

### 3. Backpressure Gate
- Batch size triggers automatic flush (1000 messages)
- Time-based flush works (every 5 minutes)
- Multiple topics handled independently
- Zero data loss under load
- Minimum 5 test cases pass

## Exit Codes

- `0` = All gates passed ✅
- `1` = One or more gates failed ❌

## Full Documentation

See `docs/QUALITY_GATES.md` for complete documentation including:
- Detailed threshold configuration
- Troubleshooting guide
- How to add new gates
- Best practices

## Common Issues

**Issue:** Tests write to S3 but expect local files
**Solution:** Set `USE_S3=false` before running tests

**Issue:** Tests timeout
**Solution:** Run individual gates or increase timeout in `quality_gate.py`

**Issue:** Gate script not found
**Solution:** Make sure you're in the project root directory

## Examples

```bash
# Check all gates (production-ready check)
python scripts/quality_gate.py
# ✓ All quality gates passed

# Check just schemas before committing schema changes
python scripts/quality_gate.py --gate schema-validation
# ✓ Schema Validation Gate passed

# Debug failing backpressure tests
python scripts/quality_gate.py --gate backpressure --verbose
# Shows detailed test output
```

## Next Steps

1. ✅ Fix test environment (set USE_S3=false for tests)
2. ✅ Run `python scripts/quality_gate.py` to verify all gates pass
3. ✅ Install pre-commit hook (optional but recommended)
4. ✅ Commit and push - CI will automatically run gates

---

**Created:** November 2, 2025
