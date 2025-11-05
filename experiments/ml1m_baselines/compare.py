import json
import pandas as pd
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
REG  = ROOT / "model_registry"
REPORTS = ROOT / "reports"
REPORTS.mkdir(exist_ok=True)

def load_meta(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️  Skipping {path}: {e}")
        return None

def main():
    rows = []
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
                "model_size_MB": round(meta.get("model_size_bytes", 0) / 1e6, 2)
            }
            rows.append(row)

    if not rows:
        print("❌ No meta.json files found in model_registry/")
        return

    df = pd.DataFrame(rows)
    df = df.sort_values("NDCG@K", ascending=False)
    print("\n=== Model Comparison (sorted by NDCG@K) ===\n")
    print(df.to_string(index=False, justify="center", col_space=12))

    out_csv = REPORTS / "model_comparison.csv"
    df.to_csv(out_csv, index=False)
    print(f"\n✅ Saved summary to {out_csv.resolve()}")

if __name__ == "__main__":
    main()
