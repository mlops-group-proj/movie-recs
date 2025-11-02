# recommender/factory.py
import numpy as np
import json
import os
import scipy.sparse as sp

MODEL_ROOT = os.getenv("MODEL_REGISTRY", "model_registry")
DEFAULT_VERSION = os.getenv("MODEL_VERSION", "v0.2")

def get_recommender(model_name: str = "als"):
    """
    Factory returning a recommender instance.
    Currently supports 'als' only.
    """
    if model_name.lower() == "als":
        path = os.path.join(MODEL_ROOT, DEFAULT_VERSION, "als")
        return ALSRecommender(path)
    else:
        raise ValueError(f"Unknown model: {model_name}")


class ALSRecommender:
    """
    Lightweight loader and inference class for pre-trained implicit ALS model.
    """

    def __init__(self, model_dir: str):
        self.model_dir = model_dir
        # Load model artifacts
        self.user_factors = np.load(os.path.join(model_dir, "user_factors.npy"))
        self.item_factors = np.load(os.path.join(model_dir, "item_factors.npy"))
        self.user_map = json.load(open(os.path.join(model_dir, "user_id_map.json")))
        self.item_map = json.load(open(os.path.join(model_dir, "item_id_map.json")))
        self.seen_csr = sp.load_npz(os.path.join(model_dir, "seen_csr.npz"))

        # Reverse lookup for item IDs
        self.rev_item_map = {v: k for k, v in self.item_map.items()}

    def recommend(self, user_id: int, k: int = 20):
        if str(user_id) not in self.user_map:
            raise ValueError(f"Unknown user_id {user_id}")

        u_idx = self.user_map[str(user_id)]
        user_vec = self.user_factors[u_idx]

        # Compute scores (dot product)
        scores = user_vec @ self.item_factors.T

        # Mask out items already seen
        seen_items = self.seen_csr[u_idx].indices
        scores[seen_items] = -np.inf

        # Top-K recommendations
        topk = np.argpartition(scores, -k)[-k:]
        topk = topk[np.argsort(scores[topk])[::-1]]

        return [int(self.rev_item_map[i]) for i in topk]
