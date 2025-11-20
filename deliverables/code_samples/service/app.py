# service/app.py
from fastapi import FastAPI, HTTPException, Response, Request
from prometheus_client import (
    Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST, REGISTRY
)
import os
import logging

from recommender import drift
from service.loader import ModelManager, ModelRegistryError
from service.rollout import RolloutConfig
from service.middleware import RequestIDMiddleware, get_request_id, store_trace, get_trace

app = FastAPI(title="Movie Recommender API")
logging.basicConfig(level=logging.INFO)

# Add request ID middleware
app.add_middleware(RequestIDMiddleware)

# ------------------------------------------------------------------
# Prometheus SLO metrics
# ------------------------------------------------------------------
# Request counters by status code
REQS = Counter("recommend_requests_total", "Total recommendation requests", ["status", "endpoint"])

# Latency histogram with SLO-friendly buckets (in seconds)
# Buckets: 10ms, 25ms, 50ms, 100ms, 250ms, 500ms, 1s, 2.5s, 5s, 10s
LAT = Histogram(
    "recommend_latency_seconds",
    "Request latency in seconds",
    ["endpoint"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
)

# Error rate metrics
ERRORS = Counter("recommend_errors_total", "Total errors by type", ["error_type", "endpoint"])

# Service uptime and health
UPTIME = Gauge("service_uptime_seconds", "Service uptime in seconds")
HEALTH_STATUS = Gauge("service_health_status", "Service health status (1=healthy, 0=unhealthy)")

# Model-specific metrics
MODEL_VERSION_INFO = Gauge("model_version_info", "Current model version", ["model_name", "version", "git_sha", "data_snapshot"])
MODEL_SWITCHES = Counter("model_switches_total", "Model hot-swap operations", ["from_version", "to_version", "status"])
MODEL_LOAD_TIME = Histogram("model_load_seconds", "Model loading time", buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0))

# A/B testing metrics
AB_REQUESTS = Counter("ab_test_requests_total", "A/B test requests by variant", ["variant", "status"])
AB_LATENCY = Histogram("ab_test_latency_seconds", "A/B test latency by variant", ["variant"], buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0))

# SLO indicators
SLO_LATENCY_TARGET = Gauge("slo_latency_target_seconds", "SLO latency target in seconds")
SLO_AVAILABILITY_TARGET = Gauge("slo_availability_target_ratio", "SLO availability target (0-1)")
SLO_ERROR_BUDGET = Gauge("slo_error_budget_remaining_ratio", "SLO error budget remaining (0-1)")

# Set SLO targets
SLO_LATENCY_TARGET.set(0.1)  # 100ms p95 target
SLO_AVAILABILITY_TARGET.set(0.999)  # 99.9% availability target

MODEL_NAME = os.getenv("MODEL_NAME", "als")
MODEL_VERSION = os.getenv("MODEL_VERSION", "v0.3")
MODEL_REGISTRY = os.getenv("MODEL_REGISTRY", "model_registry")
model_manager = ModelManager(MODEL_NAME, MODEL_VERSION, MODEL_REGISTRY)
app.state.model_manager = model_manager

# Load rollout configuration
rollout_config = RolloutConfig.from_env()
app.state.rollout_config = rollout_config
logging.info(f"🚀 Rollout strategy: {rollout_config.to_dict()}")

# ------------------------------------------------------------------
# Drift metrics setup (register once)
# ------------------------------------------------------------------
def _get_or_create(name: str, desc: str) -> Gauge:
    if name not in REGISTRY._names_to_collectors:
        return Gauge(name, desc, ["feature"], registry=REGISTRY)
    return REGISTRY._names_to_collectors[name]

PSI_G  = _get_or_create("data_drift_psi", "Population Stability Index")
KL_G   = _get_or_create("data_drift_kl", "Kullback-Leibler Divergence")
MISS_G = _get_or_create("data_missing_ratio", "Fraction of missing values")
OUTL_G = _get_or_create("data_outlier_fraction", "Fraction of outliers (z>3)")

# Cache drift results
app.state.drift_results = None

import time

# Track service start time
SERVICE_START_TIME = time.time()

@app.on_event("startup")
def compute_drift_once():
    """Compute drift once at startup."""
    # Mark service as healthy
    HEALTH_STATUS.set(1)

    logging.info("📊 Running drift check on startup...")
    try:
        results, _, _ = drift.run_drift(threshold=0.25)
        app.state.drift_results = results
        for feature, vals in results["drift_metrics"].items():
            PSI_G.labels(feature=feature).set(vals.get("psi", 0.0))
            KL_G.labels(feature=feature).set(vals.get("kl_divergence", 0.0))
            MISS_G.labels(feature=feature).set(vals.get("missing_ratio", 0.0))
            OUTL_G.labels(feature=feature).set(vals.get("outlier_fraction", 0.0))
        logging.info("✅ Drift metrics loaded successfully.")
    except Exception as e:
        logging.exception(f"⚠️ Drift computation failed: {e}")

    # Export model version info to Prometheus
    try:
        meta = model_manager.describe_active().get("meta", {})
        version_meta = meta.get("version", {})
        git_sha = version_meta.get("git_sha", "unknown")[:8]
        data_snapshot = version_meta.get("data_snapshot_id", "unknown")[:8]
        MODEL_VERSION_INFO.labels(
            model_name=MODEL_NAME,
            version=MODEL_VERSION,
            git_sha=git_sha,
            data_snapshot=data_snapshot
        ).set(1)
        logging.info(f"✅ Model version info exported: {MODEL_VERSION} (git:{git_sha}, data:{data_snapshot})")
    except Exception as e:
        logging.warning(f"⚠️ Failed to export model version info: {e}")

# ------------------------------------------------------------------
# API Endpoints
# ------------------------------------------------------------------
@app.get("/healthz")
def healthz():
    rollout = app.state.rollout_config.to_dict()
    return {
        "status": "ok",
        "version": app.state.model_manager.current_version,
        "rollout": rollout,
    }


@app.get("/recommend/{user_id}")
def recommend(user_id: int, k: int = 20, model: str | None = None, request: Request = None):
    """Return top-K recommendations for a user with A/B routing support."""
    start_time = time.time()
    endpoint = "recommend"

    try:
        # Get request ID from middleware
        request_id = get_request_id() or "unknown"

        # Select version based on rollout strategy (e.g., A/B test)
        selected_version = app.state.rollout_config.select_version(user_id)

        # Use explicitly provided model or rollout-selected version
        model_to_use = model or selected_version

        # Track which variant is being used for A/B testing
        from service.rollout import RolloutStrategy
        variant = None
        if app.state.rollout_config.strategy == RolloutStrategy.AB_TEST:
            # Variant A = even user_ids, Variant B = odd user_ids
            variant = "variant_A" if (user_id % 2 == 0) else "variant_B"

        # Switch to selected version if needed
        if model_to_use != app.state.model_manager.current_version:
            try:
                app.state.model_manager.switch(model_to_use)
            except Exception as e:
                logging.warning(f"Failed to switch to {model_to_use}: {e}")

        # Generate recommendations
        items = app.state.model_manager.recommend(user_id, k)

        # Record success metrics
        latency = time.time() - start_time
        LAT.labels(endpoint=endpoint).observe(latency)
        REQS.labels(status="200", endpoint=endpoint).inc()

        # Record A/B test metrics if in A/B mode
        if variant:
            AB_REQUESTS.labels(variant=variant, status="200").inc()
            AB_LATENCY.labels(variant=variant).observe(latency)

        # Get provenance metadata
        meta = app.state.model_manager.describe_active().get("meta", {})
        version_meta = meta.get("version", {})

        # Build provenance fields
        provenance = {
            "request_id": request_id,
            "timestamp": int(start_time * 1000),  # milliseconds since epoch
            "model_name": MODEL_NAME,
            "model_version": model_to_use,
            "git_sha": version_meta.get("git_sha", "unknown"),
            "data_snapshot_id": version_meta.get("data_snapshot_id", "unknown"),
            "container_image_digest": version_meta.get("image_digest", None),
            "latency_ms": int(latency * 1000)
        }

        # Structured logging with provenance context
        logging.info(
            f"[{request_id}] Recommendation success for user {user_id}",
            extra={
                **provenance,
                "user_id": user_id,
                "k": k,
                "num_items": len(items),
                "status": 200,
                "variant": variant
            }
        )

        # Store trace for retrieval via /trace endpoint
        store_trace(request_id, {
            **provenance,
            "user_id": user_id,
            "k": k,
            "num_items": len(items),
            "status": 200,
            "variant": variant,
            "path": "/recommend/{user_id}",
            "method": "GET"
        })

        return {
            "user_id": user_id,
            "model": model_to_use,
            "items": items,
            "variant": variant,  # Include variant for transparency
            # Provenance fields
            "provenance": provenance
        }

    except HTTPException:
        raise
    except Exception as e:
        # Record error metrics
        latency = time.time() - start_time
        LAT.labels(endpoint=endpoint).observe(latency)
        REQS.labels(status="500", endpoint=endpoint).inc()
        ERRORS.labels(error_type="internal_error", endpoint=endpoint).inc()

        # Record A/B test error metrics if applicable
        if variant:
            AB_REQUESTS.labels(variant=variant, status="500").inc()
            AB_LATENCY.labels(variant=variant).observe(latency)

        # Structured error logging with provenance context
        request_id = get_request_id() or "unknown"
        meta = app.state.model_manager.describe_active().get("meta", {})
        version_meta = meta.get("version", {})

        logging.exception(
            f"[{request_id}] Recommendation error for user {user_id}",
            extra={
                "request_id": request_id,
                "user_id": user_id,
                "model_version": app.state.model_manager.current_version,
                "git_sha": version_meta.get("git_sha", "unknown"),
                "data_snapshot_id": version_meta.get("data_snapshot_id", "unknown"),
                "status": 500,
                "latency_ms": int(latency * 1000),
                "error_type": type(e).__name__,
                "variant": variant
            }
        )
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/trace/{request_id}")
def trace(request_id: str):
    """Retrieve provenance trace for a specific request.

    Args:
        request_id: The unique request identifier (from X-Request-ID header or response)

    Returns:
        Complete provenance trace including all metadata for the request

    Example:
        curl http://localhost:8080/trace/123e4567-e89b-12d3-a456-426614174000
    """
    trace_data = get_trace(request_id)

    if not trace_data:
        raise HTTPException(
            status_code=404,
            detail=f"Trace not found for request_id={request_id}. "
                   "Traces are kept for the last 1000 requests only."
        )

    return {
        "request_id": request_id,
        "trace": trace_data
    }


@app.get("/metrics")
def metrics():
    """Prometheus metrics endpoint."""
    try:
        # Update uptime metric
        uptime = time.time() - SERVICE_START_TIME
        UPTIME.set(uptime)

        # Drift already preloaded at startup — no recomputation
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
    except Exception as e:
        logging.warning(f"Metrics endpoint error: {e}")
        return Response(status_code=500, content=f"# metrics_error {e}")


@app.get("/switch")
def switch(model: str):
    """Hot-swap the active recommender version (e.g. /switch?model=v0.3)."""
    if not model:
        raise HTTPException(status_code=400, detail="Model query parameter required")

    previous_version = app.state.model_manager.current_version
    try:
        info = app.state.model_manager.switch(model)

        # Update Prometheus metrics
        MODEL_SWITCHES.labels(from_version=previous_version, to_version=model, status="success").inc()

        # Update version info gauge
        meta = app.state.model_manager.describe_active().get("meta", {})
        version_meta = meta.get("version", {})
        git_sha = version_meta.get("git_sha", "unknown")[:8]
        data_snapshot = version_meta.get("data_snapshot_id", "unknown")[:8]
        MODEL_VERSION_INFO.labels(
            model_name=MODEL_NAME,
            version=model,
            git_sha=git_sha,
            data_snapshot=data_snapshot
        ).set(1)

        logging.info(f"🔄 Model switched: {previous_version} → {model}")
        return {"status": "ok", **info}
    except (ModelRegistryError, FileNotFoundError) as exc:
        MODEL_SWITCHES.labels(from_version=previous_version, to_version=model, status="not_found").inc()
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        MODEL_SWITCHES.labels(from_version=previous_version, to_version=model, status="error").inc()
        logging.exception("Model switch failed")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/rollout/update")
def update_rollout(
    strategy: str = "fixed",
    canary_version: str | None = None,
    canary_percentage: float = 0.0
):
    """Update rollout configuration dynamically.

    Examples:
    - Canary: /rollout/update?strategy=canary&canary_version=v0.4&canary_percentage=10
    - A/B Test: /rollout/update?strategy=ab_test&canary_version=v0.4
    - Fixed: /rollout/update?strategy=fixed
    """
    from service.rollout import RolloutStrategy

    try:
        new_strategy = RolloutStrategy(strategy)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid strategy. Must be one of: {', '.join([s.value for s in RolloutStrategy])}"
        )

    app.state.rollout_config.strategy = new_strategy
    if canary_version:
        app.state.rollout_config.canary_version = canary_version
    if canary_percentage > 0:
        app.state.rollout_config.canary_percentage = canary_percentage

    logging.info(f"🔧 Rollout config updated: {app.state.rollout_config.to_dict()}")
    return {
        "status": "ok",
        "rollout": app.state.rollout_config.to_dict()
    }


@app.get("/rollout/status")
def rollout_status():
    """Get current rollout configuration and statistics."""
    return {
        "rollout": app.state.rollout_config.to_dict(),
        "active_version": app.state.model_manager.current_version,
    }


@app.get("/experiment/analyze")
def analyze_experiment(time_window_minutes: int = 60):
    """Analyze A/B test results with statistical testing.

    Queries Prometheus for A/B test metrics and runs statistical analysis.

    Args:
        time_window_minutes: Time window to analyze (default: 60 minutes)

    Returns:
        JSON with experiment analysis, statistical tests, and recommendation
    """
    from service.rollout import RolloutStrategy
    import requests
    from service.ab_analysis import analyze_experiment as run_analysis

    # Check if we're in A/B test mode
    if app.state.rollout_config.strategy != RolloutStrategy.AB_TEST:
        raise HTTPException(
            status_code=400,
            detail=f"Not in A/B test mode. Current strategy: {app.state.rollout_config.strategy.value}"
        )

    # Query Prometheus for A/B test metrics
    prom_url = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
    time_range = f"{time_window_minutes}m"

    try:
        # Get request counts per variant
        query_requests_a = f'sum(increase(ab_test_requests_total{{variant="variant_A"}}[{time_range}]))'
        query_requests_b = f'sum(increase(ab_test_requests_total{{variant="variant_B"}}[{time_range}]))'

        # Get success counts (status="200")
        query_success_a = f'sum(increase(ab_test_requests_total{{variant="variant_A",status="200"}}[{time_range}]))'
        query_success_b = f'sum(increase(ab_test_requests_total{{variant="variant_B",status="200"}}[{time_range}]))'

        # Get latency percentiles
        query_latency_p95_a = f'histogram_quantile(0.95, sum(rate(ab_test_latency_seconds_bucket{{variant="variant_A"}}[{time_range}])) by (le))'
        query_latency_p95_b = f'histogram_quantile(0.95, sum(rate(ab_test_latency_seconds_bucket{{variant="variant_B"}}[{time_range}])) by (le))'

        def query_prom(query: str) -> float:
            """Query Prometheus and return scalar result."""
            resp = requests.get(f"{prom_url}/api/v1/query", params={"query": query}, timeout=5)
            resp.raise_for_status()
            data = resp.json()
            result = data.get("data", {}).get("result", [])
            if not result:
                return 0.0
            return float(result[0]["value"][1])

        # Fetch metrics
        requests_a = int(query_prom(query_requests_a))
        requests_b = int(query_prom(query_requests_b))
        success_a = int(query_prom(query_success_a))
        success_b = int(query_prom(query_success_b))
        latency_p95_a = query_prom(query_latency_p95_a)
        latency_p95_b = query_prom(query_latency_p95_b)

    except Exception as e:
        logging.error(f"Failed to query Prometheus: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch metrics from Prometheus: {e}")

    # Check if we have enough data
    if requests_a == 0 or requests_b == 0:
        return {
            "status": "insufficient_data",
            "message": f"No A/B test data found in the last {time_window_minutes} minutes. Generate traffic first.",
            "metrics": {
                "variant_A": {"requests": requests_a, "successes": success_a},
                "variant_B": {"requests": requests_b, "successes": success_b}
            }
        }

    # Run statistical analysis on success rate
    analysis = run_analysis(
        variant_a_successes=success_a,
        variant_a_trials=requests_a,
        variant_b_successes=success_b,
        variant_b_trials=requests_b,
        metric_name="success_rate"
    )

    # Add latency comparison
    latency_delta = latency_p95_b - latency_p95_a
    latency_pct_change = (latency_delta / latency_p95_a * 100) if latency_p95_a > 0 else 0

    return {
        "experiment": {
            "strategy": "ab_test",
            "time_window_minutes": time_window_minutes,
            "variant_A": app.state.rollout_config.primary_version,
            "variant_B": app.state.rollout_config.canary_version,
        },
        "metrics": {
            "variant_A": {
                "requests": requests_a,
                "successes": success_a,
                "success_rate": success_a / requests_a if requests_a > 0 else 0,
                "latency_p95_ms": latency_p95_a * 1000
            },
            "variant_B": {
                "requests": requests_b,
                "successes": success_b,
                "success_rate": success_b / requests_b if requests_b > 0 else 0,
                "latency_p95_ms": latency_p95_b * 1000
            }
        },
        "statistical_analysis": analysis,
        "latency_comparison": {
            "variant_A_p95_ms": latency_p95_a * 1000,
            "variant_B_p95_ms": latency_p95_b * 1000,
            "delta_ms": latency_delta * 1000,
            "percent_change": latency_pct_change
        }
    }
