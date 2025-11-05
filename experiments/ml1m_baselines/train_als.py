import pandas as pd
import numpy as np
import time, pickle, pathlib, json, os, sys
from scipy.sparse import csr_matrix
from implicit.als import AlternatingLeastSquares
from metrics import hit_rate_at_k, ndcg_at_k

# ---------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------
ROOT = pathlib.Path(__file__).resolve().parents[2]
DATA = ROOT / "data/ml1m_prepared"
REG  = ROOT / "model_registry"; REG.mkdir(exist_ok=True)
ART  = REG / "v_als"; ART.mkdir(exist_ok=True)

K        = int(os.getenv("K", "10"))
FACTORS  = int(os.getenv("ALS_FACTORS", "64"))
REG_L2   = float(os.getenv("ALS_REG", "0.01"))
ITERS    = int(os.getenv("ALS_ITERS", "15"))

# ---------------------------------------------------------------------
# Helper: build contiguous user-item matrix
# ---------------------------------------------------------------------
def build_ui(train: pd.DataFrame):
    # ensure contiguous 0-based integer IDs using factorize
    u_codes, u_uniques = pd.factorize(train["user_id"], sort=True)
    i_codes, i_uniques = pd.factorize(train["movie_id"], sort=True)

    vals = np.ones_like(u_codes, dtype=np.float32)
    UI = csr_matrix((vals, (u_codes, i_codes)),
                    shape=(len(u_uniques), len(i_uniques))).tocsr()

    uid = {int(u_uniques[i]): int(i) for i in range(len(u_uniques))}
    iid = {int(i_uniques[j]): int(j) for j in range(len(i_uniques))}
    users = np.array(u_uniques, dtype=np.int64)
    items = np.array(i_uniques, dtype=np.int64)

    print(f"[ALS] UI shape users x items = {UI.shape}")
    return UI, uid, iid, users, items


# ---------------------------------------------------------------------
# Main training and evaluation
# ---------------------------------------------------------------------
def main():
    t0 = time.time()

    # --- Load and rename to avoid .item() conflicts
    train = pd.read_csv(DATA / "train.csv").rename(columns={"user": "user_id", "item": "movie_id"})
    test  = pd.read_csv(DATA / "test.csv").rename(columns={"user": "user_id", "item": "movie_id"})

    UI, uid, iid, users, items = build_ui(train)

    # --- Train ALS
    model = AlternatingLeastSquares(
        factors=FACTORS,
        regularization=REG_L2,
        iterations=ITERS,
        random_state=42
    )
    # implicit expects item-user matrix for fitting
    model.fit(UI)

    # Persist model + metadata
    with open(ART / "model.pkl", "wb") as f:
        pickle.dump({"model": model, "uid": uid, "iid": iid, "items": items}, f)

    # --- Evaluate
    seen = train.groupby("user_id")["movie_id"].apply(set).to_dict()
    inv_iid = {v: k for k, v in iid.items()}

    hr, ndcg = [], []

    for _, row in test.iterrows():
        u, true_i = int(row.user_id), int(row.movie_id)
        if u not in uid:
            continue

        uid_idx = uid[u]

        # Recommend top items for this user
        rec_idx, _ = model.recommend(
            uid_idx, UI[uid_idx], N=K + len(seen.get(u, set()))
        )

        rec_items = []
        for j in rec_idx:
            raw_item = inv_iid.get(int(j), None)
            if raw_item is None:
                continue
            if raw_item not in seen.get(u, set()):
                rec_items.append(raw_item)
            if len(rec_items) == K:
                break

        hr.append(hit_rate_at_k(rec_items, true_i, K))
        ndcg.append(ndcg_at_k(rec_items, true_i, K))

    meta = {
        "model": "als",
        "k": K,
        "factors": FACTORS,
        "reg": REG_L2,
        "iters": ITERS,
        "hr@k": float(np.mean(hr)),
        "ndcg@k": float(np.mean(ndcg)),
        "train_seconds": time.time() - t0,
        "model_size_bytes": pathlib.Path(ART / "model.pkl").stat().st_size,
    }

    (ART / "meta.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    sys.path.append(str((ROOT / "experiments/ml1m_baselines").resolve()))
    main()
