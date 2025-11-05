# inside class ALSModel:
def recommend(self, user_id: int, k: int, exclude_seen: bool = True, seen_items: Optional[set] = None):
    """
    Returns top-k item_ids for a user using learned factors.
    Assumes self.user_factors: dict[user_id] -> np.array(dim)
            self.item_factors: dict[item_id] -> np.array(dim)
    """
    import numpy as np
    if not hasattr(self, "user_factors") or not hasattr(self, "item_factors"):
        return []

    uf = self.user_factors.get(user_id)
    if uf is None:
        return []

    items = list(self.item_factors.keys())
    mat = np.stack([self.item_factors[i] for i in items], axis=0)  # [I, D]
    scores = mat @ uf  # [I]
    ranked_idx = np.argsort(-scores)  # descending

    picked: list = []
    seen_items = seen_items or set()
    for idx in ranked_idx:
        itm = items[int(idx)]
        if exclude_seen and itm in seen_items:
            continue
        picked.append(itm)
        if len(picked) >= k:
            break
    return picked
