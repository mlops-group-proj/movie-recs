from __future__ import annotations
import pandas as pd

def load_ratings_csv(
    path: str,
    user_col: str | None = None,
    item_col: str | None = None,
    rating_col: str | None = None,
    timestamp_col: str | None = None,
):
    """
    Compatibility wrapper used by train_pipeline.
    If your repository already has a loader like `load_ratings` or `load_movielens`,
    feel free to delegate to it. Otherwise we read the CSV directly.
    """
    try:
        if "load_ratings" in globals():
            return globals()["load_ratings"](path)
        if "load_movielens" in globals():
            return globals()["load_movielens"](path)
    except Exception:
        pass

    df = pd.read_csv(path)
    return df
