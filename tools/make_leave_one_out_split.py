# tools/make_leave_one_out_split.py
import argparse, pandas as pd

def main(args):
    df = pd.read_csv(args.input)
    # required cols: user_id, item_id, rating, timestamp
    for c in ["user_id","item_id","rating","timestamp"]:
        if c not in df.columns:
            raise ValueError(f"Missing column {c} in {args.input}")

    # sort per-user by time
    df = df.sort_values(["user_id","timestamp"])

    # global item counts
    global_counts = df["item_id"].value_counts()

    train_rows = []
    test_rows  = []

    # per user, pick the latest interaction whose item appears >=2 times globally
    # so that after moving one to test, the item still exists in train (seen by someone else)
    for uid, g in df.groupby("user_id", sort=False):
        g = g.copy()
        # try from latest to earliest
        picked_idx = None
        for idx in reversed(g.index.tolist()):
            item = g.loc[idx, "item_id"]
            if global_counts.get(item, 0) >= 2:
                picked_idx = idx
                break
        if picked_idx is None:
            # no safe item to move: drop this user from eval (all items are singletons)
            train_rows.append(g)
            continue
        # assign test row
        test_rows.append(g.loc[[picked_idx]])
        # remainder goes to train
        train_rows.append(g.drop(index=[picked_idx]))

    train = pd.concat(train_rows, axis=0, ignore_index=True)
    test  = pd.concat(test_rows,  axis=0, ignore_index=True)

    # final sanity: no test item should be cold-start in train
    seen = set(train["item_id"].unique().tolist())
    cold = test[~test["item_id"].isin(seen)]
    if not cold.empty:
        raise RuntimeError(f"Still found cold-start test items: {cold['item_id'].unique().tolist()}")

    train.to_csv(args.train_out, index=False)
    test.to_csv(args.test_out, index=False)
    print(f"Wrote:\n  train -> {args.train_out} ({train.shape[0]} rows)\n  test  -> {args.test_out} ({test.shape[0]} rows)\n  users in test: {test['user_id'].nunique()}")
    # optional: show a quick preview
    print("Example test rows:")
    print(test.head(5))

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--input",    required=True, help="CSV with user_id,item_id,rating,timestamp for ALL interactions")
    ap.add_argument("--train-out",required=True)
    ap.add_argument("--test-out", required=True)
    args = ap.parse_args()
    main(args)
