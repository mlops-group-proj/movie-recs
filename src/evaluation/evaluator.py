import numpy as np
import pandas as pd
from dataclasses import dataclass

@dataclass
class EvalResult:
    users: int
    hr: float
    ndcg: float

def _ndcg_at_k(rank, k):
    return 1.0 / np.log2(rank + 1) if rank <= k else 0.0


def evaluate_topk(model, test_df, user_col, item_col, k=5,
                  train_df=None, negatives_per_user=99, all_items=None):
    users = []
    hrs, ndcgs = [], []

    if all_items is None:
        if train_df is None:
            raise ValueError("Provide train_df or all_items for negative sampling.")
        all_items = pd.Index(pd.concat([train_df[item_col], test_df[item_col]]).unique())
    else:
        if not isinstance(all_items, pd.Index):
            all_items = pd.Index(all_items)

    seen = train_df.groupby(user_col)[item_col].apply(set) if train_df is not None else pd.Series(dtype=object)

    rng = np.random.default_rng(42)

    for uid, pos_list in test_df.groupby(user_col)[item_col].apply(list).items():
        pos = pos_list[0]
        user_seen = seen.get(uid, set())
        pool = all_items.difference(pd.Index(list(user_seen) + [pos]))

        n = min(negatives_per_user, len(pool))
        if n == 0:
            continue

        cand_negs = pool.values if n == len(pool) else pool.values[rng.choice(len(pool), size=n, replace=False)]
        candidates = [pos] + cand_negs.tolist()

        scores = model.score_items(uid, candidates)
        order = np.argsort(scores)[::-1]
        ranked = [candidates[i] for i in order]
        rank = ranked.index(pos) + 1  # 1-based

        hrs.append(1.0 if rank <= k else 0.0)
        ndcgs.append(_ndcg_at_k(rank, k))
        users.append(uid)

    return EvalResult(users=len(users), hr=float(np.mean(hrs)), ndcg=float(np.mean(ndcgs)))
