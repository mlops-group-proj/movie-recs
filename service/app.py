from fastapi import FastAPI, HTTPException, Query
from recommender.factory import get_recommender
from prometheus_client import Counter, Histogram 
import os

app = FastAPI()

@app.get("/recommend/{user_id}")
def recommend(
    user_id: str,
    k: int = Query(20, ge=1, le=100),
    model: str = Query("popularity"),
):
    try:
        reco = get_recommender(model)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    items = reco.recommend(user_id=user_id, k=k, seen_items=[])
    return {"user_id": str(user_id), "model": model, "items": [str(x) for x in items]}
