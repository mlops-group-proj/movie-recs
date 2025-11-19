# Rollout Features Changelog

## Summary
This update implements comprehensive automated retraining, hot-swap model deployment, and environment-based rollout strategies for the Movie Recommender System.

**Branch**: `116-create-croncloud-scheduleraction-to-retrain-push-model_registryvxy-artifacts-and-expose-a-hot-swap-endpointenv-based-rollout`

**Date**: 2025-11-19

---

## New Features

### 1. Enhanced Automated Retraining
- **Automated commits**: Retraining workflow now commits model registry updates to the repository
- **Permissions**: Updated workflow permissions from `read` to `write` for git operations
- **Provenance**: Full tracking of git SHA, data snapshot, and build artifacts

**Files Modified:**
- [.github/workflows/retrain.yml](.github/workflows/retrain.yml)

### 2. Prometheus Metrics for Model Versions
- **`model_version_info`**: Gauge tracking current model version with labels for git SHA and data snapshot
- **`model_switches_total`**: Counter tracking hot-swap operations with success/failure status
- **Integration**: Metrics automatically updated on startup and during model switches

**Files Modified:**
- [service/app.py](service/app.py)

### 3. Environment-Based Rollout Strategies
Implemented flexible deployment strategies for gradual rollouts and A/B testing:

#### Supported Strategies:
- **`fixed`**: All traffic to single version (default)
- **`canary`**: Gradual rollout with percentage-based routing (deterministic by user_id)
- **`ab_test`**: 50/50 split based on user_id parity
- **`shadow`**: Shadow mode for parallel testing without affecting production

#### Configuration:
- Environment variables: `ROLLOUT_STRATEGY`, `CANARY_VERSION`, `CANARY_PERCENTAGE`, `ENVIRONMENT`
- Runtime updates via REST API
- Docker Compose integration

**Files Created:**
- [service/rollout.py](service/rollout.py) - Rollout strategy implementation

**Files Modified:**
- [service/app.py](service/app.py) - Integration with FastAPI
- [docker-compose.yml](docker-compose.yml) - Environment variable support

### 4. New API Endpoints

#### `POST /rollout/update`
Dynamically update rollout configuration without restarting.

**Examples:**
```bash
# Start canary: 10% to v0.4
curl -X POST "http://localhost:8080/rollout/update?strategy=canary&canary_version=v0.4&canary_percentage=10"

# Increase to 25%
curl -X POST "http://localhost:8080/rollout/update?canary_percentage=25"

# A/B test
curl -X POST "http://localhost:8080/rollout/update?strategy=ab_test&canary_version=v0.4"
```

#### `GET /rollout/status`
Get current rollout configuration and active version.

```bash
curl http://localhost:8080/rollout/status
```

#### Enhanced `/healthz`
Now includes rollout configuration in health check response.

#### Enhanced `/switch`
Improved with Prometheus metrics tracking and better error handling.

### 5. Documentation

**New Documents:**
- [docs/ROLLOUT_GUIDE.md](docs/ROLLOUT_GUIDE.md) - Comprehensive rollout guide (70+ sections)
  - Automated retraining workflows
  - Model registry versioning
  - Hot-swap deployment
  - Rollout strategies with examples
  - Prometheus metrics
  - Troubleshooting guide

- [docs/API_REFERENCE.md](docs/API_REFERENCE.md) - Complete API reference
  - All endpoints with examples
  - Rollout strategy details
  - Environment variable reference
  - Monitoring & metrics
  - Workflow examples

- [.env.example](.env.example) - Environment configuration template
  - Model configuration
  - Rollout strategy settings
  - Kafka & S3 configuration

**Updated Documents:**
- [README.md](README.md) - Added rollout features summary with link to full guide

### 6. Testing & Validation

**New Test Script:**
- [scripts/test_rollout.sh](scripts/test_rollout.sh) - Automated test suite
  - Health checks
  - Model switching tests
  - Rollout configuration tests
  - Prometheus metrics validation

---

## Technical Details

### Model Version Tracking
```python
MODEL_VERSION_INFO.labels(
    model_name="als",
    version="v0.3",
    git_sha="207521e0",
    data_snapshot="9c1de442"
).set(1)
```

### Rollout Logic (Canary)
```python
# Deterministic routing based on user_id
if (user_id % 100) < canary_percentage:
    use canary_version
else:
    use primary_version
```

### Environment Variables
```bash
# Rollout Configuration
ROLLOUT_STRATEGY=canary         # fixed, canary, ab_test, shadow
MODEL_VERSION=v0.3              # Primary version
CANARY_VERSION=v0.4             # Test version
CANARY_PERCENTAGE=10            # 0-100
ENVIRONMENT=production          # Environment label
```

---

## File Summary

### Created (5 files):
1. `service/rollout.py` - Rollout strategy implementation
2. `docs/ROLLOUT_GUIDE.md` - Comprehensive deployment guide
3. `docs/API_REFERENCE.md` - Complete API documentation
4. `.env.example` - Environment configuration template
5. `scripts/test_rollout.sh` - Automated test suite

### Modified (4 files):
1. `.github/workflows/retrain.yml` - Auto-commit model registry
2. `service/app.py` - Rollout integration + Prometheus metrics
3. `docker-compose.yml` - Environment variable support
4. `README.md` - Feature summary and documentation links

---

## Deployment Checklist

### Before Deploying:
- [ ] Review `.env.example` and set appropriate values
- [ ] Verify model registry has at least 2 versions for testing
- [ ] Check GitHub Actions permissions for auto-commits
- [ ] Configure Grafana dashboard for new metrics

### Testing:
```bash
# 1. Start services
docker compose up --build

# 2. Run test suite
./scripts/test_rollout.sh

# 3. Manual verification
curl http://localhost:8080/healthz
curl http://localhost:8080/rollout/status
curl http://localhost:8080/metrics | grep model_version
```

### Monitoring:
- [ ] Verify `model_version_info` metric in Prometheus
- [ ] Check `model_switches_total` counter
- [ ] Monitor rollout status in Grafana
- [ ] Set up alerts for failed switches

---

## Migration Notes

### For Existing Deployments:

1. **Update Environment Variables**:
   ```bash
   # Add to .env
   ROLLOUT_STRATEGY=fixed
   CANARY_VERSION=
   CANARY_PERCENTAGE=0
   ENVIRONMENT=production
   ```

2. **Update Docker Compose**:
   - Pull latest `docker-compose.yml`
   - Rebuild containers: `docker compose up --build`

3. **Verify Compatibility**:
   - Old deployments default to `fixed` strategy (no behavior change)
   - Hot-swap endpoint `/switch` works as before
   - New endpoints are additive (backward compatible)

### Breaking Changes:
**None** - All changes are backward compatible.

---

## Performance Impact

- **Memory**: +~100KB for rollout module
- **Latency**: <1ms overhead for rollout routing logic
- **CPU**: Negligible (single modulo operation per request)
- **Storage**: Model registry grows with each retrain (auto-cleanup recommended)

---

## Future Enhancements

Potential improvements for future milestones:

1. **Auto-rollback**: Automatic rollback on error rate spike
2. **Traffic splitting**: More granular percentage control (e.g., 5%, 15%, 33%)
3. **Multi-region rollout**: Staged rollout across AWS regions
4. **Model comparison dashboard**: Side-by-side metrics for A/B tests
5. **Rollout history**: Track all rollout events in database
6. **Integration tests**: Automated E2E tests in CI/CD

---

## References

- [Milestone 4 Requirements](https://github.com/mlops-group-proj/movie-recs/issues/116)
- [Original Retraining Workflow](.github/workflows/retrain.yml)
- [Model Registry Structure](docs/ROLLOUT_GUIDE.md#model-registry-versioning)
- [Prometheus Best Practices](https://prometheus.io/docs/practices/)

---

## Contributors

- Implementation: Claude Code (Anthropic)
- Testing: Team MedicalAI
- Review: TBD

---

## Approval & Sign-off

- [ ] Code review completed
- [ ] Documentation reviewed
- [ ] Tests passing
- [ ] Deployed to staging
- [ ] Ready for production

**Merge Checklist:**
- [ ] Squash commits or keep history?
- [ ] Update main branch protection rules?
- [ ] Trigger production deployment?
