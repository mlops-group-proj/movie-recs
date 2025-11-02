# service/app.py
from fastapi import FastAPI, HTTPException
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
import os
from recommender.factory import get_recommender

app = FastAPI(title="Movie Recommender API")

# Prometheus metrics
REQS = Counter("recommend_requests_total", "Requests", ["status"])
LAT = Histogram("recommend_latency_seconds", "Latency")

# Load model once at startup
MODEL_NAME = os.getenv("MODEL_NAME", "als")
MODEL_VERSION = os.getenv("MODEL_VERSION", "v0.2")
recommender = get_recommender(MODEL_NAME)


@app.get("/healthz")
def healthz():
    """Health check endpoint."""
    return {"status": "ok", "version": MODEL_VERSION}


@app.get("/recommend/{user_id}")
@LAT.time()
def recommend(user_id: int, k: int = 20, model: str | None = None):
    """Return top-K recommendations for a user."""
    try:
        model_to_use = model or MODEL_NAME
        if model_to_use != MODEL_NAME:
            raise HTTPException(status_code=400, detail="Only ALS model supported")
        items = recommender.recommend(user_id, k)
        REQS.labels("200").inc()
        return {"user_id": user_id, "model": model_to_use, "items": items}
    except Exception as e:
        REQS.labels("500").inc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/metrics")
def metrics():
    """Prometheus-compatible metrics."""
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}
