import pandas as pd
import numpy as np
import time, pickle, pathlib, json, os, sys, torch
from torch import nn
from torch.utils.data import Dataset, DataLoader
from metrics import hit_rate_at_k, ndcg_at_k

ROOT = pathlib.Path(__file__).resolve().parents[2]
DATA = ROOT / "data/ml1m_prepared"
REG  = ROOT / "model_registry"; REG.mkdir(exist_ok=True)
ART  = REG / "v_ncf"; ART.mkdir(exist_ok=True)

K       = int(os.getenv("K", "10"))
E       = int(os.getenv("NCF_EMB", "128"))
EPOCHS  = int(os.getenv("NCF_EPOCHS", "15"))
BATCH   = int(os.getenv("NCF_BATCH", "8192"))
LR      = float(os.getenv("NCF_LR", "0.001"))
NEG     = int(os.getenv("NCF_NEG", "8"))


# ---------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------
class PairDataset(Dataset):
    def __init__(self, df, n_items, neg=4, seed=42):
        self.pos = df[["user", "item"]].to_numpy()
        self.n_items = n_items
        self.neg = neg
        rng = np.random.RandomState(seed)
        negs = []
        for u, i in self.pos:
            for _ in range(neg):
                j = rng.randint(1, n_items + 1)
                negs.append([u, j, 0])
        self.data = np.concatenate([np.c_[self.pos, np.ones(len(self.pos))],
                                    np.array(negs)], axis=0)
        rng.shuffle(self.data)

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        u, i, y = self.data[idx]
        return int(u), int(i), float(y)


# ---------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------
class NCF(nn.Module):
    def __init__(self, n_users, n_items, emb=64):
        super().__init__()
        self.u = nn.Embedding(n_users + 1, emb)
        self.i = nn.Embedding(n_items + 1, emb)
        self.mlp = nn.Sequential(
            nn.Linear(emb * 2, 128), nn.ReLU(),
            nn.Linear(128, 64), nn.ReLU(),
            nn.Linear(64, 1), nn.Sigmoid()
        )

    def forward(self, u, i):
        x = torch.cat([self.u(u), self.i(i)], dim=1)
        return self.mlp(x).squeeze(-1)


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------
def main():
    t0 = time.time()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # --- Load data
    train = pd.read_csv(DATA / "train.csv")
    test  = pd.read_csv(DATA / "test.csv")

    for df in [train, test]:
        df["user"] = df["user"].astype(int)
        df["item"] = df["item"].astype(int)

    n_users = train["user"].max()
    n_items = train["item"].max()

    ds = PairDataset(train, n_items=n_items, neg=NEG)
    dl = DataLoader(ds, batch_size=BATCH, shuffle=True, num_workers=0)

    model = NCF(n_users, n_items, emb=E).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=LR)
    bce = nn.BCELoss()

    # --- Training
    for epoch in range(EPOCHS):
        model.train()
        running = 0.0
        for u, i, y in dl:
            u = u.to(device)
            i = i.to(device)
            y = y.to(device, dtype=torch.float32)
            p = model(u, i)
            loss = bce(p, y)
            opt.zero_grad()
            loss.backward()
            opt.step()
            running += loss.item()
        print(f"epoch {epoch+1}/{EPOCHS} loss={running/len(dl):.4f}")

    torch.save(model.state_dict(), ART / "model.pt")

    # --- Evaluate
    seen = train.groupby("user")["item"].apply(set).to_dict()
    model.eval()
    hr, ndcg = [], []

    with torch.no_grad():
        for _, row in test.iterrows():
            u = int(row["user"])
            true_i = int(row["item"])

            if u not in seen:
                continue

            cand = [j for j in range(1, n_items + 1) if j not in seen[u]]

            import random
            sample = random.sample(cand, min(1000, len(cand)))
            if true_i not in sample:
                sample[0] = true_i

            U = torch.tensor([u] * len(sample), dtype=torch.long, device=device)
            I = torch.tensor(sample, dtype=torch.long, device=device)
            scores = model(U, I).cpu().numpy()

            ranked = [x for _, x in sorted(zip(scores, sample), reverse=True)]
            rec = ranked[:K]

            hr.append(hit_rate_at_k(rec, true_i, K))
            ndcg.append(ndcg_at_k(rec, true_i, K))

    meta = {
        "model": "ncf",
        "emb": E,
        "epochs": EPOCHS,
        "batch": BATCH,
        "neg": NEG,
        "lr": LR,
        "k": K,
        "hr@k": float(np.mean(hr)),
        "ndcg@k": float(np.mean(ndcg)),
        "train_seconds": time.time() - t0,
        "model_size_bytes": (ART / "model.pt").stat().st_size
    }
    
    meta.update({
    "n_users": int(n_users),
    "n_items": int(n_items),
    "emb": int(E)
})


    (ART / "meta.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))


# ---------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------
if __name__ == "__main__":
    sys.path.append(str((ROOT / "experiments/ml1m_baselines").resolve()))
    main()
