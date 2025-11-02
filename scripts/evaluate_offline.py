# scripts/evaluate_offline_61.py
import argparse
import json
import os
from typing import List

import numpy as np
import pandas as pd


def hit_rate_at_k(predictions: pd.DataFrame, ground_truth: pd.DataFrame, k: int = 10) -> float:
    users = ground_truth['user_id'].unique()
    hits = 0
    for user in users:
        gt_items = set(ground_truth.loc[ground_truth.user_id == user, 'item_id'])
        user_preds = predictions.loc[predictions.user_id == user].sort_values('score', ascending=False)
        top_k = set(user_preds.head(k)['item_id'])
        if len(gt_items.intersection(top_k)) > 0:
            hits += 1
    return hits / max(1, len(users))


def ndcg_at_k(predictions: pd.DataFrame, ground_truth: pd.DataFrame, k: int = 10) -> float:
    users = ground_truth['user_id'].unique()
    ndcgs = []
    for user in users:
        gt_items = set(ground_truth.loc[ground_truth.user_id == user, 'item_id'])
        user_preds = predictions.loc[predictions.user_id == user].sort_values('score', ascending=False)
        top_k = user_preds.head(k)['item_id'].tolist()
        dcg = 0.0
        for i, item in enumerate(top_k, start=1):
            if item in gt_items:
                dcg += 1.0 / np.log2(i + 1)
        # ideal DCG: # of relevant items up to k (we treat each relevant item as gain=1)
        ideal_relevant_count = min(k, len(gt_items))
        idcg = sum(1.0 / np.log2(i + 1) for i in range(1, ideal_relevant_count + 1))
        ndcgs.append(dcg / idcg if idcg > 0 else 0.0)
    return float(np.mean(ndcgs))


def load_data(pred_path: str, truth_path: str) -> (pd.DataFrame, pd.DataFrame):
    preds = pd.read_csv(pred_path)
    truth = pd.read_csv(truth_path)
    required_pred_cols = {'user_id', 'item_id', 'score'}
    required_truth_cols = {'user_id', 'item_id'}  # label optional (we assume ground truth rows are positives)
    if not required_pred_cols.issubset(preds.columns):
        raise ValueError(f"Predictions file must contain columns: {required_pred_cols}")
    if not required_truth_cols.issubset(truth.columns):
        raise ValueError(f"Ground truth file must contain columns: {required_truth_cols}")
    return preds, truth


def evaluate(preds: pd.DataFrame, truth: pd.DataFrame, ks: List[int]) -> dict:
    results = {}
    for k in ks:
        hr = hit_rate_at_k(preds, truth, k)
        ndcg = ndcg_at_k(preds, truth, k)
        results[f"HR@{k}"] = hr
        results[f"NDCG@{k}"] = ndcg
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--preds", required=True, help="Path to predictions CSV")
    parser.add_argument("--truth", required=True, help="Path to ground-truth CSV")
    parser.add_argument("--ks", default="5,10,20", help="Comma-separated K values, e.g. 5,10,20")
    parser.add_argument("--out", default="metrics/offline_eval_61.json", help="Output JSON file")
    args = parser.parse_args()

    preds, truth = load_data(args.preds, args.truth)
    ks = [int(x) for x in args.ks.split(",")]

    results = evaluate(preds, truth, ks)

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(results, f, indent=2)

    print("Evaluation results:")
    for k in ks:
        print(f" HR@{k}: {results[f'HR@{k}']:.4f}\t NDCG@{k}: {results[f'NDCG@{k}']:.4f}")
    print(f"Saved results to {args.out}")


if __name__ == "__main__":
    main()
