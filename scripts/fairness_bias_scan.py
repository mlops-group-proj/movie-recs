#!/usr/bin/env python3
"""
Compute simple fairness indicators from reco_responses logs.

Expected input: JSONL records with at least
{
  "ts": 1731465600000,   # ms since epoch
  "user_id": 42,
  "movie_ids": [1,2,3],
  "model_version": "v0.3",
  "variant": "A"          # optional (A/B tag)
}

Metrics:
- Top popularity share (exposure %) for the top_p_pct most-seen items.
- Tail exposure share (1 - top_pop_share).
- Gini coefficient over item exposure counts.
- Segment disparity on exposure between variant A/B or even/odd user ids.
"""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Dict, Any


def gini(values: Iterable[int]) -> float:
    vals = sorted([v for v in values if v >= 0])
    if not vals:
        return 0.0
    n = len(vals)
    cum = 0
    for i, v in enumerate(vals, start=1):
        cum += i * v
    return (2 * cum) / (n * sum(vals)) - (n + 1) / n


def load_records(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def compute_metrics(path: Path, top_p_pct: float = 0.1) -> Dict[str, Any]:
    exposures = Counter()
    segment_counts = defaultdict(int)
    segment_exposures = defaultdict(int)
    total_recs = 0

    for rec in load_records(path):
        movies = rec.get("movie_ids") or []
        user_id = rec.get("user_id")
        variant = rec.get("variant")
        seg = variant if variant else ("even" if user_id and user_id % 2 == 0 else "odd")

        for m in movies:
            exposures[m] += 1
            segment_exposures[seg] += 1
        segment_counts[seg] += 1
        total_recs += len(movies)

    if not exposures:
        return {
            "total_recommendations": 0,
            "unique_items": 0,
            "top_pop_share": 0.0,
            "tail_share": 0.0,
            "gini_exposure": 0.0,
            "segment_exposure_share": {},
        }

    sorted_counts = sorted(exposures.items(), key=lambda kv: kv[1], reverse=True)
    top_n = max(1, int(len(sorted_counts) * top_p_pct))
    top_exposure = sum(cnt for _, cnt in sorted_counts[:top_n])
    total_exposure = sum(exposures.values())

    segment_share = {}
    for seg, cnt in segment_exposures.items():
        segment_share[seg] = cnt / total_exposure

    return {
        "total_recommendations": total_recs,
        "unique_items": len(exposures),
        "top_pop_share": top_exposure / total_exposure,
        "tail_share": 1 - (top_exposure / total_exposure),
        "gini_exposure": gini(exposures.values()),
        "segment_exposure_share": segment_share,
    }


def main():
    parser = argparse.ArgumentParser(description="Fairness metrics over reco_responses logs.")
    parser.add_argument("--responses", type=Path, required=True, help="Path to reco_responses JSONL export.")
    parser.add_argument("--top-percent", type=float, default=0.1, help="Percent of most popular items to treat as head (0-1).")
    parser.add_argument("--out", type=Path, help="Optional path to write JSON summary.")
    args = parser.parse_args()

    metrics = compute_metrics(args.responses, args.top_percent)
    print(json.dumps(metrics, indent=2))

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
