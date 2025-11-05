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
K = int(os.getenv("K", "10"))

# ---------------------------------------------------------------------
# Build user–item interaction matrix
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


# ---------------------------------------------------------------------
# Main training and evaluation
# ---------------------------------------------------------------------
def main():
    t0 = time.time()

    # --- Load and enforce int typing
    train = pd.read_csv(DATA / "train.csv")
    test  = pd.read_csv(DATA / "test.csv")

    for df in [train, test]:
        df["user"] = df["user"].astype(int)
        df["item"] = df["item"].astype(int)

    # --- Build matrix and compute similarities
    UI, uid, iid, users, items = build_ui(train)
    sims = cosine_similarity(UI.T, dense_output=False)

    with open(ART / "sims.pkl", "wb") as f:
        pickle.dump({"sims": sims, "iid": iid, "items": items}, f)

    inv_iid = {v: k for k, v in iid.items()}
    seen = train.groupby("user")["item"].apply(set).to_dict()

    # --- Recommendation function
    def recommend(u, k=K):
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

    # --- Evaluate
    hr, ndcg = [], []
    for _, row in test.iterrows():
        u = int(row["user"])
        true_i = int(row["item"])
        if u not in uid or u not in seen:
            continue
        rec = recommend(u, K)
        hr.append(hit_rate_at_k(rec, true_i, K))
        ndcg.append(ndcg_at_k(rec, true_i, K))

    # --- Save results
    meta = {
        "model": "itemcf",
        "k": K,
        "hr@k": float(np.mean(hr)),
        "ndcg@k": float(np.mean(ndcg)),
        "train_seconds": time.time() - t0,
        "model_size_bytes": pathlib.Path(ART / "sims.pkl").stat().st_size,
    }
    (ART / "meta.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))


# ---------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------
if __name__ == "__main__":
    sys.path.append(str((ROOT / "experiments/ml1m_baselines").resolve()))
    main()
