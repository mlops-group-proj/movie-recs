# service/app.py
from fastapi import FastAPI, HTTPException, Response
from prometheus_client import (
    Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST, REGISTRY
)
import os
import logging

from recommender import drift
from service.loader import ModelManager, ModelRegistryError
from service.rollout import RolloutConfig

app = FastAPI(title="Movie Recommender API")
logging.basicConfig(level=logging.INFO)

# ------------------------------------------------------------------
# Prometheus base metrics
# ------------------------------------------------------------------
REQS = Counter("recommend_requests_total", "Requests", ["status"])
LAT = Histogram("recommend_latency_seconds", "Latency")
MODEL_VERSION_INFO = Gauge("model_version_info", "Current model version", ["model_name", "version", "git_sha", "data_snapshot"])
MODEL_SWITCHES = Counter("model_switches_total", "Model hot-swap operations", ["from_version", "to_version", "status"])

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

@app.on_event("startup")
def compute_drift_once():
    """Compute drift once at startup."""
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
@LAT.time()
def recommend(user_id: int, k: int = 20, model: str | None = None):
    """Return top-K recommendations for a user."""
    try:
        model_to_use = model or MODEL_NAME
        if model_to_use != MODEL_NAME:
            raise HTTPException(status_code=400, detail="Only ALS model supported")
        items = app.state.model_manager.recommend(user_id, k)
        REQS.labels("200").inc()
        return {"user_id": user_id, "model": model_to_use, "items": items}
    except Exception as e:
        REQS.labels("500").inc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/metrics")
def metrics():
    """Prometheus metrics endpoint."""
    try:
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
