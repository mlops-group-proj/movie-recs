"""
drift.py  —  Detect data distribution drift between training and test sets.
For Milestone 3–4: schema & drift quality gates, metrics export.

Usage:
    python drift.py --threshold 0.25  # returns exit code 1 if drift exceeds threshold
"""

import pandas as pd
import numpy as np
import json, pathlib, os, argparse, sys, logging
from scipy.stats import entropy, wasserstein_distance
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from prometheus_client import CollectorRegistry, Gauge, generate_latest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data/ml1m_prepared"
OUT  = ROOT / "model_registry" / "v_drift"
OUT.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# --------------------------------------------------------------------
# Metric helpers
# --------------------------------------------------------------------
def kl_divergence(p, q, eps=1e-10):
    p, q = np.array(p) + eps, np.array(q) + eps
    p, q = p / p.sum(), q / q.sum()
    return float(entropy(p, q))

def population_stability_index(train_col, test_col, bins=10):
    train_counts, bin_edges = np.histogram(train_col, bins=bins)
    test_counts, _ = np.histogram(test_col, bins=bin_edges)
    train_perc = train_counts / len(train_col)
    test_perc = test_counts / len(test_col)
    psi = np.sum((train_perc - test_perc) * np.log((train_perc + 1e-6)/(test_perc + 1e-6)))
    return float(psi)

def compare_distributions(train, test, col):
    """Return drift metrics for a given column."""
    common = sorted(set(train[col].unique()) | set(test[col].unique()))
    p = train[col].value_counts(normalize=True).reindex(common, fill_value=0)
    q = test[col].value_counts(normalize=True).reindex(common, fill_value=0)
    kl = kl_divergence(p.values, q.values)
    wd = wasserstein_distance(p.values, q.values)
    psi = population_stability_index(train[col], test[col])
    return {"kl_divergence": kl, "wasserstein": wd, "psi": psi}

def plot_distributions(train, test, col, path):
    plt.figure(figsize=(8,4))
    bins = np.linspace(min(train[col].min(), test[col].min()),
                       max(train[col].max(), test[col].max()), 40)
    plt.hist(train[col], bins=bins, alpha=0.5, label="train")
    plt.hist(test[col],  bins=bins, alpha=0.5, label="test")
    plt.title(f"{col} distribution (train vs test)")
    plt.xlabel(col); plt.ylabel("count"); plt.legend()
    plt.tight_layout(); plt.savefig(path); plt.close()

# --------------------------------------------------------------------
# Main drift routine
# --------------------------------------------------------------------
def run_drift(threshold=0.25, out_dir=OUT):
    train = pd.read_csv(DATA / "train.csv")
    test  = pd.read_csv(DATA / "test.csv")

    schema_ok = list(train.columns) == list(test.columns)
    missing_cols = set(train.columns) ^ set(test.columns)

    results = {"schema_match": schema_ok, "missing_cols": list(missing_cols)}
    metrics = {}

    for col in ["user", "item"]:
        metrics[col] = compare_distributions(train, test, col)
        plot_distributions(train, test, col, out_dir / f"{col}_drift.png")

    results["drift_metrics"] = metrics
    results["aggregate"] = {
        "avg_kl": np.mean([m["kl_divergence"] for m in metrics.values()]),
        "avg_wd": np.mean([m["wasserstein"] for m in metrics.values()]),
        "avg_psi": np.mean([m["psi"] for m in metrics.values()])
    }

    out_json = out_dir / "drift_metrics.json"
    out_plot = out_dir / "drift_plot.png"
    with open(out_json, "w") as f:
        json.dump(results, f, indent=2)

    # Summary bar
    plt.figure(figsize=(6,3))
    bars = list(metrics.keys())
    plt.bar(bars, [metrics[c]["psi"] for c in bars], color="tomato", alpha=0.7)
    plt.ylabel("Population Stability Index (PSI)")
    plt.title("Data Drift Summary (lower is better)")
    plt.tight_layout(); plt.savefig(out_plot); plt.close()

    # Prometheus export
    registry = CollectorRegistry()
    g = Gauge("data_drift_metric", "Drift metric values", ["feature","metric"], registry=registry)
    for feature, vals in metrics.items():
        for mname, val in vals.items():
            g.labels(feature, mname).set(val)
    metrics_txt = generate_latest(registry).decode("utf-8")
    (out_dir / "drift_metrics.prom").write_text(metrics_txt)

    drift_flag = any(v["psi"] > threshold for v in metrics.values())
    results["drift_detected"] = drift_flag
    return results, drift_flag, out_json

# --------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=float, default=0.25,
                        help="PSI threshold for drift flag")
    args = parser.parse_args()

    results, drift_flag, out_json = run_drift(threshold=args.threshold)
    logging.info(json.dumps(results, indent=2))
    logging.info(f"Saved drift metrics → {out_json}")

    if drift_flag:
        logging.error("🚨 Drift detected (PSI exceeded threshold)")
        sys.exit(1)
    else:
        logging.info("✅ No significant drift detected.")
        sys.exit(0)

if __name__ == "__main__":
    main()
