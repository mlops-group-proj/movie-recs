import pandas as pd
import numpy as np
import time, pickle, pathlib, json, os, sys
from scipy.sparse import csr_matrix
from sklearn.metrics.pairwise import cosine_similarity
from metrics import hit_rate_at_k, ndcg_at_k

# ---------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------
ROOT = pathlib.Path(__file__).resolve().parents[2]
DATA = ROOT / "data/ml1m_prepared"
REG  = ROOT / "model_registry"; REG.mkdir(exist_ok=True)
ART  = REG / "v_itemcf"; ART.mkdir(exist_ok=True)

CONFIG = {
    "K": int(os.getenv("K", "10")),
    "TIME_SPLIT_COL": os.getenv("TIME_COL", "timestamp"),
    "SPLIT_RATIO": float(os.getenv("SPLIT_RATIO", "0.8")),
    "SEED": int(os.getenv("SEED", "42"))
}

np.random.seed(CONFIG["SEED"])

# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def build_ui(train):
    users = np.sort(train["user"].unique())
    items = np.sort(train["item"].unique())
    uid = {u: i for i, u in enumerate(users)}
    iid = {i: j for j, i in enumerate(items)}
    rows = train["user"].map(uid).to_numpy()
    cols = train["item"].map(iid).to_numpy()
    vals = np.ones_like(rows, dtype=np.float32)
    M = csr_matrix((vals, (rows, cols)), shape=(len(users), len(items)))
    return M, uid, iid, users, items

def chronological_split(df, time_col="timestamp", ratio=0.8):
    """Split by time rather than random sampling."""
    if time_col not in df.columns:
        raise ValueError(f"Missing timestamp column '{time_col}' in dataset")
    df = df.sort_values(time_col)
    cutoff = int(len(df) * ratio)
    return df.iloc[:cutoff].copy(), df.iloc[cutoff:].copy()

# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------
def main():
    t0 = time.time()

    # --- Load data
    ratings = pd.read_csv(DATA / "ratings.csv")  # unified file
    ratings["user"] = ratings["user"].astype(int)
    ratings["item"] = ratings["item"].astype(int)

    # --- Chronological split (Milestone 3 requirement)
    train, test = chronological_split(
        ratings, CONFIG["TIME_SPLIT_COL"], CONFIG["SPLIT_RATIO"]
    )

    # --- Build matrix & similarities
    UI, uid, iid, users, items = build_ui(train)
    sims = cosine_similarity(UI.T, dense_output=False)
    with open(ART / "sims.pkl", "wb") as f:
        pickle.dump({"sims": sims, "iid": iid, "items": items}, f)

    inv_iid = {v: k for k, v in iid.items()}
    seen = train.groupby("user")["item"].apply(set).to_dict()

    def recommend(u, k=CONFIG["K"]):
        if u not in uid:
            return items[:k]
        user_row = UI[uid[u]]
        scores = user_row.dot(sims).toarray().ravel()
        rec = np.argsort(-scores)
        reco_items = []
        seen_i = seen.get(u, set())
        for j in rec:
            it = inv_iid.get(j, items[j] if j < len(items) else None)
            if it is None or it in seen_i:
                continue
            reco_items.append(it)
            if len(reco_items) == k:
                break
        return reco_items

    # --- Evaluate overall
    hr, ndcg = [], []
    for _, row in test.iterrows():
        u, true_i = int(row["user"]), int(row["item"])
        if u not in uid:
            continue
        rec = recommend(u, CONFIG["K"])
        hr.append(hit_rate_at_k(rec, true_i, CONFIG["K"]))
        ndcg.append(ndcg_at_k(rec, true_i, CONFIG["K"]))

    overall = {"hr@k": np.mean(hr), "ndcg@k": np.mean(ndcg)}

    # --- Subpopulation analysis (cold vs warm users)
    user_interacts = train["user"].value_counts()
    cold_users = user_interacts[user_interacts <= 5].index
    warm_users = user_interacts[user_interacts > 5].index

    def eval_subset(subset_users):
        hr_s, ndcg_s = [], []
        sub = test[test["user"].isin(subset_users)]
        for _, row in sub.iterrows():
            u, true_i = int(row["user"]), int(row["item"])
            if u not in uid:
                continue
            rec = recommend(u, CONFIG["K"])
            hr_s.append(hit_rate_at_k(rec, true_i, CONFIG["K"]))
            ndcg_s.append(ndcg_at_k(rec, true_i, CONFIG["K"]))
        return np.mean(hr_s or [0]), np.mean(ndcg_s or [0])

    cold_hr, cold_ndcg = eval_subset(cold_users)
    warm_hr, warm_ndcg = eval_subset(warm_users)

    # --- Save results
    meta = {
        "model": "itemcf",
        "k": CONFIG["K"],
        "overall": overall,
        "cold_users": {"hr@k": cold_hr, "ndcg@k": cold_ndcg},
        "warm_users": {"hr@k": warm_hr, "ndcg@k": warm_ndcg},
        "train_seconds": time.time() - t0,
        "split_ratio": CONFIG["SPLIT_RATIO"],
        "seed": CONFIG["SEED"],
    }
    out_json = ART / "meta.json"
    out_csv = ART / "results.csv"
    (ART / "meta.json").write_text(json.dumps(meta, indent=2))
    pd.DataFrame([
        ["overall", overall["hr@k"], overall["ndcg@k"]],
        ["cold_users", cold_hr, cold_ndcg],
        ["warm_users", warm_hr, warm_ndcg],
    ], columns=["subset", "hr@k", "ndcg@k"]).to_csv(out_csv, index=False)

    print(json.dumps(meta, indent=2))
    print(f"\nResults saved to {out_json} and {out_csv}")

# ---------------------------------------------------------------------
if __name__ == "__main__":
    sys.path.append(str((ROOT / "experiments/ml1m_baselines").resolve()))
    main()
