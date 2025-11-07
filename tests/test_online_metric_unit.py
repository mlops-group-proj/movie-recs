import pandas as pd
from scripts.online_metric import compute_success, proportion_ci

def test_compute_success_basic():
    df_reco = pd.DataFrame([{
        "user_id": 1,
        "model": "m1",
        "movie_ids": [42],
        "ts": pd.Timestamp("2025-01-01 12:00").timestamp(),
    }])
    df_watch = pd.DataFrame([{
        "user_id": 1,
        "movie_id": 42,
        "ts": pd.Timestamp("2025-01-01 12:05").timestamp(),
    }])
    result = compute_success(df_reco, df_watch, window_min=10)
    assert round(result.loc[0, "success_rate"], 2) == 1.00


def test_compute_success_failure():
    df_reco = pd.DataFrame([{
        "user_id": 1,
        "model": "m2",
        "movie_ids": [99],
        "ts": pd.Timestamp("2025-01-01 12:00").timestamp(),
    }])
    df_watch = pd.DataFrame([{
        "user_id": 1,
        "movie_id": 42,
        "ts": pd.Timestamp("2025-01-01 12:05").timestamp(),
    }])
    result = compute_success(df_reco, df_watch, window_min=10)
    assert result.loc[0, "success_rate"] == 0.0


def test_proportion_ci_bounds():
    lo, hi = proportion_ci(3, 10)
    assert 0 <= lo <= hi <= 1
