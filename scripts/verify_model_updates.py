#!/usr/bin/env python3
"""Verify that at least 2 model updates occurred within a 7-day window.

This script queries Prometheus for model switch events and verifies that
at least 2 distinct model version changes occurred within the same 7-day
window.

Requirements:
- At least 2 model updates within a 7-day window
- Model switches tracked via model_switches_total metric

Usage:
    # Check model updates in the last 7 days
    python scripts/verify_model_updates.py

    # Check specific time window
    python scripts/verify_model_updates.py --start 2025-11-12T00:00:00Z --end 2025-11-19T23:59:59Z

    # Output as JSON
    python scripts/verify_model_updates.py --format json
"""

import argparse
import requests
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Tuple
import json
from collections import defaultdict


def query_prometheus_range(
    prom_url: str,
    query: str,
    start_time: datetime,
    end_time: datetime
) -> List[Dict]:
    """Query Prometheus for range data.

    Args:
        prom_url: Prometheus base URL
        query: PromQL query
        start_time: Start time
        end_time: End time

    Returns:
        List of result dictionaries
    """
    params = {
        "query": query,
        "start": start_time.isoformat() + "Z",
        "end": end_time.isoformat() + "Z",
        "step": "60s"  # 1 minute resolution
    }
    endpoint = f"{prom_url}/api/v1/query_range"

    try:
        resp = requests.get(endpoint, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        if data["status"] != "success":
            print(f"⚠️  Prometheus query failed: {data}", file=sys.stderr)
            return []

        return data.get("data", {}).get("result", [])

    except requests.RequestException as e:
        print(f"❌ Failed to query Prometheus: {e}", file=sys.stderr)
        return []


def extract_model_switches(
    prom_url: str,
    start_time: datetime,
    end_time: datetime
) -> List[Dict]:
    """Extract model switch events from Prometheus.

    Args:
        prom_url: Prometheus base URL
        start_time: Start time
        end_time: End time

    Returns:
        List of model switch events with timestamps
    """
    # Query model_switches_total metric
    query = 'model_switches_total{status="success"}'

    results = query_prometheus_range(prom_url, query, start_time, end_time)

    switches = []
    for result in results:
        metric = result.get("metric", {})
        values = result.get("values", [])

        from_version = metric.get("from_version", "unknown")
        to_version = metric.get("to_version", "unknown")

        # Process time series to find increases (actual switch events)
        prev_value = None
        for timestamp, value in values:
            current_value = float(value)

            # Detect increase (new switch event)
            if prev_value is not None and current_value > prev_value:
                dt = datetime.fromtimestamp(float(timestamp))
                switches.append({
                    "timestamp": dt,
                    "from_version": from_version,
                    "to_version": to_version,
                    "count_increase": int(current_value - prev_value)
                })

            prev_value = current_value

    # Sort by timestamp
    switches.sort(key=lambda x: x["timestamp"])
    return switches


def find_max_updates_in_7day_window(switches: List[Dict]) -> Tuple[int, List[Dict], datetime, datetime]:
    """Find the maximum number of model updates within any 7-day sliding window.

    Args:
        switches: List of model switch events

    Returns:
        Tuple of (max_count, events_in_window, window_start, window_end)
    """
    if len(switches) < 2:
        if switches:
            return len(switches), switches, switches[0]["timestamp"], switches[0]["timestamp"]
        return 0, [], None, None

    max_count = 0
    best_window_events = []
    best_start = None
    best_end = None

    # Sliding window approach
    for i, start_switch in enumerate(switches):
        window_start = start_switch["timestamp"]
        window_end = window_start + timedelta(days=7)

        # Count switches within this 7-day window
        window_events = []
        for switch in switches[i:]:
            if switch["timestamp"] <= window_end:
                window_events.append(switch)
            else:
                break

        if len(window_events) > max_count:
            max_count = len(window_events)
            best_window_events = window_events
            best_start = window_start
            best_end = window_end

    return max_count, best_window_events, best_start, best_end


def verify_model_updates(
    prom_url: str,
    start_time: datetime,
    end_time: datetime
) -> Dict:
    """Verify that at least 2 model updates occurred within a 7-day window.

    Args:
        prom_url: Prometheus base URL
        start_time: Start of observation period
        end_time: End of observation period

    Returns:
        Dictionary with verification results
    """
    print(f"🔍 Searching for model updates from {start_time} to {end_time}\n")

    # Extract model switches
    switches = extract_model_switches(prom_url, start_time, end_time)

    if not switches:
        print("⚠️  No model switch events found in Prometheus!")
        return {
            "observation_period": {
                "start": start_time.isoformat() + "Z",
                "end": end_time.isoformat() + "Z",
                "duration_days": (end_time - start_time).days
            },
            "total_switches": 0,
            "switches": [],
            "best_7day_window": {
                "start": None,
                "end": None,
                "switch_count": 0,
                "switches": []
            },
            "requirement": {
                "minimum_updates": 2,
                "within_days": 7,
                "actual_updates": 0,
                "meets_requirement": False
            }
        }

    # Find best 7-day window
    max_count, window_events, window_start, window_end = find_max_updates_in_7day_window(switches)

    # Format switches for output
    formatted_switches = []
    for sw in switches:
        formatted_switches.append({
            "timestamp": sw["timestamp"].isoformat() + "Z",
            "from_version": sw["from_version"],
            "to_version": sw["to_version"]
        })

    formatted_window_switches = []
    if window_events:
        for sw in window_events:
            formatted_window_switches.append({
                "timestamp": sw["timestamp"].isoformat() + "Z",
                "from_version": sw["from_version"],
                "to_version": sw["to_version"]
            })

    return {
        "observation_period": {
            "start": start_time.isoformat() + "Z",
            "end": end_time.isoformat() + "Z",
            "duration_days": (end_time - start_time).days
        },
        "total_switches": len(switches),
        "switches": formatted_switches,
        "best_7day_window": {
            "start": window_start.isoformat() + "Z" if window_start else None,
            "end": window_end.isoformat() + "Z" if window_end else None,
            "switch_count": max_count,
            "switches": formatted_window_switches
        },
        "requirement": {
            "minimum_updates": 2,
            "within_days": 7,
            "actual_updates": max_count,
            "meets_requirement": max_count >= 2
        }
    }


def format_text_report(results: Dict) -> str:
    """Format results as human-readable text report."""
    obs = results["observation_period"]
    window = results["best_7day_window"]
    req = results["requirement"]

    report = f"""
╔══════════════════════════════════════════════════════════════════╗
║              MODEL UPDATE VERIFICATION REPORT                     ║
╚══════════════════════════════════════════════════════════════════╝

Observation Period:
  Start:     {obs['start']}
  End:       {obs['end']}
  Duration:  {obs['duration_days']} days

Model Switches Found:
  Total:     {results['total_switches']} switches

"""

    if results['switches']:
        report += "All Model Switches:\n"
        for i, sw in enumerate(results['switches'], 1):
            report += f"  {i}. [{sw['timestamp']}] {sw['from_version']} → {sw['to_version']}\n"
        report += "\n"

    report += f"""Best 7-Day Window:
  Window:    {window['start']} to {window['end']}
  Switches:  {window['switch_count']} updates

"""

    if window['switches']:
        report += "Switches in Best Window:\n"
        for i, sw in enumerate(window['switches'], 1):
            report += f"  {i}. [{sw['timestamp']}] {sw['from_version']} → {sw['to_version']}\n"
        report += "\n"

    report += f"""Requirement Check:
  Required:  ≥{req['minimum_updates']} updates within {req['within_days']} days
  Actual:    {req['actual_updates']} updates
  Status:    {'✅ PASS' if req['meets_requirement'] else '❌ FAIL'}

"""

    if req['meets_requirement']:
        report += "🎉 The system meets the model update requirement!\n"
    else:
        report += f"⚠️  WARNING: Found only {req['actual_updates']} updates. Need ≥2 within 7 days.\n"

    return report


def main():
    parser = argparse.ArgumentParser(description="Verify model updates occurred within 7-day window")

    parser.add_argument(
        "--start",
        type=str,
        help="Start time (ISO 8601 format, e.g., 2025-11-12T00:00:00Z). Default: 7 days ago"
    )
    parser.add_argument(
        "--end",
        type=str,
        help="End time (ISO 8601 format). Default: now"
    )
    parser.add_argument(
        "--prometheus-url",
        type=str,
        default="http://localhost:9090",
        help="Prometheus URL (default: http://localhost:9090)"
    )
    parser.add_argument(
        "--format",
        type=str,
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)"
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output file path (default: stdout)"
    )

    args = parser.parse_args()

    # Parse times
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(days=7)

    if args.end:
        try:
            end_time = datetime.fromisoformat(args.end.replace("Z", ""))
        except ValueError as e:
            print(f"❌ Error parsing --end: {e}", file=sys.stderr)
            sys.exit(1)

    if args.start:
        try:
            start_time = datetime.fromisoformat(args.start.replace("Z", ""))
        except ValueError as e:
            print(f"❌ Error parsing --start: {e}", file=sys.stderr)
            sys.exit(1)

    # Verify model updates
    try:
        results = verify_model_updates(args.prometheus_url, start_time, end_time)
    except Exception as e:
        print(f"❌ Error verifying model updates: {e}", file=sys.stderr)
        sys.exit(1)

    # Format output
    if args.format == "json":
        output = json.dumps(results, indent=2)
    else:
        output = format_text_report(results)

    # Write output
    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
        print(f"✅ Report saved to: {args.output}")
    else:
        print(output)

    # Exit with appropriate code
    if not results["requirement"]["meets_requirement"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
