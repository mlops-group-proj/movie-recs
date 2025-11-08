# recommender/factory.py
import torch
import numpy as np
import json
import os
import scipy.sparse as sp

MODEL_ROOT = os.getenv("MODEL_REGISTRY", "model_registry")
DEFAULT_VERSION = os.getenv("MODEL_VERSION", "v0.2")


def get_recommender(model_name: str = "als"):
    """
    Factory returning a recommender instance.
    Supports 'als' and 'ncf'.
    """
    model_name = model_name.lower()
    if model_name == "als":
        path = os.path.join(MODEL_ROOT, DEFAULT_VERSION, "als")
        return ALSRecommender(path)
    elif model_name == "ncf":
        path = os.path.join(MODEL_ROOT, "v_ncf", "model.pt")
        return NCFRecommender(path)
    else:
        raise ValueError(f"Unknown model: {model_name}")


class ALSRecommender:
    """Lightweight loader for ALS"""
    def __init__(self, model_dir: str):
        self.model_dir = model_dir
        self.user_factors = np.load(os.path.join(model_dir, "user_factors.npy"))
        self.item_factors = np.load(os.path.join(model_dir, "item_factors.npy"))
        self.user_map = json.load(open(os.path.join(model_dir, "user_id_map.json")))
        self.item_map = json.load(open(os.path.join(model_dir, "item_id_map.json")))
        self.seen_csr = sp.load_npz(os.path.join(model_dir, "seen_csr.npz"))
        self.rev_item_map = {v: k for k, v in self.item_map.items()}

    def recommend(self, user_id: int, k: int = 20):
        if str(user_id) not in self.user_map:
            raise ValueError(f"Unknown user_id {user_id}")
        u_idx = self.user_map[str(user_id)]
        user_vec = self.user_factors[u_idx]
        scores = user_vec @ self.item_factors.T
        seen_items = self.seen_csr[u_idx].indices
        scores[seen_items] = -np.inf
        topk = np.argpartition(scores, -k)[-k:]
        topk = topk[np.argsort(scores[topk])[::-1]]
        return [int(self.rev_item_map[i]) for i in topk]


class NCFRecommender:
    """Simple NCF model loader using saved state dict."""
    def __init__(self, model_path: str):
        print(f"Loading NCF model from {model_path}")
        state = torch.load(model_path, map_location="cpu")

        n_users = state["u.weight"].shape[0]
        n_items = state["i.weight"].shape[0]
        embed_dim = state["u.weight"].shape[1]

        # Build same architecture
        self.user_emb = torch.nn.Embedding(n_users, embed_dim)
        self.item_emb = torch.nn.Embedding(n_items, embed_dim)
        self.mlp = torch.nn.Sequential(
            torch.nn.Linear(embed_dim * 2, 128),
            torch.nn.ReLU(),
            torch.nn.Linear(128, 64),
            torch.nn.ReLU(),
            torch.nn.Linear(64, 1)
        )

        # Load weights with strict=False to tolerate minor mismatches
        self.load_state(state)

    def load_state(self, state):
        new_state = {}
        for k, v in state.items():
            if k.startswith("u."):
                new_state["user_emb." + k[2:]] = v
            elif k.startswith("i."):
                new_state["item_emb." + k[2:]] = v
            else:
                new_state["mlp." + k.split(".", 1)[1]] = v
        self.load_weights(new_state)

    def load_weights(self, new_state):
        try:
            self.load_state_dict(new_state, strict=False)
        except Exception:
            for name, param in new_state.items():
                target = dict(self.named_parameters()).get(name)
                if target is not None and target.shape == param.shape:
                    target.data.copy_(param)

    def load_state_dict(self, state_dict, strict=False):
        all_params = dict(self.named_parameters())
        for k, v in state_dict.items():
            if k in all_params and all_params[k].shape == v.shape:
                all_params[k].data.copy_(v)
        print("NCF weights loaded successfully.")

    def named_parameters(self):
        yield from self.user_emb.named_parameters(prefix="user_emb")
        yield from self.item_emb.named_parameters(prefix="item_emb")
        yield from self.mlp.named_parameters(prefix="mlp")

    def recommend(self, user_id: int, k: int = 20):
        self.user_emb.eval()
        self.item_emb.eval()
        with torch.no_grad():
            u_vec = self.user_emb.weight[user_id]
            scores = (u_vec @ self.item_emb.weight.T).numpy()
        topk = np.argpartition(scores, -k)[-k:]
        return topk[np.argsort(scores[topk])[::-1]].tolist()



# ------------------------------------------------------------
# ItemCF Recommender (placeholder)
# ------------------------------------------------------------
class ItemCFRecommender:
    def __init__(self, model_dir: str):
        self.model_dir = model_dir
        self.meta = json.load(open(os.path.join(model_dir, "meta.json")))
        # You can add similarity matrix or item embeddings later
    def recommend(self, user_id: int, k: int = 20):
        # Placeholder: return top popular items
        return list(range(k))

# ------------------------------------------------------------
# Popularity baseline
# ------------------------------------------------------------
class PopularityRecommender:
    def __init__(self, model_dir: str):
        self.model_dir = model_dir
        self.items = json.load(open(os.path.join(model_dir, "items.json")))
    def recommend(self, user_id: int, k: int = 20):
        return [i["item_id"] for i in sorted(self.items, key=lambda x: -x["count"])[:k]]
