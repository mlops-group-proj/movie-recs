#!/usr/bin/env python3
"""Calculate API availability from Prometheus metrics.

This script queries Prometheus to calculate the availability percentage
over a specified time window. Availability is calculated as:

    Availability = (Total Requests - Error Requests) / Total Requests

Where error requests are HTTP 500 status codes.

Requirements:
- ≥70% availability during 72h before and 144h after submission
- Prometheus must be accessible at PROMETHEUS_URL

Usage:
    # Calculate availability for the last 72 hours
    python scripts/calculate_availability.py --hours 72

    # Calculate for custom time window
    python scripts/calculate_availability.py --start 2025-11-18T00:00:00Z --end 2025-11-19T23:59:59Z

    # Output as JSON
    python scripts/calculate_availability.py --hours 144 --format json
"""

import argparse
import requests
import sys
from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional
import json


def query_prometheus(
    prom_url: str,
    query: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
) -> float:
    """Query Prometheus and return scalar result.

    Args:
        prom_url: Prometheus base URL
        query: PromQL query
        start_time: Start time for range queries (optional)
        end_time: End time for range queries (optional)

    Returns:
        Query result as float, or 0.0 if no data
    """
    if start_time and end_time:
        # Range query
        params = {
            "query": query,
            "start": start_time.isoformat() + "Z",
            "end": end_time.isoformat() + "Z",
            "step": "60s"  # 1 minute resolution
        }
        endpoint = f"{prom_url}/api/v1/query_range"
    else:
        # Instant query
        params = {"query": query}
        endpoint = f"{prom_url}/api/v1/query"

    try:
        resp = requests.get(endpoint, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        if data["status"] != "success":
            print(f"!!  Prometheus query failed: {data}", file=sys.stderr)
            return 0.0

        result = data.get("data", {}).get("result", [])
        if not result:
            return 0.0

        # For instant queries, return the value
        if "value" in result[0]:
            return float(result[0]["value"][1])

        # For range queries, sum all values
        if "values" in result[0]:
            total = sum(float(v[1]) for v in result[0]["values"])
            return total

        return 0.0

    except requests.RequestException as e:
        print(f"XX Failed to query Prometheus: {e}", file=sys.stderr)
        return 0.0


def calculate_availability(
    prom_url: str,
    hours: Optional[int] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None
) -> Dict[str, any]:
    """Calculate API availability from Prometheus metrics.

    Args:
        prom_url: Prometheus base URL
        hours: Number of hours to look back (if start/end not provided)
        start_time: Start of time window (optional)
        end_time: End of time window (optional)

    Returns:
        Dictionary with availability metrics
    """
    # Determine time window
    if start_time is None or end_time is None:
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours or 72)

    time_range = f"{int((end_time - start_time).total_seconds())}s"

    print(f"*  Calculating availability from {start_time} to {end_time}")
    print(f"*Time window: {time_range}\n")

    # Query total requests
    query_total = f'sum(increase(recommend_requests_total[{time_range}]))'
    total_requests = query_prometheus(prom_url, query_total)

    # Query successful requests (status="200")
    query_success = f'sum(increase(recommend_requests_total{{status="200"}}[{time_range}]))'
    success_requests = query_prometheus(prom_url, query_success)

    # Query error requests (status="500")
    query_errors = f'sum(increase(recommend_requests_total{{status="500"}}[{time_range}]))'
    error_requests = query_prometheus(prom_url, query_errors)

    # Calculate availability
    if total_requests == 0:
        availability_pct = 0.0
        print("!!  No requests found in the time window!")
    else:
        availability_pct = (success_requests / total_requests) * 100

    # Query uptime metrics
    query_uptime = f'avg_over_time(service_health_status[{time_range}])'
    avg_health = query_prometheus(prom_url, query_uptime)

    # Query latency P95
    query_latency_p95 = f'histogram_quantile(0.95, sum(rate(recommend_latency_seconds_bucket[{time_range}])) by (le))'
    latency_p95 = query_prometheus(prom_url, query_latency_p95)

    return {
        "time_window": {
            "start": start_time.isoformat() + "Z",
            "end": end_time.isoformat() + "Z",
            "duration_hours": (end_time - start_time).total_seconds() / 3600
        },
        "metrics": {
            "total_requests": int(total_requests),
            "successful_requests": int(success_requests),
            "error_requests": int(error_requests),
            "availability_percent": round(availability_pct, 2),
            "avg_health_status": round(avg_health, 3),
            "p95_latency_seconds": round(latency_p95, 3)
        },
        "slo_compliance": {
            "required_availability": 70.0,
            "actual_availability": round(availability_pct, 2),
            "meets_requirement": availability_pct >= 70.0,
            "margin": round(availability_pct - 70.0, 2)
        }
    }


def format_text_report(results: Dict) -> str:
    """Format results as human-readable text report."""
    tw = results["time_window"]
    m = results["metrics"]
    slo = results["slo_compliance"]

    report = f"""
╔══════════════════════════════════════════════════════════════════╗
║                  API AVAILABILITY REPORT                          ║
╚══════════════════════════════════════════════════════════════════╝

Time Window:
  Start:     {tw['start']}
  End:       {tw['end']}
  Duration:  {tw['duration_hours']:.1f} hours

Request Metrics:
  Total Requests:      {m['total_requests']:,}
  Successful (200):    {m['successful_requests']:,}
  Errors (500):        {m['error_requests']:,}
  Availability:        {m['availability_percent']:.2f}%

Additional Metrics:
  Avg Health Status:   {m['avg_health_status']:.3f}
  P95 Latency:         {m['p95_latency_seconds']:.3f}s

SLO Compliance:
  Required:            ≥{slo['required_availability']:.0f}%
  Actual:              {slo['actual_availability']:.2f}%
  Status:              {'*  PASS' if slo['meets_requirement'] else 'XX FAIL'}
  Margin:              {slo['margin']:+.2f} percentage points

"""

    if slo['meets_requirement']:
        report += "*  The API meets the ≥70% availability requirement!\n"
    else:
        report += "!!  WARNING: The API does NOT meet the 70% availability requirement.\n"

    return report


def main():
    parser = argparse.ArgumentParser(description="Calculate API availability from Prometheus metrics")

    # Time window options
    time_group = parser.add_mutually_exclusive_group()
    time_group.add_argument(
        "--hours",
        type=int,
        default=72,
        help="Number of hours to look back (default: 72)"
    )
    time_group.add_argument(
        "--start",
        type=str,
        help="Start time (ISO 8601 format, e.g., 2025-11-18T00:00:00Z)"
    )

    parser.add_argument(
        "--end",
        type=str,
        help="End time (ISO 8601 format, required if --start is used)"
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

    # Parse start/end times if provided
    start_time = None
    end_time = None
    if args.start:
        if not args.end:
            print("XX Error: --end is required when using --start", file=sys.stderr)
            sys.exit(1)
        try:
            start_time = datetime.fromisoformat(args.start.replace("Z", ""))
            end_time = datetime.fromisoformat(args.end.replace("Z", ""))
        except ValueError as e:
            print(f"XX Error parsing time: {e}", file=sys.stderr)
            sys.exit(1)

    # Calculate availability
    try:
        results = calculate_availability(
            prom_url=args.prometheus_url,
            hours=args.hours if not start_time else None,
            start_time=start_time,
            end_time=end_time
        )
    except Exception as e:
        print(f"XX Error calculating availability: {e}", file=sys.stderr)
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
        print(f"*  Report saved to: {args.output}")
    else:
        print(output)

    # Exit with appropriate code
    if not results["slo_compliance"]["meets_requirement"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
