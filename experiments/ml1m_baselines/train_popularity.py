import pandas as pd
import numpy as np
import time, pickle, pathlib, json, os, sys
from metrics import hit_rate_at_k, ndcg_at_k

# ---------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------
ROOT = pathlib.Path(__file__).resolve().parents[2]
DATA = ROOT / "data/ml1m_prepared"
REG  = ROOT / "model_registry"; REG.mkdir(exist_ok=True)
ART  = REG / "v_popularity"; ART.mkdir(exist_ok=True)

K = int(os.getenv("K", "10"))

# ---------------------------------------------------------------------
# Main training and evaluation
# ---------------------------------------------------------------------
def main():
    t0 = time.time()

    # --- Load and ensure correct dtypes
    train = pd.read_csv(DATA / "train.csv")
    test  = pd.read_csv(DATA / "test.csv")

    for df in [train, test]:
        df["user"] = df["user"].astype(int)
        df["item"] = df["item"].astype(int)

    # --- Build popularity ranking (most-watched items overall)
    pop = train.groupby("item").size().sort_values(ascending=False).index.to_list()
    with open(ART / "model.pkl", "wb") as f:
        pickle.dump(pop, f)

    # --- Items each user has already seen (to avoid re-recommending)
    seen = train.groupby("user")["item"].apply(set).to_dict()

    # --- Evaluate
    hr, ndcg = [], []
    for _, row in test.iterrows():
        u = int(row["user"])
        true_i = int(row["item"])

        # skip users not seen in training
        if u not in seen:
            continue

        # recommend top-K unseen popular items
        rec = [i for i in pop if i not in seen[u]][:K]

        hr.append(hit_rate_at_k(rec, true_i, K))
        ndcg.append(ndcg_at_k(rec, true_i, K))

    # --- Store metrics and metadata
    meta = {
        "model": "popularity",
        "k": K,
        "hr@k": float(np.mean(hr)),
        "ndcg@k": float(np.mean(ndcg)),
        "train_seconds": time.time() - t0,
        "model_size_bytes": pathlib.Path(ART / "model.pkl").stat().st_size,
    }

    (ART / "meta.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))


# ---------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------
if __name__ == "__main__":
    sys.path.append(str((ROOT / "experiments/ml1m_baselines").resolve()))
    main()
