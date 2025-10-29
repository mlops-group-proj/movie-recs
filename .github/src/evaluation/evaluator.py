import pandas as pd
from collections import defaultdict
from .metrics import hr_at_k, ndcg_at_k

def evaluate_topk(model, test_df: pd.DataFrame, user_col: str, item_col: str, k: int = 10):
    # Build ground-truth per user (items in test set)
    truth = defaultdict(set)
    for row in test_df[[user_col, item_col]].itertuples(index=False):
        truth[getattr(row, user_col)].add(getattr(row, item_col))

    users = list(truth.keys())
    recs = model.recommend_for_users(users, top_k=k)

    hrs, ndcgs = [], []
    for u in users:
        rec_list = recs.get(u, [])
        gt = truth[u]
        hrs.append(hr_at_k(rec_list, gt, k=k))
        ndcgs.append(ndcg_at_k(rec_list, gt, k=k))

    return {
        "users_evaluated": len(users),
        "HR@{}".format(k): sum(hrs) / len(hrs) if hrs else 0.0,
        "NDCG@{}".format(k): sum(ndcgs) / len(ndcgs) if ndcgs else 0.0,
    }