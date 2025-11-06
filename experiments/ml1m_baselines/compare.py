import json
import pandas as pd
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
REG  = ROOT / "model_registry"
REPORTS = ROOT / "reports"
REPORTS.mkdir(exist_ok=True)


def load_meta(path):
    """Load each model's meta.json with error handling."""
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️  Skipping {path}: {e}")
        return None


def load_latency():
    """Load latency benchmark results if available."""
    lat_path = REPORTS / "benchmark_latency.json"
    if lat_path.exists():
        try:
            with open(lat_path) as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️  Could not read latency file: {e}")
    return {}


def main():
    rows = []

    # Load model metrics
    for subdir in REG.iterdir():
        meta_path = subdir / "meta.json"
        if meta_path.exists():
            meta = load_meta(meta_path)
            if not meta:
                continue
            row = {
                "model": meta.get("model", subdir.name),
                "k": meta.get("k"),
                "HR@K": meta.get("hr@k"),
                "NDCG@K": meta.get("ndcg@k"),
                "train_seconds": meta.get("train_seconds"),
                "model_size_MB": round(meta.get("model_size_bytes", 0) / 1e6, 2),
            }
            rows.append(row)

    if not rows:
        print("❌ No meta.json files found in model_registry/")
        return

    df = pd.DataFrame(rows)

    # Load latency results (if available)
    latency = load_latency()
    if latency:
        for m, r in latency.items():
            if m in df["model"].values:
                df.loc[df["model"] == m, "p50_ms"] = r.get("p50_ms")
                df.loc[df["model"] == m, "p95_ms"] = r.get("p95_ms")

    # Sort by NDCG@K
    df = df.sort_values("NDCG@K", ascending=False)

    # Print to console
    print("\n=== Model Comparison (sorted by NDCG@K) ===\n")
    print(df.to_string(index=False, justify="center", col_space=12))

    # Save to CSV
    out_csv = REPORTS / "model_comparison.csv"
    df.to_csv(out_csv, index=False)
    print(f"\n✅ Saved CSV summary to {out_csv.resolve()}")

    # Save to Markdown
    out_md = REPORTS / "model_comparison.md"
    md = [
        "# 📊 Model Comparison Summary\n",
        "This table combines model accuracy, training cost, and inference latency.\n",
        "Generated automatically by `compare.py`.\n",
        "",
        df.to_markdown(index=False),
    ]
    out_md.write_text("\n".join(md))
    print(f"✅ Saved Markdown summary to {out_md.resolve()}\n")


if __name__ == "__main__":
    main()
