import time
import json
import pickle
import pathlib
import random
import numpy as np
from scipy.sparse import csr_matrix
import torch

# ---------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------
ROOT = pathlib.Path(__file__).resolve().parents[2]
REG  = ROOT / "model_registry"
OUT  = ROOT / "reports"
OUT.mkdir(exist_ok=True)

# ---------------------------------------------------------------------
# Benchmark helpers
# ---------------------------------------------------------------------
def benchmark_popularity(n=2000, k=10):
    """Measure latency for Popularity recommender (constant-time lookup)."""
    pop = pickle.load(open(REG / "v_popularity" / "model.pkl", "rb"))
    users = range(1, 6041)
    lat = []
    for _ in range(n):
        _ = random.choice(users)
        t0 = time.perf_counter()
        _ = pop[:k]
        lat.append((time.perf_counter() - t0) * 1000)
    return {"p50_ms": np.percentile(lat, 50), "p95_ms": np.percentile(lat, 95)}


def benchmark_itemcf(n=500, k=10):
    """Measure latency for Item-Item CF (sparse matrix cosine sim)."""
    obj = pickle.load(open(REG / "v_itemcf" / "sims.pkl", "rb"))
    sims, iid, items = obj["sims"], obj["iid"], obj["items"]
    UI = csr_matrix((1, len(iid)))
    lat = []
    for _ in range(n):
        t0 = time.perf_counter()
        _ = UI.dot(sims)  # simulate inference
        lat.append((time.perf_counter() - t0) * 1000)
    return {"p50_ms": np.percentile(lat, 50), "p95_ms": np.percentile(lat, 95)}


def benchmark_als(n=1000, k=10):
    """Measure latency for ALS implicit model recommendations."""
    obj = pickle.load(open(REG / "v_als" / "model.pkl", "rb"))
    model, uid, iid, items = obj["model"], obj["uid"], obj["iid"], obj["items"]
    users = list(uid.keys())
    UI = csr_matrix((1, len(iid)))
    lat = []
    for _ in range(n):
        u = random.choice(users)
        t0 = time.perf_counter()
        _ = model.recommend(uid[u], UI[0], N=k)
        lat.append((time.perf_counter() - t0) * 1000)
    return {"p50_ms": np.percentile(lat, 50), "p95_ms": np.percentile(lat, 95)}


def benchmark_ncf(n=500, k=10):
    """Measure latency for Neural Collaborative Filtering (PyTorch)."""
    from torch import nn

    # Define same architecture used during training
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

    ART = REG / "v_ncf"
    meta = json.load(open(ART / "meta.json"))
    E = int(meta.get("emb", 64))
    n_users = int(meta.get("n_users", 6040))
    n_items = int(meta.get("n_items", 3703))

    device = torch.device("cpu")
    model = NCF(n_users, n_items, emb=E).to(device)
    state_dict = torch.load(ART / "model.pt", map_location=device)
    model.load_state_dict(state_dict, strict=True)
    model.eval()

    lat = []
    with torch.no_grad():
        for _ in range(n):
            u = torch.randint(0, n_users, (1,), device=device)
            i = torch.randint(0, n_items, (1,), device=device)
            t0 = time.perf_counter()
            _ = model(u, i)
            lat.append((time.perf_counter() - t0) * 1000)

    return {"p50_ms": np.percentile(lat, 50), "p95_ms": np.percentile(lat, 95)}


# ---------------------------------------------------------------------
# Main benchmarking routine
# ---------------------------------------------------------------------
def main():
    print("\n=== Inference Latency Benchmarks (K=10) ===\n")
    results = {
        "popularity": benchmark_popularity(),
        "itemcf": benchmark_itemcf(),
        "als": benchmark_als(),
        "ncf": benchmark_ncf(),
    }

    for name, r in results.items():
        print(f"{name:12s}  p50={r['p50_ms']:.3f} ms   p95={r['p95_ms']:.3f} ms")

    out_path = OUT / "benchmark_latency.json"
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\n*  Saved latency results to {out_path.resolve()}\n")


# ---------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------
if __name__ == "__main__":
    main()
