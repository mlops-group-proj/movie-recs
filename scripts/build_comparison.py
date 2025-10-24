from __future__ import annotations
from pathlib import Path
import pandas as pd

def main():
    Path("reports").mkdir(exist_ok=True, parents=True)
    offline = pd.read_csv("reports/offline_metrics.csv")            
    train = pd.read_csv("reports/benchmark_train.csv")              
    infer = pd.read_csv("reports/benchmark_infer.csv")              

    offline = offline.rename(columns={"K":"k"})
    df = offline.merge(train, on=["model","version"], how="left") \
                .merge(infer, on=["model","version","k"], how="left")

    order = ["popularity","itemcf","als"]
    df["order"] = df["model"].apply(lambda m: order.index(m) if m in order else 99)
    df = df.sort_values(["order"]).drop(columns=["order"])

    out = df.copy()
    for c in ["HR@K","NDCG@K"]:
        out[c] = out[c].astype(float).round(4)
    for c in ["train_seconds","p50_ms","p95_ms"]:
        if c in out: out[c] = out[c].astype(float).round(2)

    out_csv = "reports/model_comparison.csv"
    out_md  = "reports/model_comparison.md"

    out.to_csv(out_csv, index=False)

    md = ["# Model Comparison",
          "",
          "Combined quality and performance at top-K.",
          "",
          out.to_markdown(index=False)]
    Path(out_md).write_text("\n".join(md), encoding="utf-8")

    print(f"[OK] wrote {out_csv} and {out_md}")
    print(out)

if __name__ == "__main__":
    main()
