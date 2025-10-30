# src/data/splitter.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple, Optional
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SplitStats:
    users_total: int
    users_kept: int
    users_dropped_min_inter: int
    users_dropped_all_to_train: int
    users_dropped_all_to_test: int
    train_rows: int
    test_rows: int


def _ensure_columns(df: pd.DataFrame, *cols: str) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}. Got: {list(df.columns)}")


def _coerce_timestamp(ts: pd.Series) -> pd.Series:
    """
    Accepts int/float seconds, ms-like numbers, ISO strings, or pandas datetimes.
    Returns epoch milliseconds (Int64) for stable ordering.
    """
    if np.issubdtype(ts.dtype, np.number):
        s = pd.to_numeric(ts, errors="coerce")
        scale_to_ms = (s.fillna(0).abs().max() < 1_000_000_000_000)  # seconds → ms
        return (s * (1000 if scale_to_ms else 1)).astype("Int64")
    dt = pd.to_datetime(ts, errors="coerce", utc=True)
    return (dt.view("int64") // 1_000_000).astype("Int64")  # ns → ms


def chronological_split(
    df: pd.DataFrame,
    user_col: str = "userId",
    timestamp_col: str = "timestamp",
    holdout_ratio: float = 0.20,
    *,
    min_user_interactions: int = 2,
    drop_users_not_meeting_min: bool = True,
    stable_tie_break: bool = True,
    random_tie_break_seed: Optional[int] = 13,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Per-user chronological split to prevent temporal leakage.

    - For each user: sort ascending by timestamp (and a stable tiebreak).
    - Oldest (1 - holdout_ratio) → train; newest → test.
    - Users with < min_user_interactions:
        - drop entirely (default), or
        - keep entirely in train if drop_users_not_meeting_min=False.
    - Ties are broken stably by original row order, or deterministically random.

    Returns (train_df, test_df) with no overlap.
    """
    if not 0.0 < holdout_ratio < 1.0:
        raise ValueError("holdout_ratio must be in (0,1).")

    _ensure_columns(df, user_col, timestamp_col)
    if len(df) == 0:
        return df.copy(), df.copy()

    work = df.copy()
    work["_ts_ms"] = _coerce_timestamp(work[timestamp_col])

    # Tiebreaker
    if stable_tie_break:
        work["_tie"] = np.arange(len(work), dtype=np.int64)
    else:
        rng = np.random.default_rng(random_tie_break_seed)
        work["_tie"] = rng.permutation(len(work))

    # Sort
    work.sort_values([user_col, "_ts_ms", "_tie"], kind="mergesort", inplace=True)
    work["_rownum"] = work.groupby(user_col).cumcount()

    sizes = work.groupby(user_col, sort=False)["_ts_ms"].size().rename("n")
    split_idx = (sizes * (1.0 - holdout_ratio)).astype(int)
    split_idx = split_idx.clip(lower=1, upper=sizes - 1)  # ensure both sides non-empty

    too_small = sizes[sizes < min_user_interactions].index

    if drop_users_not_meeting_min:
        keep_users = sizes.index.difference(too_small)
        pruned = work[work[user_col].isin(keep_users)]
        sizes_k = pruned.groupby(user_col)["_ts_ms"].size()
        split_idx_k = (sizes_k * (1.0 - holdout_ratio)).astype(int).clip(lower=1, upper=sizes_k - 1)

        mark = split_idx_k.rename("split_at").to_frame()
        marked = pruned.merge(mark, left_on=user_col, right_index=True, how="left")
        train_mask = marked["_rownum"] < marked["split_at"]

        train_df = marked.loc[train_mask].drop(columns=["_ts_ms", "_tie", "_rownum", "split_at"])
        test_df = marked.loc[~train_mask].drop(columns=["_ts_ms", "_tie", "_rownum", "split_at"])

        return train_df.reset_index(drop=True), test_df.reset_index(drop=True)

    # keep too-small entirely in train
    small_mask = work[user_col].isin(too_small)
    big = work[~small_mask]
    small = work[small_mask]

    if not big.empty:
        sizes_b = big.groupby(user_col)["_ts_ms"].size()
        split_idx_b = (sizes_b * (1.0 - holdout_ratio)).astype(int).clip(lower=1, upper=sizes_b - 1)

        mark_b = split_idx_b.rename("split_at").to_frame()
        big_m = big.merge(mark_b, left_on=user_col, right_index=True, how="left")
        big_train = big_m.loc[big_m["_rownum"] < big_m["split_at"]]
        big_test = big_m.loc[big_m["_rownum"] >= big_m["split_at"]]
    else:
        big_train = big_test = big

    train_df = pd.concat([big_train, small], ignore_index=True)
    test_df = big_test.copy()

    train_df = train_df.drop(columns=["_ts_ms", "_tie", "_rownum", "split_at"], errors="ignore")
    test_df = test_df.drop(columns=["_ts_ms", "_tie", "_rownum", "split_at"], errors="ignore")

    return train_df.reset_index(drop=True), test_df.reset_index(drop=True)