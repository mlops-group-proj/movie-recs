from __future__ import annotations

import os
import sys
import math
import traceback
from dataclasses import dataclass
from config_loader import load_config

import numpy as np
import pandas as pd

from evaluation.evaluator import evaluate_topk
...
k = cfg.eval.top_k
metrics = evaluate_topk(
    model=model,
    test_df=test_df,
    user_col=cfg.data.user_col,
    item_col=cfg.data.item_col,
    k=k,
    train_df=train_df,            
    negatives_per_user=100,
)
print(f"HR@{k} = {metrics.hr:.4f} | NDCG@{k} = {metrics.ndcg:.4f} | users={metrics.users}")

try:
    from src.config_loader import load_config  # preferred in your tree
except Exception:  # fallback if older path/name
    from utils.config import load_config  # type: ignore

# --- Data loader: be tolerant to different function names --------------------
try:
    from src.data.loader import load_ratings_csv as _load_ratings  # type: ignore
except Exception:
    try:
        from src.data.loader import load_ratings as _load_ratings  # type: ignore
    except Exception:
        try:
            from src.data.loader import load_movielens as _load_ratings  # type: ignore
        except Exception:
            _load_ratings = None  # we will fallback to pandas.read_csv

def _load_ratings_df(path: str) -> pd.DataFrame:
    if _load_ratings is not None:
        return _load_ratings(path)
    return pd.read_csv(path)

# --- Splitter ----------------------------------------------------------------
from src.data.splitter import chronological_split  # exists in your tree

# --- Flexible ALS import + safe fallback -------------------------------------
ALSModel = None
try:
    # file als_model.py, class ALSModel
    from src.models.als_model import ALSModel  # type: ignore
except Exception:
    try:
        # file als.py, class ALSModel
        from src.models.als import ALSModel  # type: ignore
    except Exception:
        try:
            # file als_model.py, class ALS (alias)
            from src.models.als_model import ALS as ALSModel  # type: ignore
        except Exception:
            try:
                # file als.py, class ALS (alias)
                from src.models.als import ALS as ALSModel  # type: ignore
            except Exception:
                ALSModel = None

class _PopularityModel:
    """
    Fallback recommender if ALS isn't available yet.
    Recommends globally popular items the user hasn't seen.
    Must implement fit(...), recommend(user_id, k).
    """
    def fit(self, train_df: pd.DataFrame, user_col: str, item_col: str, rating_col: str):
        self.user_col = user_col
        self.item_col = item_col
        self.rating_col = rating_col
        self.seen = train_df.groupby(user_col)[item_col].apply(set).to_dict()
        self.pop = (
            train_df.groupby(item_col)[rating_col].count()
            .sort_values(ascending=False)
            .index.tolist()
        )

    def recommend(self, user_id: int | str, k: int = 10) -> list:
        seen_items = self.seen.get(user_id, set())
        recs = [i for i in self.pop if i not in seen_items]
        return recs[:k]

# --- Evaluator import + local fallback using metrics --------------------------
try:
    from src.evaluation.evaluator import evaluate_topk  # type: ignore
except Exception:
    # Minimal local evaluator using your metrics module
    try:
        from src.evaluation.metrics import hr_at_k, ndcg_at_k  # type: ignore
    except Exception:
        hr_at_k = ndcg_at_k = None  # type: ignore

    def evaluate_topk(  # type: ignore[override]
        model,
        test_df: pd.DataFrame,
        user_col: str,
        item_col: str,
        k: int = 10,
    ) -> dict:
        """
        Very small fallback: for each user in test, ask model.recommend(user, k),
        then compute HR@K and NDCG@K with the relevant ground-truth items.
        Assumes model has recommend(user_id, k) and test has at least one item/user.
        """
        users = test_df[user_col].unique().tolist()
        hits, ndcgs, used = 0, 0.0, 0
        for u in users:
            rel_items = set(test_df.loc[test_df[user_col] == u, item_col].tolist())
            if not rel_items:
                continue
            try:
                recs = model.recommend(u, k=k)
            except Exception:
                # If ALS expect different API, just skip this user
                continue
            used += 1
            if hr_at_k is not None and ndcg_at_k is not None:
                hits += hr_at_k(recs, rel_items)
                ndcgs += ndcg_at_k(recs, rel_items)
            else:
                # Very crude: 1 if any rel in recs else 0; ndcg=1 if hit
                hit = int(any(r in rel_items for r in recs))
                hits += hit
                ndcgs += float(hit)
        if used == 0:
            return {"users_scored": 0, f"hr@{k}": 0.0, f"ndcg@{k}": 0.0}
        return {
            "users_scored": used,
            f"hr@{k}": hits / used,
            f"ndcg@{k}": ndcgs / used,
        }

# --- Small helpers ------------------------------------------------------------
def _print_kv(title: str, kv: dict):
    print(title)
    widest = max((len(str(k)) for k in kv.keys()), default=0)
    for k, v in kv.items():
        print(f"  {str(k).ljust(widest)} : {v}")

# -----------------------------------------------------------------------------
def run_training(env: str | None = None) -> dict:
    if env:  
        os.environ["APP_ENV"] = env

    try:
        cfg = load_config()          
    except TypeError:
        try:
            cfg = load_config(None)  
        except TypeError:
            cfg = load_config()      

    ratings_path = getattr(cfg.data, "ratings_path", os.environ.get("RATINGS_PATH", "data/ratings.csv"))
    user_col = getattr(cfg.data, "user_col", "userId")
    item_col = getattr(cfg.data, "item_col", "movieId")
    rating_col = getattr(cfg.data, "rating_col", "rating")
    timestamp_col = getattr(cfg.data, "timestamp_col", "timestamp")
    k = getattr(cfg.eval, "top_k", 10)

    # Print brief header
    _print_kv("=== Training Pipeline ===", {
        "Environment" : getattr(cfg, "env", env or os.environ.get("APP_ENV", "dev")),
        "PYTHONPATH"  : os.environ.get("PYTHONPATH", ""),
        "RATINGS_PATH": ratings_path,
        "Model"       : getattr(cfg.train, "model_type", "als"),
        "Epochs"      : getattr(cfg.train, "epochs", getattr(cfg.train, "als_iters", 10)),
        "Log level"   : getattr(getattr(cfg, "logging", object()), "level", "INFO"),
    })

    # 2) Load data
    print(f"[train_pipeline] Reading ratings CSV: {ratings_path}", flush=True)
    df = _load_ratings_df(ratings_path)
    if df is None or len(df) == 0:
        print("[train_pipeline] ERROR: Loaded 0 rows from ratings. Check the path/file.", flush=True)
        return {}

    # 3) Chronological split (per-user)
    print("[train_pipeline] Splitting chronologically (per-user holdout ≈20%)", flush=True)
    train_df, test_df = chronological_split(
        df,
        user_col=user_col,
        timestamp_col=timestamp_col,
        holdout_ratio=0.20,
    )
    print(f"[train_pipeline] Train rows: {len(train_df):,} | Test rows: {len(test_df):,}", flush=True)

    # 4) Build model (ALS or fallback)
    model_type = str(getattr(cfg.train, "model_type", "als")).lower()
    if model_type == "als":
        if ALSModel is None:
            print("[train_pipeline] ALS not found; using popularity fallback for now.", flush=True)
            model = _PopularityModel()
        else:
            model = ALSModel(
                rank=getattr(cfg.train, "als_rank", 64),
                reg=getattr(cfg.train, "als_reg", 0.01),
                iters=getattr(cfg.train, "als_iters", 15),
            )
    else:
        raise NotImplementedError(f"Model '{model_type}' not implemented yet.")

    # 5) Fit
    print("[train_pipeline] Fitting model...", flush=True)
    model.fit(
        train_df=train_df,
        user_col=user_col,
        item_col=item_col,
        rating_col=rating_col,
    )
    print("[train_pipeline] Fit complete.", flush=True)

    # 6) Evaluate @K
    print(f"[train_pipeline] Evaluating HR@{k}, NDCG@{k} ...", flush=True)
    metrics = evaluate_topk(
        model=model,
        test_df=test_df,
        user_col=user_col,
        item_col=item_col,
        k=k,
    )
    # standardize keys for printing
    users_scored = metrics.get("users_scored", metrics.get("users", 0))
    hr_val = metrics.get(f"hr@{k}", metrics.get("hr", 0.0))
    ndcg_val = metrics.get(f"ndcg@{k}", metrics.get("ndcg", 0.0))
    print(f"[train_pipeline] METRICS: users={users_scored:,}, HR@{k}={hr_val:.6f}, NDCG@{k}={ndcg_val:.6f}", flush=True)

    return {
        "users_scored": users_scored,
        f"hr@{k}": float(hr_val),
        f"ndcg@{k}": float(ndcg_val),
    }

# -----------------------------------------------------------------------------
if __name__ == "__main__":
    try:
        run_training()
    except Exception as e:
        print("[train_pipeline] ERROR:", repr(e), flush=True)
        traceback.print_exc()
        sys.exit(1)

k = cfg.eval.top_k
metrics = evaluate_topk(
    model=model,
    test_df=test_df,
    user_col=cfg.data.user_col,
    item_col=cfg.data.item_col,
    k=k,
    train_df=train_df,   # so we can exclude seen items
)

log.info(f"Users evaluated : {metrics['users']}")
log.info(f"HR@{k}          : {metrics['hr']:.4f}")
log.info(f"NDCG@{k}        : {metrics['ndcg']:.4f}")

#return metrics
