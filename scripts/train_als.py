# scripts/train_als.py
from __future__ import annotations

# ---- put env vars BEFORE any numeric imports (quiet BLAS warnings)
import os
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import argparse
import json
from pathlib import Path
import math
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix, save_npz
from implicit.als import AlternatingLeastSquares


COLUMN_ALIASES = {
    "user_id": ["userId", "userid", "userID"],
    "item_id": ["itemId", "itemid", "itemID", "movieId", "movie_id", "movieID", "movieid"],
}


def _normalize_col_key(name: str) -> str:
    """Lowercase column name and drop non-alphanumeric chars for fuzzy matching."""
    return "".join(ch for ch in name.lower() if ch.isalnum())


def ensure_column(df: pd.DataFrame, target_name: str) -> pd.DataFrame:
    """
    Ensure the requested column exists.
    If a case/format variant exists (e.g., userId vs user_id), rename it lazily.
    """
    if target_name in df.columns:
        return df

    for alias in COLUMN_ALIASES.get(target_name, []):
        if alias in df.columns:
            print(f"[INFO] Renaming column '{alias}' -> '{target_name}' for compatibility.")
            return df.rename(columns={alias: target_name})

    target_key = _normalize_col_key(target_name)
    for col in df.columns:
        if _normalize_col_key(col) == target_key:
            print(f"[INFO] Renaming column '{col}' -> '{target_name}' for compatibility.")
            return df.rename(columns={col: target_name})

    raise KeyError(f"Column '{target_name}' not found in DataFrame columns: {list(df.columns)}")


# ---------- helpers: mapping, matrix, split ----------
def build_uid_iid_maps(df: pd.DataFrame, user_col: str, item_col: str):
    """
    Build raw-id -> index maps from the TRAIN data only.
    Return maps and arrays of raw ids in index order.
    """
    users = df[user_col].astype(int).unique()
    items = df[item_col].astype(int).unique()

    u2i = {int(u): i for i, u in enumerate(users)}
    i2i = {int(it): i for i, it in enumerate(items)}

    users_arr = np.asarray(users, dtype=np.int64)
    items_arr = np.asarray(items, dtype=np.int64)
    return u2i, i2i, users_arr, items_arr


def make_csr(
    df: pd.DataFrame,
    user_col: str,
    item_col: str,
    u2i: dict[int, int],
    i2i: dict[int, int],
    weight_col: str | None = None,
) -> csr_matrix:
    """
    Build a USER x ITEM CSR matrix from triples.
    Rows are user indices. Columns are item indices.
    """
    rows = df[user_col].map(lambda u: u2i[int(u)]).to_numpy()
    cols = df[item_col].map(lambda it: i2i[int(it)]).to_numpy()
    if weight_col and (weight_col in df.columns):
        data = df[weight_col].astype(float).to_numpy()
    else:
        data = np.ones_like(rows, dtype=np.float32)

    n_users, n_items = len(u2i), len(i2i)
    return csr_matrix((data, (rows, cols)), shape=(n_users, n_items)).tocsr()


def leave_one_out(df: pd.DataFrame, user_col: str, item_col: str, seed: int = 42):
    """
    Random leave-one-out per user (users with <2 interactions are dropped).
    No groupby.apply (avoids future warnings).
    """
    rng = np.random.default_rng(seed)

    counts = df.groupby(user_col)[item_col].size()
    keep_users = counts[counts >= 2].index
    df2 = df[df[user_col].isin(keep_users)].copy()

    test_idx = []
    for _, idxs in df2.groupby(user_col).indices.items():
        test_idx.append(int(rng.choice(idxs)))
    test_idx = set(test_idx)

    mask = df2.index.to_series().isin(test_idx)
    test = df2.loc[mask, [user_col, item_col]].reset_index(drop=True)
    train = df2.loc[~mask].reset_index(drop=True)
    return train, test


# ---------- metrics ----------
def hit_rate_at_k(recs: list[int], gt_item: int, k: int = 10) -> float:
    return 1.0 if gt_item in recs[:k] else 0.0


def ndcg_at_k(recs: list[int], gt_item: int, k: int = 10) -> float:
    for r, it in enumerate(recs[:k], start=1):
        if it == gt_item:
            return 1.0 / math.log2(r + 1)
    return 0.0


# ---------- safe top-k (manual) ----------
def topk_manual(
    user_vec: np.ndarray,
    item_factors: np.ndarray,
    seen_idx: np.ndarray,
    k: int,
) -> np.ndarray:
    """
    Compute scores = item_factors @ user_vec, mask seen items, return top-k indices.
    Robust to any out-of-range values in seen_idx.
    """
    # Sanity: shape check
    n_items, f = item_factors.shape
    if user_vec.shape[-1] != f:
        raise ValueError(f"user_vec dim {user_vec.shape[-1]} != item_factors dim {f}")

    scores = item_factors @ user_vec  # (n_items,)

    # Clip seen indices to valid range (avoid IndexError)
    if seen_idx is not None and seen_idx.size:
        seen_idx = seen_idx.astype(np.int64, copy=False)
        seen_idx = seen_idx[(seen_idx >= 0) & (seen_idx < n_items)]
        if seen_idx.size:
            scores[seen_idx] = -np.inf

    k = min(k, n_items)
    if k <= 0:
        return np.array([], dtype=np.int64)

    # Top-k via argpartition then sort that slice
    topk = np.argpartition(scores, -k)[-k:]
    topk = topk[np.argsort(scores[topk])[::-1]]
    return topk


# ---------- main ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ratings_csv", required=True, help="Path to interactions/ratings CSV")
    ap.add_argument("--user_col", default="user_id")
    ap.add_argument("--item_col", default="item_id")
    ap.add_argument("--weight_col", default=None, help="Optional implicit weight column")
    ap.add_argument("--factors", type=int, default=64)
    ap.add_argument("--iters", type=int, default=15)
    ap.add_argument("--reg", type=float, default=0.01)
    ap.add_argument("--k_eval", type=int, default=10)
    ap.add_argument("--output_dir", default="model_registry/v0.2/als")
    args = ap.parse_args()

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # 1) Load data + split
    df = pd.read_csv(args.ratings_csv)

    # Normalize column names so downstream code can rely on args.user_col/item_col/weight_col
    for col in filter(None, [args.user_col, args.item_col, args.weight_col]):
        df = ensure_column(df, col)

    train_df, test_df = leave_one_out(df, args.user_col, args.item_col, seed=42)

    # 2) Mappings + train matrix from TRAIN ONLY
    u2i, i2i, users_arr, items_arr = build_uid_iid_maps(train_df, args.user_col, args.item_col)
    UI = make_csr(train_df, args.user_col, args.item_col, u2i, i2i, args.weight_col)  # U x I

    # 3) Train ALS (implicit expects I x U as CSR)
    model = AlternatingLeastSquares(
        factors=args.factors,
        iterations=args.iters,
        regularization=args.reg,
    )
    model.fit(UI.T.tocsr())  # I x U

    # --- shape sanity checks (helpful if anything goes out of sync) ---
    n_users, n_items = UI.shape
    if model.item_factors.shape[0] != n_items:
        print(
            f"[WARN] item_factors rows ({model.item_factors.shape[0]}) "
            f"!= n_items from UI ({n_items}). Proceeding with min(...) to be safe."
        )
    # ------------------------------------------------------------------

    # 4) Evaluate HR@K / NDCG@K safely
    test_known = test_df[
        test_df[args.user_col].isin(u2i) & test_df[args.item_col].isin(i2i)
    ]
    hrs, ndcgs = [], []

    item_f = model.item_factors  # I x F
    user_f = model.user_factors  # U x F

    for _, row in test_known.iterrows():
        u_raw = int(row[args.user_col])
        i_gt_raw = int(row[args.item_col])
        u_idx = u2i[u_raw]
        gt_idx = i2i[i_gt_raw]

        # items this user has seen (column indices in [0..n_items-1])
        seen_idx = UI[u_idx].indices

        # top-k by manual scoring (robust to any odd index values)
        rec_indices = topk_manual(user_f[u_idx], item_f, seen_idx, k=args.k_eval)
        rec_raw_items = items_arr[rec_indices].tolist()

        hrs.append(hit_rate_at_k(rec_raw_items, i_gt_raw, k=args.k_eval))
        ndcgs.append(ndcg_at_k(rec_raw_items, i_gt_raw, k=args.k_eval))

    hr = float(np.mean(hrs)) if hrs else 0.0
    ndcg = float(np.mean(ndcgs)) if ndcgs else 0.0
    print(f"[ALS] HR@{args.k_eval}={hr:.4f}  NDCG@{args.k_eval}={ndcg:.4f}")

    # 5) Save artifacts (factors, id lists, train CSR, meta with metrics)
    np.save(out / "user_factors.npy", user_f)
    np.save(out / "item_factors.npy", item_f)
    (out / "users.json").write_text(json.dumps(list(map(int, users_arr))))
    (out / "items.json").write_text(json.dumps(list(map(int, items_arr))))
    save_npz(out / "seen_csr.npz", UI)

    meta = {
        "type": "ALS",
        "factors": args.factors,
        "iterations": args.iters,
        "regularization": args.reg,
        "users": int(len(u2i)),
        "items": int(len(i2i)),
        "k_eval": int(args.k_eval),
        "hr": hr,
        "ndcg": ndcg,
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2))
    print(f"[ALS] Saved artifacts to: {out.resolve()}")


if __name__ == "__main__":
    main()
