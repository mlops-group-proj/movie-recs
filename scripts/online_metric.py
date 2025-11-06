"""
online_metric.py — Compute online KPI from Kafka topics.

Milestone 3 requirement: use reco_responses (and optionally watch)
to measure "proxy success" — did the user watch any recommended title
within N minutes after the recommendation?

Usage:
    python scripts/online_metric.py --bootstrap $KAFKA_BOOTSTRAP \
        --api-key $KAFKA_API_KEY --api-secret $KAFKA_API_SECRET \
        --team myteam --window-min 10 --limit 5000
"""

import os, json, argparse, time, io
import pandas as pd
from confluent_kafka import Consumer
from datetime import datetime, timedelta
from scipy import stats

# ---------------------------------------------------------------------
# CLI + Config
# ---------------------------------------------------------------------
def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bootstrap", required=True)
    ap.add_argument("--api-key", required=True)
    ap.add_argument("--api-secret", required=True)
    ap.add_argument("--team", required=True)
    ap.add_argument("--window-min", type=int, default=10)
    ap.add_argument("--limit", type=int, default=10000)
    return ap.parse_args()

# ---------------------------------------------------------------------
# Kafka utilities
# ---------------------------------------------------------------------
def consume_topic(bootstrap, key, secret, topic, limit):
    c = Consumer({
        "bootstrap.servers": bootstrap,
        "security.protocol": "SASL_SSL",
        "sasl.mechanisms": "PLAIN",
        "sasl.username": key,
        "sasl.password": secret,
        "group.id": f"{topic}-reader",
        "auto.offset.reset": "earliest",
    })
    c.subscribe([topic])
    msgs = []
    try:
        while len(msgs) < limit:
            m = c.poll(1.0)
            if m is None:
                continue
            if m.error():
                print("Kafka error:", m.error())
                continue
            msgs.append(json.loads(m.value().decode("utf-8")))
    finally:
        c.close()
    return pd.DataFrame(msgs)

# ---------------------------------------------------------------------
# KPI computation
# ---------------------------------------------------------------------
def compute_success(df_reco, df_watch, window_min=10):
    """Join recommendations with subsequent watches within a time window."""
    if df_reco.empty or df_watch.empty:
        return None

    df_reco["ts"] = pd.to_datetime(df_reco["ts"], unit="s")
    df_watch["ts"] = pd.to_datetime(df_watch["ts"], unit="s")

    results = []
    for model, group in df_reco.groupby("model", dropna=False):
        successes, total = 0, 0
        for _, row in group.iterrows():
            uid = row["user_id"]
            rec_movies = set(row.get("movie_ids", []))
            cutoff = row["ts"] + timedelta(minutes=window_min)
            watched = df_watch[
                (df_watch["user_id"] == uid)
                & (df_watch["ts"] <= cutoff)
                & (df_watch["movie_id"].isin(rec_movies))
            ]
            total += 1
            if len(watched) > 0:
                successes += 1
        rate = successes / total if total else 0
        ci_low, ci_high = proportion_ci(successes, total)
        results.append(
            {"model": model, "success_rate": rate,
             "n": total, "ci_low": ci_low, "ci_high": ci_high}
        )
    return pd.DataFrame(results)

def proportion_ci(successes, total, confidence=0.95):
    if total == 0:
        return (0, 0)
    phat = successes / total
    z = stats.norm.ppf(1 - (1 - confidence) / 2)
    half = z * (phat * (1 - phat) / total) ** 0.5
    return max(phat - half, 0), min(phat + half, 1)

# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------
def main():
    args = parse_args()
    team = args.team
    topics = {
        "reco": f"{team}.reco_responses",
        "watch": f"{team}.watch",
    }

    print(f"Consuming {args.limit} messages per topic…")
    df_reco = consume_topic(args.bootstrap, args.api_key, args.api_secret,
                            topics["reco"], args.limit)
    df_watch = consume_topic(args.bootstrap, args.api_key, args.api_secret,
                             topics["watch"], args.limit)

    if df_reco.empty:
        print("No reco_responses found.")
        return

    # Optional: add model name from payload meta
    if "model" not in df_reco.columns:
        df_reco["model"] = df_reco.get("model_name", "unknown")

    metrics = compute_success(df_reco, df_watch, args.window_min)
    if metrics is None:
        print("Not enough data for KPI computation.")
        return

    out_dir = "reports"
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_csv = os.path.join(out_dir, f"online_kpi_{ts}.csv")
    metrics.to_csv(out_csv, index=False)

    print("\n=== Online KPI Results ===")
    print(metrics.to_markdown(index=False))
    print(f"\nSaved KPI table → {out_csv}")

if __name__ == "__main__":
    main()
