#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Prepare/clean the dataset and export train-ready files.
"""

import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd


def read_csv_safe(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {p}")
    return pd.read_csv(p, engine="python")


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    lower = {c.lower(): c for c in df.columns}
    u = lower.get("userid") or lower.get("user_id")
    i = lower.get("movieid") or lower.get("item_id")
    r = lower.get("rating") or lower.get("score")
    t = lower.get("timestamp")

    df = df[[u, i, r] + ([t] if t else [])].copy()
    df.columns = ["user_id", "item_id", "rating"] + (["timestamp"] if t else [])
    return df


def clean_ratings(df: pd.DataFrame) -> pd.DataFrame:
    df = normalize_columns(df)
    df.dropna(subset=["user_id", "item_id", "rating"], inplace=True)
    df["user_id"] = df["user_id"].astype(int)
    df["item_id"] = df["item_id"].astype(int)
    df["rating"] = df["rating"].astype(float)
    if "timestamp" not in df:
        df["timestamp"] = range(len(df))
    return df


def to_implicit(df: pd.DataFrame, threshold: float = 4.0) -> pd.DataFrame:
    df = df.copy()
    df["weight"] = (df["rating"] >= threshold).astype(float)
    return df[df["weight"] > 0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ratings", required=True)
    ap.add_argument("--outdir", default="data/processed")
    ap.add_argument("--implicit_threshold", type=float, default=4.0)
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    df = read_csv_safe(args.ratings)
    df = clean_ratings(df)

    implicit = to_implicit(df, args.implicit_threshold)
    implicit.to_csv(outdir / "ratings_implicit.csv", index=False)
    df.to_csv(outdir / "ratings_explicit.csv", index=False)

    print("[✅] Data prepared successfully!")
    print(f"Saved to: {outdir}")


if __name__ == "__main__":
    main()
