import argparse, json, os
import numpy as np
import pandas as pd
from src.evaluation.evaluator import evaluate_topk

class PopularityModel:
    def __init__(self, train_df, user_col, item_col):
        self.item_scores = train_df.groupby(item_col).size().to_dict()
    def score_items(self, user_id, item_ids):
        return np.array([self.item_scores.get(i, 0.0) for i in item_ids], dtype=float)

def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", required=True)
    ap.add_argument("--test", required=True)
    ap.add_argument("--items", default=None)
    ap.add_argument("--user-col", default="user_id")
    ap.add_argument("--item-col", default="item_id")
    ap.add_argument("--negatives", type=int, default=99)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--baseline", choices=["popularity"], default="popularity")
    return ap.parse_args()

def main():
    args = parse_args()
    train = pd.read_csv(args.train)
    test  = pd.read_csv(args.test)
    items = pd.read_csv(args.items) if args.items else None
    model = PopularityModel(train, args.user_col, args.item_col)
    all_items = items[args.item_col].unique() if items is not None else None

    res = evaluate_topk(
        model=model,
        test_df=test,
        user_col=args.user_col, item_col=args.item_col,
        k=args.k, train_df=train, negatives_per_user=args.negatives,
        all_items=all_items
    )

    os.makedirs(args.outdir, exist_ok=True)
    out = {"users": res.users, f"HR@{args.k}": res.hr, f"NDCG@{args.k}": res.ndcg, "model": "baseline:popularity"}
    print(f"Users evaluated: {res.users}")
    print(f"HR@{args.k}:   {res.hr:.4f}")
    print(f"NDCG@{args.k}: {res.ndcg:.4f}")
    print("Model:        baseline:popularity")
    with open(os.path.join(args.outdir, "metrics.json"), "w") as f: json.dump(out, f, indent=2)
    pd.DataFrame([out]).to_csv(os.path.join(args.outdir, "metrics.csv"), index=False)

if __name__ == "__main__":
    main()
