from __future__ import annotations

import os
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import argparse, json, math
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from numpy.linalg import norm


def leave_one_out(df: pd.DataFrame, user_col: str, item_col: str, seed: int = 42):
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


def make_csr(df: pd.DataFrame, user_col: str, item_col: str, u2i: dict, i2i: dict) -> csr_matrix:
    rows = df[user_col].map(lambda u: u2i[int(u)]).to_numpy()
    cols = df[item_col].map(lambda it: i2i[int(it)]).to_numpy()
    data = np.ones_like(rows, dtype=np.float32)
    return csr_matrix((data, (rows, cols)), shape=(len(u2i), len(i2i))).tocsr()


def hit_rate_at_k(recs: list[int], gt_item: int, k: int = 10) -> float:
    return 1.0 if gt_item in recs[:k] else 0.0

def ndcg_at_k(recs: list[int], gt_item: int, k: int = 10) -> float:
    for r, it in enumerate(recs[:k], start=1):
        if it == gt_item:
            return 1.0 / math.log2(r + 1)
    return 0.0


def popularity_model(train_df: pd.DataFrame, user_col: str, item_col: str):
    counts = (train_df
              .groupby(item_col)[user_col]
              .count()
              .sort_values(ascending=False))
    ranked_items = counts.index.to_numpy(dtype=np.int64)
    return ranked_items  

def recommend_popularity(global_ranked_items: np.ndarray, seen_raw: set[int], k: int) -> list[int]:
    if not len(seen_raw):
        return global_ranked_items[:k].tolist()
    mask = ~np.isin(global_ranked_items, list(seen_raw))
    return global_ranked_items[mask][:k].tolist()

def itemcf_prepare(UI: csr_matrix):
    IU = UI.T.tocsr() 
    norms = np.sqrt(IU.multiply(IU).sum(axis=1)).A1 + 1e-12
    return IU, norms

def recommend_itemcf(IU: csr_matrix, norms: np.ndarray, user_row: csr_matrix, seen: np.ndarray, k: int) -> list[int]:
    interacted = user_row.indices
    if interacted.size == 0:
        return []
    
    V_sum = IU[interacted].sum(axis=0)  
    scores = np.zeros(IU.shape[0], dtype=np.float32)
    for i in interacted:
        vi = IU[i]                  
        dots = IU @ vi.T            
        dots = np.asarray(dots.todense()).ravel()
        scores += (dots / (norms[i] * norms))
    if seen.size:
        scores[seen] = -np.inf
    k = min(k, scores.size)
    topk = np.argpartition(scores, -k)[-k:]
    topk = topk[np.argsort(scores[topk])[::-1]]
    return topk.tolist()


def als_load(reg_dir: Path):
    user_f = np.load(reg_dir / "user_factors.npy")
    item_f = np.load(reg_dir / "item_factors.npy")
    users = np.array(json.loads((reg_dir / "users.json").read_text()), dtype=np.int64)
    items = np.array(json.loads((reg_dir / "items.json").read_text()), dtype=np.int64)
    return user_f, item_f, users, items

def recommend_als(user_vec: np.ndarray, item_f: np.ndarray, seen_idx: np.ndarray, k: int) -> list[int]:
    n_items = item_f.shape[0]
    scores = item_f @ user_vec
    if seen_idx.size:
        seen_idx = seen_idx[(seen_idx >= 0) & (seen_idx < n_items)]
        scores[seen_idx] = -np.inf
    k = min(k, n_items)
    if k <= 0:
        return []
    topk = np.argpartition(scores, -k)[-k:]
    topk = topk[np.argsort(scores[topk])[::-1]]
    return topk.tolist()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ratings_csv", default="data/processed/ratings_implicit.csv")
    ap.add_argument("--user_col", default="user_id")
    ap.add_argument("--item_col", default="item_id")
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--als_dir", default="model_registry/v0.2/als")
    ap.add_argument("--out_csv", default="reports/offline_metrics.csv")
    args = ap.parse_args()

    Path("reports").mkdir(exist_ok=True)

    df = pd.read_csv(args.ratings_csv)
    train_df, test_df = leave_one_out(df, args.user_col, args.item_col, seed=42)
    users_raw = np.sort(train_df[args.user_col].astype(int).unique())
    items_raw = np.sort(train_df[args.item_col].astype(int).unique())
    u2i = {u:i for i,u in enumerate(users_raw)}
    i2i = {it:i for i,it in enumerate(items_raw)}
    UI = make_csr(train_df, args.user_col, args.item_col, u2i, i2i)  

    rows = []
    K = args.k
    global_rank = popularity_model(train_df, args.user_col, args.item_col)
    hr_list, ndcg_list = [], []
    for _, row in test_df.iterrows():
        u = int(row[args.user_col]); gt = int(row[args.item_col])
        if u not in u2i:  
            continue
        seen_raw = set(train_df.loc[train_df[args.user_col]==u, args.item_col].astype(int).tolist())
        recs = recommend_popularity(global_rank, seen_raw, K)
        hr_list.append(hit_rate_at_k(recs, gt, K))
        ndcg_list.append(ndcg_at_k(recs, gt, K))
    rows.append({"model":"popularity","version":"v0.1","K":K,
                 "HR@K":float(np.mean(hr_list) if hr_list else 0.0),
                 "NDCG@K":float(np.mean(ndcg_list) if ndcg_list else 0.0)})
    IU, norms = itemcf_prepare(UI)            
    hr_list, ndcg_list = [], []
    for _, row in test_df.iterrows():
        u = int(row[args.user_col]); gt = int(row[args.item_col])
        if (u not in u2i) or (gt not in i2i):  
            continue
        uidx = u2i[u]; seen = UI[uidx].indices
        rec_idx = recommend_itemcf(IU, norms, UI[uidx], seen, K)
        rec_raw = items_raw[rec_idx] if len(rec_idx) else []
        hr_list.append(hit_rate_at_k(list(rec_raw), gt, K))
        ndcg_list.append(ndcg_at_k(list(rec_raw), gt, K))
    rows.append({"model":"itemcf","version":"v0.1","K":K,
                 "HR@K":float(np.mean(hr_list) if hr_list else 0.0),
                 "NDCG@K":float(np.mean(ndcg_list) if ndcg_list else 0.0)})

    als_dir = Path(args.als_dir)
    if als_dir.exists():
        user_f, item_f, users_art, items_art = als_load(als_dir)
        raw_item_to_local = {int(r): i for i, r in enumerate(items_raw)}
        hr_list, ndcg_list = [], []
        for _, row in test_df.iterrows():
            u = int(row[args.user_col]); gt = int(row[args.item_col])
            if (u not in u2i) or (gt not in raw_item_to_local):
                continue
            uidx = u2i[u]
            seen = UI[uidx].indices
        else:
            pass

        als_item_pos = {int(r): i for i, r in enumerate(items_art)}
        hr_list, ndcg_list = [], []
        for _, row in test_df.iterrows():
            u = int(row[args.user_col]); gt = int(row[args.item_col])
            if (u not in u2i) or (gt not in als_item_pos):
                continue
            uidx = u2i[u]
            if uidx >= user_f.shape[0]:
                continue
            seen_local = UI[uidx].indices
            seen_als = [als_item_pos[int(items_raw[j])] for j in seen_local if int(items_raw[j]) in als_item_pos]
            seen_als = np.array(seen_als, dtype=np.int64)
            rec_idx = recommend_als(user_f[uidx], item_f, seen_als, K)
            rec_raw = items_art[rec_idx]
            hr_list.append(hit_rate_at_k(list(rec_raw), gt, K))
            ndcg_list.append(ndcg_at_k(list(rec_raw), gt, K))
        rows.append({"model":"als","version":"v0.2","K":K,
                     "HR@K":float(np.mean(hr_list) if hr_list else 0.0),
                     "NDCG@K":float(np.mean(ndcg_list) if ndcg_list else 0.0)})
    else:
        rows.append({"model":"als","version":"v0.2","K":K,"HR@K":None,"NDCG@K":None})

    out = Path(args.out_csv)
    out.parent.mkdir(exist_ok=True, parents=True)
    pd.DataFrame(rows).to_csv(out, index=False)
    print(f"[OK] Wrote {out}")
    print(pd.DataFrame(rows))
    

if __name__ == "__main__":
    main()
