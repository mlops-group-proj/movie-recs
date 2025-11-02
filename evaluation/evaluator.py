from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable, Optional, Set, Dict
import numpy as np
import pandas as pd


@dataclass
class EvalResult:
    users: int
    k: int
    hr: float
    ndcg: float


def _build_user_pos(df: pd.DataFrame, user_col: str, item_col: str) -> Dict[int, Set[int]]:
    pos: Dict[int, Set[int]] = {}
    for u, g in df.groupby(user_col):
        pos[int(u)] = set(map(int, g[item_col].tolist()))
    return pos


def _ndcg_at_k(ranked: Iterable[int], positives: Set[int], k: int) -> float:
    ndcg = 0.0
    for i, it in enumerate(ranked[:k], start=1):
        if it in positives:
            ndcg += 1.0 / np.log2(i + 1)
    ideal_hits = min(len(positives), k)
    if ideal_hits == 0:
        return 0.0
    idcg = sum(1.0 / np.log2(i + 1) for i in range(1, ideal_hits + 1))
    return float(ndcg / idcg)


def _hr_at_k(ranked: Iterable[int], positives: Set[int], k: int) -> float:
    topk = set(ranked[:k])
    return 1.0 if (topk & positives) else 0.0


def _sample_negatives(
    all_items: np.ndarray,
    forbidden: Set[int],
    n: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """
    Sample up to n negatives without replacement from all_items \ forbidden.
    If fewer than n are available, return all available (no error).
    """
    avail = np.setdiff1d(all_items, np.fromiter((int(x) for x in forbidden), dtype=int, count=len(forbidden)))
    m = min(int(n), int(avail.size))
    if m <= 0:
        return np.empty((0,), dtype=int)
    return rng.choice(avail, size=m, replace=False).astype(int)


def evaluate_topk(
    model,
    *,
    test_df: pd.DataFrame,
    user_col: str,
    item_col: str,
    k: int = 10,
    train_df: Optional[pd.DataFrame] = None,
    negatives_per_user: int = 99,
    items_df: Optional[pd.DataFrame] = None,
    item_id_col: Optional[str] = None,
    seed: int = 42,
) -> EvalResult:
    """
    Computes HR@K and NDCG@K using sampled negatives.
    Requires model.score_items(user_id, item_ids) -> np.ndarray (higher is better).
    """
    assert user_col in test_df.columns and item_col in test_df.columns

    rng = np.random.default_rng(seed)

    if items_df is not None:
        col = item_id_col or item_col
        universe = np.asarray(items_df[col].astype(int).unique(), dtype=int)
    else:
        pools = [test_df[item_col].astype(int).unique()]
        if train_df is not None:
            pools.append(train_df[item_col].astype(int).unique())
        universe = np.asarray(np.unique(np.concatenate(pools)), dtype=int)

    seen: Dict[int, Set[int]] = _build_user_pos(train_df[[user_col, item_col]], user_col, item_col) if train_df is not None else {}

    test_pos = _build_user_pos(test_df[[user_col, item_col]], user_col, item_col)

    hrs, ndcgs = [], []
    for u, positives in test_pos.items():
        forbidden = set(positives) | seen.get(u, set())
        negs = _sample_negatives(universe, forbidden, negatives_per_user, rng)
        for pos_item in positives:
            cand = np.concatenate([[int(pos_item)], negs])
            scores = model.score_items(int(u), cand)
            order = np.argsort(-scores)
            ranked = cand[order].tolist()
            hrs.append(_hr_at_k(ranked, {int(pos_item)}, k))
            ndcgs.append(_ndcg_at_k(ranked, {int(pos_item)}, k))

    return EvalResult(users=len(test_pos), k=k, hr=float(np.mean(hrs)), ndcg=float(np.mean(ndcgs)))