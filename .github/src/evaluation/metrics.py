import numpy as np

def hr_at_k(recommended, ground_truth, k=10):
    """
    recommended: list of item ids
    ground_truth: set or list of true items (at least one)
    """
    rec_k = set(recommended[:k])
    return 1.0 if len(rec_k.intersection(set(ground_truth))) > 0 else 0.0

def ndcg_at_k(recommended, ground_truth, k=10):
    rec_k = recommended[:k]
    dcg = 0.0
    for i, it in enumerate(rec_k, start=1):
        if it in ground_truth:
            dcg += 1.0 / np.log2(i + 1)
    idcg = 1.0  
    return dcg / idcg if idcg > 0 else 0.0