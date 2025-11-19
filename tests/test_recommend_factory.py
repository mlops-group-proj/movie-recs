# tests/test_recommend_factory.py
import os
import pytest
from fastapi.testclient import TestClient
from recommender.factory import get_recommender
from service.app import app


@pytest.fixture(scope="session", autouse=True)
def setup_env():
    """Ensure model registry and version env vars exist."""
    os.environ.setdefault("MODEL_REGISTRY", "model_registry")
    os.environ.setdefault("MODEL_VERSION", "v0.3")
    os.environ.setdefault("MODEL_NAME", "als")


def test_factory_loads_model():
    """Factory should load ALS recommender without errors."""
    rec = get_recommender("als")
    assert rec is not None
    assert hasattr(rec, "recommend")
    assert rec.user_factors.shape[1] == rec.item_factors.shape[1]


def test_recommendations_returned():
    """Recommender should return a non-empty list of movie IDs for a valid user."""
    rec = get_recommender("als")
    # pick a known user ID from your training set (1 works for MovieLens 1M)
    items = rec.recommend(1, k=5)
    assert isinstance(items, list)
    assert len(items) > 0
    assert all(isinstance(i, int) for i in items)


def test_fastapi_endpoint(monkeypatch):
    """FastAPI /recommend/{user_id} returns valid JSON with expected structure."""
    client = TestClient(app)

    # hit the health endpoint first
    res_health = client.get("/healthz")
    assert res_health.status_code == 200
    assert "status" in res_health.json()

    # mock latency histogram to skip Prometheus time decorator overhead
    res = client.get("/recommend/1?k=3")
    assert res.status_code == 200
    data = res.json()
    assert "user_id" in data
    assert "items" in data
    assert isinstance(data["items"], list)
    assert len(data["items"]) == 3


def test_switch_endpoint():
    client = TestClient(app)
    res = client.get("/switch", params={"model": os.environ.get("MODEL_VERSION", "v0.3")})
    assert res.status_code == 200
    payload = res.json()
    assert payload["status"] == "ok"
    assert payload["model_version"] == os.environ.get("MODEL_VERSION", "v0.3")
