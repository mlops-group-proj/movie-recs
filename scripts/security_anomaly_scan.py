#!/usr/bin/env python3
"""
Lightweight security and abuse checks over watch/rate event exports.

Input: JSONL with fields
{
  "ts": 1731465600000,
  "user_id": 42,
  "movie_id": 123,
  "rating": 5            # optional (for rate topic)
}

Signals:
- Event volume by user: flag users with count > mean + 3*std (spam/poison risk).
- Schema issues: count records missing required fields.
"""
import argparse
import json
from collections import Counter
from pathlib import Path
from statistics import mean, pstdev
from typing import Iterable, Dict, Any


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


def scan(path: Path) -> Dict[str, Any]:
    counts = Counter()
    schema_errors = 0

    for rec in load_records(path):
        if "user_id" not in rec or "movie_id" not in rec:
            schema_errors += 1
            continue
        counts[rec["user_id"]] += 1

    if not counts:
        return {"total_events": 0, "schema_errors": schema_errors, "flagged_users": []}

    vals = list(counts.values())
    avg = mean(vals)
    sd = pstdev(vals) if len(vals) > 1 else 0
    threshold = avg + 3 * sd
    flagged = [{"user_id": uid, "count": cnt} for uid, cnt in counts.items() if cnt > threshold]

    return {
        "total_events": sum(vals),
        "unique_users": len(counts),
        "schema_errors": schema_errors,
        "mean_events_per_user": avg,
        "std_events_per_user": sd,
        "threshold": threshold,
        "flagged_users": flagged,
    }


def main():
    parser = argparse.ArgumentParser(description="Detect rating spam / schema issues from event exports.")
    parser.add_argument("--events", type=Path, required=True, help="Path to watch/rate JSONL export.")
    parser.add_argument("--out", type=Path, help="Optional path to write JSON summary.")
    args = parser.parse_args()

    summary = scan(args.events)
    print(json.dumps(summary, indent=2))

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
