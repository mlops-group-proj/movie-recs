#!/usr/bin/env python3
"""
Push fairness and security summary metrics to Prometheus Pushgateway.

Reads the JSON summaries produced by:
  - scripts/fairness_bias_scan.py (fairness)
  - scripts/security_anomaly_scan.py (security)

and pushes gauges to a Pushgateway so Grafana can plot them.

Environment:
  PUSHGATEWAY_URL (default: http://localhost:9091)
  JOB_NAME (default: reco_responsible_metrics)
"""
import json
import os
import sys
from pathlib import Path
from urllib import request


def load_json(path: Path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def build_payload(fair: dict, sec: dict) -> str:
    lines = []
    if fair:
        lines.append(f"reco_tail_share {fair.get('tail_share', 0)}")
        lines.append(f"reco_top_pop_share {fair.get('top_pop_share', 0)}")
        lines.append(f"reco_exposure_gini {fair.get('gini_exposure', 0)}")
        lines.append(f"reco_unique_items {fair.get('unique_items', 0)}")
    if sec:
        flagged = len(sec.get("flagged_users", []))
        lines.append(f"reco_security_flagged_users {flagged}")
        lines.append(f"reco_security_schema_errors {sec.get('schema_errors', 0)}")
        lines.append(f"reco_security_mean_events_per_user {sec.get('mean_events_per_user', 0)}")
        lines.append(f"reco_security_threshold {sec.get('threshold', 0)}")
    return "\n".join(lines) + "\n"


def push(payload: str, push_url: str):
    req = request.Request(push_url, data=payload.encode(), method="POST")
    req.add_header("Content-Type", "text/plain")
    with request.urlopen(req, timeout=5) as resp:
        return resp.read()


def main():
    fair_path = Path("deliverables/evidence/fairness/reco_bias.json")
    sec_path = Path("deliverables/evidence/security/rate_anomalies.json")

    fair = load_json(fair_path)
    sec = load_json(sec_path)

    payload = build_payload(fair, sec)
    if not payload.strip():
        print("No metrics to push (missing or empty JSON).", file=sys.stderr)
        sys.exit(1)

    pushgateway = os.getenv("PUSHGATEWAY_URL", "http://localhost:9091")
    job = os.getenv("JOB_NAME", "reco_responsible_metrics")
    push_url = f"{pushgateway}/metrics/job/{job}"

    try:
        push(payload, push_url)
        print(f"Pushed metrics to {push_url}")
        print(payload)
    except Exception as e:
        print(f"Failed to push metrics: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
