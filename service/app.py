# service/app.py
from fastapi import FastAPI, HTTPException, Response
from prometheus_client import (
    Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST, REGISTRY
)
import os
import logging

from recommender import drift
from service.loader import ModelManager, ModelRegistryError

app = FastAPI(title="Movie Recommender API")
logging.basicConfig(level=logging.INFO)

# ------------------------------------------------------------------
# Prometheus base metrics
# ------------------------------------------------------------------
REQS = Counter("recommend_requests_total", "Requests", ["status"])
LAT = Histogram("recommend_latency_seconds", "Latency")

MODEL_NAME = os.getenv("MODEL_NAME", "als")
MODEL_VERSION = os.getenv("MODEL_VERSION", "v0.3")
MODEL_REGISTRY = os.getenv("MODEL_REGISTRY", "model_registry")
model_manager = ModelManager(MODEL_NAME, MODEL_VERSION, MODEL_REGISTRY)
app.state.model_manager = model_manager

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

# ------------------------------------------------------------------
# API Endpoints
# ------------------------------------------------------------------
@app.get("/healthz")
def healthz():
    return {
        "status": "ok",
        "version": app.state.model_manager.current_version,
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
    try:
        info = app.state.model_manager.switch(model)
        return {"status": "ok", **info}
    except ModelRegistryError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logging.exception("Model switch failed")
        raise HTTPException(status_code=500, detail=str(exc))
