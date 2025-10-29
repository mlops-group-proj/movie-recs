import numpy as np
import pandas as pd
from scipy.sparse import coo_matrix
from typing import Dict, Any

class ALSModel:
    def __init__(self, rank=64, reg=0.01, iters=15, user_map=None, item_map=None):
        self.rank = rank
        self.reg = reg
        self.iters = iters
        self.user_map = user_map or {}
        self.item_map = item_map or {}
        self.U = None
        self.V = None

    def _encode_ids(self, df, user_col, item_col):
        if not self.user_map:
            self.user_map = {u:i for i, u in enumerate(df[user_col].unique())}
        if not self.item_map:
            self.item_map = {m:i for i, m in enumerate(df[item_col].unique())}
        ui = df[user_col].map(self.user_map).values
        ii = df[item_col].map(self.item_map).values
        return ui, ii

    def fit(self, df: pd.DataFrame, user_col: str, item_col: str, rating_col: str):
        ui, ii = self._encode_ids(df, user_col, item_col)
        vals = df[rating_col].astype(float).values
        mat = coo_matrix((vals, (ui, ii)), shape=(len(self.user_map), len(self.item_map)))
        rng = np.random.default_rng(42)
        self.U = rng.normal(size=(mat.shape[0], self.rank))
        self.V = rng.normal(size=(mat.shape[1], self.rank))

    def recommend_for_users(self, user_ids, top_k=10):
        scores = self.U @ self.V.T
        out = {}
        for uid in user_ids:
            idx = self.user_map.get(uid, None)
            if idx is None: 
                out[uid] = []
                continue
            top_items = np.argsort(-scores[idx])[:top_k]
            rev_item = {v:k for k,v in self.item_map.items()}
            out[uid] = [rev_item[i] for i in top_items]
        return out

    def to_dict(self) -> Dict[str, Any]:
        return {"rank": self.rank, "reg": self.reg, "iters": self.iters}