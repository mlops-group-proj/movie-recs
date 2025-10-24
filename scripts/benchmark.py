from __future__ import annotations
import os, time, json, math, statistics as stats
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
try:
    import psutil
except Exception:
    psutil = None

def leave_one_out(df, user_col, item_col, seed=42):
    rng = np.random.default_rng(seed)
    cnt = df.groupby(user_col)[item_col].size()
    keep = cnt[cnt >= 2].index
    df2 = df[df[user_col].isin(keep)].copy()
    pick = []
    for _, idxs in df2.groupby(user_col).indices.items():
        pick.append(int(rng.choice(idxs)))
    pick = set(pick)
    mask = df2.index.to_series().isin(pick)
    return df2[~mask].reset_index(drop=True), df2[mask].reset_index(drop=True)

def make_csr(df, user_col, item_col):
    users = np.sort(df[user_col].astype(int).unique())
    items = np.sort(df[item_col].astype(int).unique())
    u2i = {u:i for i,u in enumerate(users)}
    i2i = {it:i for i,it in enumerate(items)}
    rows = df[user_col].map(lambda u: u2i[int(u)]).to_numpy()
    cols = df[item_col].map(lambda it: i2i[int(it)]).to_numpy()
    data = np.ones_like(rows, dtype=np.float32)
    UI = csr_matrix((data,(rows,cols)), shape=(len(users), len(items))).tocsr()
    return UI, users, items, u2i, i2i

def measure_mem_mb():
    if psutil:
        return psutil.Process(os.getpid()).memory_info().rss / (1024**2)
    return None  

def timer(fn, *args, **kwargs):
    mem_before = measure_mem_mb()
    t0 = time.perf_counter()
    out = fn(*args, **kwargs)
    t1 = time.perf_counter()
    mem_after = measure_mem_mb()
    return out, (t1 - t0), (None if mem_before is None or mem_after is None else max(mem_before, mem_after))

def pop_train(train_df, item_col, user_col):
    counts = train_df.groupby(item_col)[user_col].count().sort_values(ascending=False)
    return counts.index.to_numpy(dtype=np.int64)

def pop_recommend(global_rank, seen_raw, k):
    if not seen_raw: return global_rank[:k].tolist()
    mask = ~np.isin(global_rank, list(seen_raw))
    return global_rank[mask][:k].tolist()

def itemcf_prepare(UI: csr_matrix):
    IU = UI.T.tocsr()
    norms = np.sqrt(IU.multiply(IU).sum(axis=1)).A1 + 1e-12
    return IU, norms

def itemcf_recommend(IU, norms, user_row, seen_idx, k):
    interacted = user_row.indices
    if interacted.size == 0: return []
    scores = np.zeros(IU.shape[0], dtype=np.float32)
    for i in interacted:
        vi = IU[i]
        dots = IU @ vi.T
        dots = np.asarray(dots.todense()).ravel()
        scores += (dots / (norms[i] * norms))
    if seen_idx.size: scores[seen_idx] = -np.inf
    k = min(k, scores.size)
    topk = np.argpartition(scores, -k)[-k:]
    topk = topk[np.argsort(scores[topk])[::-1]]
    return topk.tolist()

def als_train(UI: csr_matrix, factors=64, iters=10, reg=0.01):
    from implicit.als import AlternatingLeastSquares
    model = AlternatingLeastSquares(factors=factors, iterations=iters, regularization=reg)
    model.fit(UI.T.tocsr())
    return model

def als_recommend(user_vec, item_f, seen_idx, k):
    n_items = item_f.shape[0]
    scores = item_f @ user_vec
    if seen_idx.size:
        seen_idx = seen_idx[(seen_idx >= 0) & (seen_idx < n_items)]
        scores[seen_idx] = -np.inf
    k = min(k, n_items)
    if k <= 0: return []
    topk = np.argpartition(scores, -k)[-k:]
    topk = topk[np.argsort(scores[topk])[::-1]]
    return topk.tolist()

def bench_train(df, user_col="user_id", item_col="item_id"):
    train, _ = leave_one_out(df, user_col, item_col)
    UI, users, items, u2i, i2i = make_csr(train, user_col, item_col)

    results = []

    _, dur, mem = timer(pop_train, train, item_col, user_col)
    results.append({"model":"popularity","version":"v0.1","train_seconds":dur,"peak_mem_mb":mem})

    _, dur, mem = timer(itemcf_prepare, UI)
    results.append({"model":"itemcf","version":"v0.1","train_seconds":dur,"peak_mem_mb":mem})

   
    model, dur, mem = timer(als_train, UI)
    results.append({"model":"als","version":"v0.2","train_seconds":dur,"peak_mem_mb":mem})

    Path("model_registry/v0.2/als").mkdir(parents=True, exist_ok=True)
    np.save("model_registry/v0.2/als/user_factors.npy", model.user_factors)
    np.save("model_registry/v0.2/als/item_factors.npy", model.item_factors)
    Path("model_registry/v0.2/als/users.json").write_text(json.dumps(list(map(int, users))))
    Path("model_registry/v0.2/als/items.json").write_text(json.dumps(list(map(int, items))))

    return results, UI, users, items, u2i, i2i, model

def bench_infer(UI, users, items, u2i, model, k=10, n_users_sample=500):
    rng = np.random.default_rng(0)
    cand = [u for u in users if UI[u2i[u]].indices.size > 0]
    sample_users = rng.choice(cand, size=min(n_users_sample, len(cand)), replace=False)

    lat = {"popularity":[], "itemcf":[], "als":[]}

    global_rank = pop_train(pd.DataFrame({"user_id":[], "item_id":[]}), "item_id", "user_id") 
    IU, norms = itemcf_prepare(UI)
    user_f = model.user_factors
    item_f = model.item_factors
    counts = np.asarray(UI.sum(axis=0)).ravel()
    global_order = np.argsort(-counts)
    global_items_raw = items[global_order]

    for u in sample_users:
        uidx = u2i[int(u)]
        seen_idx = UI[uidx].indices
        seen_raw = set(items[seen_idx].tolist())

        # pop
        t0 = time.perf_counter()
        recs = pop_recommend(global_items_raw, seen_raw, k)
        lat["popularity"].append((time.perf_counter()-t0)*1000)

        # itemcf
        t0 = time.perf_counter()
        _ = itemcf_recommend(IU, norms, UI[uidx], seen_idx, k)
        lat["itemcf"].append((time.perf_counter()-t0)*1000)

        # als
        t0 = time.perf_counter()
        _ = als_recommend(user_f[uidx], item_f, seen_idx, k)
        lat["als"].append((time.perf_counter()-t0)*1000)

    rows = []
    for m in ["popularity","itemcf","als"]:
        p50 = stats.median(lat[m]) if lat[m] else None
        p95 = np.percentile(lat[m], 95) if lat[m] else None
        rows.append({"model":m,"version":"v0.2" if m=="als" else "v0.1",
                     "k":k,"p50_ms":p50,"p95_ms":p95})
    return rows

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--ratings_csv", default="data/processed/ratings_implicit.csv")
    ap.add_argument("--user_col", default="user_id")
    ap.add_argument("--item_col", default="item_id")
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--out_train", default="reports/benchmark_train.csv")
    ap.add_argument("--out_infer", default="reports/benchmark_infer.csv")
    args = ap.parse_args()

    Path("reports").mkdir(exist_ok=True, parents=True)
    df = pd.read_csv(args.ratings_csv)

    train_rows, UI, users, items, u2i, i2i, als_model = bench_train(df, args.user_col, args.item_col)
    infer_rows = bench_infer(UI, users, items, u2i, als_model, k=args.k)

    pd.DataFrame(train_rows).to_csv(args.out_train, index=False)
    pd.DataFrame(infer_rows).to_csv(args.out_infer, index=False)
    print(f"[OK] wrote {args.out_train} and {args.out_infer}")

if __name__ == "__main__":
    main()
