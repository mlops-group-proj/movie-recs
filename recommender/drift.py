"""
drift.py — Detect data distribution drift between training and test sets.
Extended version with PSI, KL divergence, missing values, and outlier detection.

Outputs:
    model_registry/v_drift/drift_metrics.json
    model_registry/v_drift/drift_plot.png
    model_registry/v_drift/drift_metrics.prom
"""

import pandas as pd
import numpy as np
import json, pathlib
from scipy.stats import entropy, wasserstein_distance, zscore
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from prometheus_client import CollectorRegistry, Gauge, generate_latest, REGISTRY
import os
import logging


# --------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------
ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "model_registry" / "v_drift"
FALLBACK_OUT = pathlib.Path("/tmp/v_drift")

# Try preferred output path first
try:
    DEFAULT_OUT.mkdir(parents=True, exist_ok=True)
    # Test write permission
    testfile = DEFAULT_OUT / ".write_test"
    with open(testfile, "w") as f:
        f.write("ok")
    testfile.unlink()
    OUT = DEFAULT_OUT
    logging.info(f"✅ Drift output directory set to {OUT}")
except Exception as e:
    logging.warning(f"⚠️ Drift output not writable at {DEFAULT_OUT} ({e}). Using fallback {FALLBACK_OUT}")
    FALLBACK_OUT.mkdir(parents=True, exist_ok=True)
    OUT = FALLBACK_OUT

DATA = ROOT / "data/ml1m_prepared"

# --------------------------------------------------------------------
# Prometheus: expose drift output path
# --------------------------------------------------------------------
try:
    if "drift_output_path_info" not in REGISTRY._names_to_collectors:
        drift_path_metric = Gauge(
            "drift_output_path_info",
            "Path used to store drift visualizations and metrics",
            ["path"]
        )
    else:
        drift_path_metric = REGISTRY._names_to_collectors["drift_output_path_info"]
    drift_path_metric.labels(path=str(OUT)).set(1)
    logging.info(f"📊 Exposed Prometheus metric for drift path: {OUT}")
except Exception as e:
    logging.warning(f"⚠️ Could not register drift path metric: {e}")

# --------------------------------------------------------------------
# Cleanup: keep only the most recent N drift runs
# --------------------------------------------------------------------
MAX_DRIFT_FILES = 5  # change if you want to keep more or fewer runs

try:
    drift_files = sorted(
        [f for f in OUT.glob("*.png") if f.is_file()],
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    if len(drift_files) > MAX_DRIFT_FILES:
        for f in drift_files[MAX_DRIFT_FILES:]:
            f.unlink()
            logging.info(f"🧹 Removed old drift plot: {f.name}")
except Exception as e:
    logging.warning(f"⚠️ Drift cleanup failed: {e}")


# --------------------------------------------------------------------
# Metric helpers
# --------------------------------------------------------------------
def kl_divergence(p, q, eps=1e-10):
    """Kullback–Leibler divergence between discrete distributions."""
    p, q = np.array(p) + eps, np.array(q) + eps
    p, q = p / p.sum(), q / q.sum()
    return float(entropy(p, q))

def population_stability_index(train_col, test_col, bins=10):
    """Population Stability Index."""
    train_counts, bin_edges = np.histogram(train_col, bins=bins)
    test_counts, _ = np.histogram(test_col, bins=bin_edges)
    train_perc = train_counts / len(train_col)
    test_perc = test_counts / len(test_col)
    psi = np.sum((train_perc - test_perc) * np.log((train_perc + 1e-6)/(test_perc + 1e-6)))
    return float(psi)

def missing_value_ratio(series):
    """Fraction of missing values."""
    return float(series.isna().mean())

def outlier_fraction(series, threshold=3.0):
    """Fraction of samples whose z-score exceeds the threshold."""
    if not np.issubdtype(series.dtype, np.number):
        return 0.0
    z = np.abs(zscore(series, nan_policy="omit"))
    return float(np.nanmean(z > threshold))

def compare_distributions(train, test, col):
    """Return drift metrics for a given column."""
    common = sorted(set(train[col].dropna().unique()) | set(test[col].dropna().unique()))
    p = train[col].value_counts(normalize=True).reindex(common, fill_value=0)
    q = test[col].value_counts(normalize=True).reindex(common, fill_value=0)
    kl = kl_divergence(p.values, q.values)
    wd = wasserstein_distance(p.values, q.values)
    psi = population_stability_index(train[col], test[col])
    miss = missing_value_ratio(test[col])
    outliers = outlier_fraction(test[col])
    return {"kl_divergence": kl, "wasserstein": wd, "psi": psi,
            "missing_ratio": miss, "outlier_fraction": outliers}

def plot_distributions(train, test, col, path):
    plt.figure(figsize=(8, 4))
    bins = np.linspace(min(train[col].min(), test[col].min()),
                       max(train[col].max(), test[col].max()), 40)
    plt.hist(train[col], bins=bins, alpha=0.5, label="train")
    plt.hist(test[col], bins=bins, alpha=0.5, label="test")
    plt.title(f"{col} distribution (train vs test)")
    plt.xlabel(col); plt.ylabel("count"); plt.legend()
    plt.tight_layout(); plt.savefig(path); plt.close()

# --------------------------------------------------------------------
# Main drift routine
# --------------------------------------------------------------------
def run_drift(threshold=0.25, out_dir=OUT):
    train = pd.read_csv(DATA / "train.csv")
    test = pd.read_csv(DATA / "test.csv")

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
        "avg_psi": np.mean([m["psi"] for m in metrics.values()]),
        "avg_missing": np.mean([m["missing_ratio"] for m in metrics.values()]),
        "avg_outliers": np.mean([m["outlier_fraction"] for m in metrics.values()]),
    }

    # Save JSON summary
    out_json = out_dir / "drift_metrics.json"
    with open(out_json, "w") as f:
        json.dump(results, f, indent=2)

    # Summary plot
    plt.figure(figsize=(6, 3))
    bars = list(metrics.keys())
    plt.bar(bars, [metrics[c]["psi"] for c in bars], color="tomato", alpha=0.7)
    plt.ylabel("Population Stability Index (PSI)")
    plt.title("Data Drift Summary (lower is better)")
    plt.tight_layout(); plt.savefig(out_dir / "drift_plot.png"); plt.close()

    # ----------------------------------------------------------------
    # Prometheus metrics export
    # ----------------------------------------------------------------
    registry = CollectorRegistry()
    gauges = {
        "data_drift_psi": Gauge("data_drift_psi", "Population Stability Index", ["feature"], registry=registry),
        "data_drift_kl": Gauge("data_drift_kl", "Kullback-Leibler Divergence", ["feature"], registry=registry),
        "data_missing_ratio": Gauge("data_missing_ratio", "Fraction of missing values", ["feature"], registry=registry),
        "data_outlier_fraction": Gauge("data_outlier_fraction", "Fraction of outliers (z>3)", ["feature"], registry=registry),
    }

    for feature, vals in metrics.items():
        gauges["data_drift_psi"].labels(feature=feature).set(vals["psi"])
        gauges["data_drift_kl"].labels(feature=feature).set(vals["kl_divergence"])
        gauges["data_missing_ratio"].labels(feature=feature).set(vals["missing_ratio"])
        gauges["data_outlier_fraction"].labels(feature=feature).set(vals["outlier_fraction"])

    (out_dir / "drift_metrics.prom").write_text(generate_latest(registry).decode("utf-8"))

    drift_flag = any(v["psi"] > threshold for v in metrics.values())
    results["drift_detected"] = drift_flag
    return results, drift_flag, out_json
