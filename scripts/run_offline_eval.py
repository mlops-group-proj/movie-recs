import argparse
import pandas as pd
from evaluation.evaluator import evaluate_topk

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", required=True)
    ap.add_argument("--test", required=True)
    ap.add_argument("--items")
    ap.add_argument("--user-col", default="user_id")
    ap.add_argument("--item-col", default="item_id")
    ap.add_argument("--item-id-col", default=None)
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--negatives", type=int, default=99)
    args = ap.parse_args()

    train = pd.read_csv(args.train)
    test  = pd.read_csv(args.test)
    items = pd.read_csv(args.items) if args.items else None

    class RandomBaseline:
        def score_items(self, user_id, item_ids):
            return pd.Series(item_ids).rank(method="first").values

    res = evaluate_topk(
        RandomBaseline(),
        test_df=test,
        user_col=args.user_col,
        item_col=args.item_col,
        k=args.k,
        train_df=train,
        negatives_per_user=args.negatives,
        items_df=items,
        item_id_col=args.item_id_col,
    )
    print(f"Users: {res.users}  K: {res.k}  HR@K: {res.hr:.4f}  NDCG@K: {res.ndcg:.4f}")

if __name__ == "__main__":
    main()