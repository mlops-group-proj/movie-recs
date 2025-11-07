# recommender/evaluator.py
"""
Lightweight top-K ranking metrics for implicit feedback.

Each metric expects:
- preds: List[List[int]]  -> per-user ranked recommendations (best → worst)
- truth: List[int] or List[Set[int]] -> per-user relevant item(s)

Notes
-----
* Duplicates in predictions are ignored (first occurrence kept).
* k is clipped to the available number of predictions.
* All metrics return population averages in [0, 1].
"""

from __future__ import annotations
from typing import Iterable, List, Sequence, Set, Union, Dict

Relevant = Union[Set[int], Sequence[int]]


def _to_relevant(x: Relevant) -> Set[int]:
    # Accepts single id list like [42] or multi-relevant set/list
    return set(x) if isinstance(x, (set, list, tuple)) else {int(x)}  # type: ignore


def _unique_keep_order(items: Iterable[int]) -> List[int]:
    seen = set()
    out = []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out


def _safe_k(preds_row: Sequence[int], k: int) -> int:
    if k <= 0:
        return 0
    return min(k, len(preds_row))


# ------------------------------ Core metrics ------------------------------

def hit_rate(preds: List[Sequence[int]], truth: List[Relevant], k: int = 10) -> float:
    """
    HR@K: fraction of users with at least one relevant item in top-K.
    """
    if not preds or not truth:
        return 0.0
    assert len(preds) == len(truth), "preds and truth must have the same length"

    hits, n = 0, len(preds)
    for p, t in zip(preds, truth):
        rel = _to_relevant(t)
        topk = _unique_keep_order(p)[:_safe_k(p, k)]
        if rel and any(it in rel for it in topk):
            hits += 1
    return hits / n if n else 0.0


def precision_at_k(preds: List[Sequence[int]], truth: List[Relevant], k: int = 10) -> float:
    """
    Precision@K: average |relevant ∩ topK| / K (per-user, then mean).
    If K > len(preds_row), denominator becomes len(preds_row).
    """
    if not preds or not truth:
        return 0.0
    assert len(preds) == len(truth)

    vals = []
    for p, t in zip(preds, truth):
        rel = _to_relevant(t)
        topk = _unique_keep_order(p)[:_safe_k(p, k)]
        denom = max(1, len(topk))
        vals.append(len(rel.intersection(topk)) / denom)
    return sum(vals) / len(vals)


def recall_at_k(preds: List[Sequence[int]], truth: List[Relevant], k: int = 10) -> float:
    """
    Recall@K: average |relevant ∩ topK| / |relevant|.
    If a user has no relevant items, that user contributes 0.
    """
    if not preds or not truth:
        return 0.0
    assert len(preds) == len(truth)

    vals = []
    for p, t in zip(preds, truth):
        rel = _to_relevant(t)
        if not rel:
            vals.append(0.0)
            continue
        topk = _unique_keep_order(p)[:_safe_k(p, k)]
        vals.append(len(rel.intersection(topk)) / len(rel))
    return sum(vals) / len(vals)


def _dcg_at_k(rank_positions: List[int], k: int, gains: str = "exp") -> float:
    """
    Compute DCG for given 1-indexed rank positions of relevant hits.
    gains='exp' -> (2^rel - 1) / log2(1+rank); with binary rel this becomes 1/log2(1+rank)
    gains='linear' -> 1 / log2(1+rank)
    """
    import math

    dcg = 0.0
    for r in rank_positions:
        if r <= k:
            if gains == "exp":
                gain = 1.0  # binary relevance
            elif gains == "linear":
                gain = 1.0
            else:
                raise ValueError("gains must be 'exp' or 'linear'")
            dcg += gain / math.log2(r + 1)
    return dcg


def ndcg(preds: List[Sequence[int]], truth: List[Relevant], k: int = 10, gains: str = "exp") -> float:
    """
    nDCG@K with binary relevance.
    """
    if not preds or not truth:
        return 0.0
    assert len(preds) == len(truth)

    import math

    vals = []
    for p, t in zip(preds, truth):
        rel = _to_relevant(t)
        topk = _unique_keep_order(p)[:_safe_k(p, k)]
        if not topk or not rel:
            vals.append(0.0)
            continue

        # Collect 1-indexed ranks where we hit a relevant item
        ranks = [i + 1 for i, it in enumerate(topk) if it in rel]
        dcg = _dcg_at_k(ranks, k, gains=gains)

        # Ideal DCG: place up to min(|rel|, k) relevant items at ranks 1..R
        R = min(len(rel), len(topk), k)
        if R == 0:
            vals.append(0.0)
            continue
        ideal = sum(1.0 / math.log2(r + 1) for r in range(1, R + 1))
        vals.append(dcg / ideal if ideal > 0 else 0.0)

    return sum(vals) / len(vals)


def map_at_k(preds: List[Sequence[int]], truth: List[Relevant], k: int = 10) -> float:
    """
    Mean Average Precision@K (binary relevance).
    For each user, compute the average precision over the relevant hits in top-K.
    Users with no relevant items contribute 0.
    """
    if not preds or not truth:
        return 0.0
    assert len(preds) == len(truth)

    import math

    ap_vals = []
    for p, t in zip(preds, truth):
        rel = _to_relevant(t)
        topk = _unique_keep_order(p)[:_safe_k(p, k)]
        if not rel:
            ap_vals.append(0.0)
            continue

        hits, cum_prec = 0, 0.0
        for i, it in enumerate(topk, start=1):
            if it in rel:
                hits += 1
                cum_prec += hits / i
        ap = (cum_prec / hits) if hits > 0 else 0.0
        ap_vals.append(ap)
    return sum(ap_vals) / len(ap_vals)


def mrr_at_k(preds: List[Sequence[int]], truth: List[Relevant], k: int = 10) -> float:
    """
    Mean Reciprocal Rank@K.
    """
    if not preds or not truth:
        return 0.0
    assert len(preds) == len(truth)

    import math

    rr = []
    for p, t in zip(preds, truth):
        rel = _to_relevant(t)
        topk = _unique_keep_order(p)[:_safe_k(p, k)]
        rank = next((i + 1 for i, it in enumerate(topk) if it in rel), None)
        rr.append(1.0 / rank if rank else 0.0)
    return sum(rr) / len(rr)


# ------------------------------ Convenience wrapper ------------------------------

def evaluate_batch(
    preds: List[Sequence[int]],
    truth: List[Relevant],
    k: int = 10,
    *,
    gains: str = "exp",
) -> Dict[str, float]:
    """
    Compute a standard suite of offline ranking metrics at K.
    Returns a dict: { 'hr@k': ..., 'precision@k': ..., ... }.
    """
    return {
        f"hr@{k}": hit_rate(preds, truth, k),
        f"precision@{k}": precision_at_k(preds, truth, k),
        f"recall@{k}": recall_at_k(preds, truth, k),
        f"ndcg@{k}": ndcg(preds, truth, k, gains=gains),
        f"map@{k}": map_at_k(preds, truth, k),
        f"mrr@{k}": mrr_at_k(preds, truth, k),
    }


__all__ = [
    "hit_rate",
    "precision_at_k",
    "recall_at_k",
    "ndcg",
    "map_at_k",
    "mrr_at_k",
    "evaluate_batch",
]
