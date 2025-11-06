"""
drift.py  —  Detect data distribution drift between training and test sets.
For Milestone 3: schema & drift quality gates.

Usage:
    python drift.py  # (reads data/ml1m_prepared/train.csv and test.csv)

Outputs:
    model_registry/v_drift/drift_metrics.json
    model_registry/v_drift/drift_plot.png
"""

import pandas as pd
import numpy as np
import json, pathlib, os
from scipy.stats import entropy, wasserstein_distance
# --- Ensure headless plotting works in CI (no GUI required) ---
import matplotlib
matplotlib.use("Agg")  # must be called before importing pyplot
import matplotlib.pyplot as plt

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data/ml1m_prepared"
OUT  = ROOT / "model_registry" / "v_drift"
OUT.mkdir(parents=True, exist_ok=True)

def kl_divergence(p, q, eps=1e-10):
    p, q = np.array(p) + eps, np.array(q) + eps
    p, q = p / p.sum(), q / q.sum()
    return float(entropy(p, q))

def compare_distributions(train, test, col):
    """Return histogram-based drift metrics for a given column."""
    common = sorted(set(train[col].unique()) | set(test[col].unique()))
    p = train[col].value_counts(normalize=True).reindex(common, fill_value=0)
    q = test[col].value_counts(normalize=True).reindex(common, fill_value=0)
    kl = kl_divergence(p.values, q.values)
    wd = wasserstein_distance(p.values, q.values)
    return {"kl_divergence": kl, "wasserstein": wd,
            "n_train": len(train), "n_test": len(test)}

def plot_distributions(train, test, col, path):
    plt.figure(figsize=(8,4))
    bins = np.linspace(min(train[col].min(), test[col].min()),
                       max(train[col].max(), test[col].max()), 40)
    plt.hist(train[col], bins=bins, alpha=0.5, label="train")
    plt.hist(test[col],  bins=bins, alpha=0.5, label="test")
    plt.title(f"{col} distribution (train vs test)")
    plt.xlabel(col); plt.ylabel("count"); plt.legend()
    plt.tight_layout(); plt.savefig(path); plt.close()

def main():
    train = pd.read_csv(DATA / "train.csv")
    test  = pd.read_csv(DATA / "test.csv")

    # ---- Schema validation (basic) ----
    schema_ok = list(train.columns) == list(test.columns)
    missing_cols = set(train.columns) ^ set(test.columns)

    results = {"schema_match": schema_ok, "missing_cols": list(missing_cols)}

    # ---- Drift for key columns ----
    metrics = {}
    for col in ["user", "item"]:
        metrics[col] = compare_distributions(train, test, col)
        plot_distributions(train, test, col, OUT / f"{col}_drift.png")

    results["drift_metrics"] = metrics

    # ---- Aggregate summary ----
    avg_kl = np.mean([m["kl_divergence"] for m in metrics.values()])
    avg_wd = np.mean([m["wasserstein"] for m in metrics.values()])
    results["aggregate"] = {"avg_kl": avg_kl, "avg_wasserstein": avg_wd}

    # ---- Save ----
    out_json = OUT / "drift_metrics.json"
    out_plot = OUT / "drift_plot.png"

    with open(out_json, "w") as f:
        json.dump(results, f, indent=2)

    # Combined summary plot
    plt.figure(figsize=(6,3))
    bars = ["user","item"]
    plt.bar(bars, [metrics[c]["kl_divergence"] for c in bars], alpha=0.7)
    plt.ylabel("KL divergence")
    plt.title("Drift summary (lower is better)")
    plt.tight_layout(); plt.savefig(out_plot); plt.close()

    print(json.dumps(results, indent=2))
    print(f"\nSaved drift metrics → {out_json}")
    print(f"Saved drift plot    → {out_plot}")

if __name__ == "__main__":
    main()
