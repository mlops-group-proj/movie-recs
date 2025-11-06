import time
import json
import pickle
import pathlib
import random
import numpy as np
from scipy.sparse import csr_matrix
import torch

ROOT = pathlib.Path(__file__).resolve().parents[2]
REG  = ROOT / "model_registry"
OUT  = ROOT / "reports"
OUT.mkdir(exist_ok=True)


def benchmark_popularity(n=2000, k=10):
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
    obj = pickle.load(open(REG / "v_itemcf" / "sims.pkl", "rb"))
    sims, iid, items = obj["sims"], obj["iid"], obj["items"]
    inv_iid = {v: k for k, v in iid.items()}
    users = list(range(1, 500))
    lat = []
    UI = csr_matrix((1, len(iid)))
    for _ in range(n):
        u = random.choice(users)
        t0 = time.perf_counter()
        _ = UI.dot(sims)
        lat.append((time.perf_counter() - t0) * 1000)
    return {"p50_ms": np.percentile(lat, 50), "p95_ms": np.percentile(lat, 95)}


def benchmark_als(n=1000, k=10):
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
    ART = REG / "v_ncf"
    model = torch.load(ART / "model.pt", map_location="cpu")
    meta = json.load(open(ART / "meta.json"))
    n_users, n_items = meta.get("n_users", 6040), meta.get("n_items", 3703)

    device = torch.device("cpu")
    u = torch.randint(0, n_users, (n,))
    i = torch.randint(0, n_items, (n,))
    model.eval()

    lat = []
    with torch.no_grad():
        for uu, ii in zip(u, i):
            t0 = time.perf_counter()
            _ = model(torch.tensor([uu]), torch.tensor([ii]))
            lat.append((time.perf_counter() - t0) * 1000)
    return {"p50_ms": np.percentile(lat, 50), "p95_ms": np.percentile(lat, 95)}


def main():
    results = {
        "popularity": benchmark_popularity(),
        "itemcf": benchmark_itemcf(),
        "als": benchmark_als(),
        "ncf": benchmark_ncf(),
    }

    print("\n=== Inference Latency Benchmarks (ms) ===\n")
    for m, r in results.items():
        print(f"{m:12s}  p50={r['p50_ms']:.3f} ms  p95={r['p95_ms']:.3f} ms")

    (OUT / "benchmark_latency.json").write_text(json.dumps(results, indent=2))
    print(f"\n✅ Saved latency results to {OUT / 'benchmark_latency.json'}")


if __name__ == "__main__":
    main()
