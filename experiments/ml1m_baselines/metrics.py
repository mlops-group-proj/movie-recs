import numpy as np

def hit_rate_at_k(reco, truth_item, k=10):
    return 1.0 if truth_item in reco[:k] else 0.0

def ndcg_at_k(reco, truth_item, k=10):
    # binary relevance; DCG = 1/log2(rank+1) if found
    for idx, iid in enumerate(reco[:k], start=1):
        if iid == truth_item:
            return 1.0 / np.log2(idx + 1.0)
    return 0.0
