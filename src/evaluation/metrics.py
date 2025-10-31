# src/evaluation/metrics.py
from __future__ import annotations
from typing import Iterable, Sequence
import math

def hr_at_k(truth: Iterable, ranked_items: Sequence, k: int) -> float:
    """
    Hit Rate@K: 1 if any ground-truth item appears in top-K ranked_items, else 0.
    """
    if k <= 0 or not ranked_items:
        return 0.0
    truth_set = set(truth)
    for item in ranked_items[:k]:
        if item in truth_set:
            return 1.0
    return 0.0

def ndcg_at_k(truth: Iterable, ranked_items: Sequence, k: int) -> float:
    """
    NDCG@K for binary relevance (multiple relevant items allowed).
    DCG: sum(1/log2(rank+1)) for each relevant item in top-K (rank starts at 1)
    IDCG: ideal DCG with min(len(truth), K) relevant items at the top.
    """
    if k <= 0 or not ranked_items:
        return 0.0
    truth_set = set(truth)
    dcg = 0.0
    for idx, item in enumerate(ranked_items[:k], start=1):
        if item in truth_set:
            dcg += 1.0 / math.log2(idx + 1)

    m = min(len(truth_set), k)
    if m == 0:
        return 0.0
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, m + 1))
    return dcg / idcg if idcg > 0 else 0.0
