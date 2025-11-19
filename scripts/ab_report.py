#!/usr/bin/env python3
"""Generate A/B test experiment report from API analysis.

Usage:
    python scripts/ab_report.py --time-window 60 --output reports/ab_test_2025-11-19.md
"""

import argparse
import requests
import json
from datetime import datetime
from pathlib import Path


def fetch_experiment_analysis(api_url: str, time_window: int) -> dict:
    """Fetch experiment analysis from API."""
    url = f"{api_url}/experiment/analyze"
    params = {"time_window_minutes": time_window}

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"❌ Failed to fetch experiment analysis: {e}")
        exit(1)


def generate_markdown_report(data: dict, time_window: int) -> str:
    """Generate markdown report from experiment analysis data."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Check for insufficient data
    if data.get("status") == "insufficient_data":
        return f"""# A/B Test Experiment Report - INSUFFICIENT DATA

**Generated**: {timestamp}
**Time Window**: {time_window} minutes

## ⚠️ Status: Insufficient Data

{data.get('message', 'No data available')}

### Metrics Summary
- Variant A: {data['metrics']['variant_A']['requests']} requests
- Variant B: {data['metrics']['variant_B']['requests']} requests

**Action Required**: Generate traffic to collect experiment data before analysis can be performed.
"""

    exp = data.get("experiment", {})
    metrics = data.get("metrics", {})
    analysis = data.get("statistical_analysis", {})
    latency = data.get("latency_comparison", {})

    variant_a = metrics.get("variant_A", {})
    variant_b = metrics.get("variant_B", {})
    test_results = analysis.get("results", {})
    decision = analysis.get("decision", "unknown")
    recommendation = analysis.get("recommendation", "No recommendation available")

    # Decision emoji
    decision_emoji = {
        "ship_variant_a": "✅",
        "ship_variant_b": "🚀",
        "no_difference": "⚖️",
        "inconclusive": "⏳"
    }.get(decision, "❓")

    report = f"""# A/B Test Experiment Report

**Generated**: {timestamp}
**Time Window**: {time_window} minutes
**Experiment Strategy**: {exp.get('strategy', 'unknown')}

---

## {decision_emoji} Decision: {decision.replace('_', ' ').title()}

**Recommendation**: {recommendation}

---

## Experiment Setup

| Variant | Model Version | Description |
|---------|---------------|-------------|
| **Variant A** | {exp.get('variant_A', 'unknown')} | Control (even user_ids) |
| **Variant B** | {exp.get('variant_B', 'unknown')} | Treatment (odd user_ids) |

---

## Metrics Summary

### Success Rate

| Metric | Variant A | Variant B | Delta |
|--------|-----------|-----------|-------|
| **Requests** | {variant_a.get('requests', 0):,} | {variant_b.get('requests', 0):,} | - |
| **Successes** | {variant_a.get('successes', 0):,} | {variant_b.get('successes', 0):,} | - |
| **Success Rate** | {variant_a.get('success_rate', 0):.2%} | {variant_b.get('success_rate', 0):.2%} | {test_results.get('delta', 0):.4f} |

### Latency (P95)

| Metric | Variant A | Variant B | Delta |
|--------|-----------|-----------|-------|
| **P95 Latency** | {latency.get('variant_A_p95_ms', 0):.2f}ms | {latency.get('variant_B_p95_ms', 0):.2f}ms | {latency.get('delta_ms', 0):+.2f}ms ({latency.get('percent_change', 0):+.1f}%) |

---

## Statistical Analysis

### Two-Proportion Z-Test

**Hypothesis Test**: Does Variant B differ from Variant A in success rate?

| Statistic | Value |
|-----------|-------|
| **Z-statistic** | {test_results.get('z_statistic', 0):.4f} |
| **P-value** | {test_results.get('p_value', 0):.6f} |
| **Significant?** | {'✅ Yes' if test_results.get('significant', False) else '❌ No'} (α=0.05) |
| **Effect Size** | {test_results.get('delta', 0):.4f} ({test_results.get('delta', 0)*100:.2f} percentage points) |
| **95% CI** | [{test_results.get('ci_lower', 0):.4f}, {test_results.get('ci_upper', 0):.4f}] |

**Interpretation**:
- **P-value < 0.05**: Statistically significant difference
- **P-value ≥ 0.05**: No statistically significant difference
- **Effect Size**: {abs(test_results.get('delta', 0))*100:.2f} percentage point {'increase' if test_results.get('delta', 0) > 0 else 'decrease'}

---

## Decision Criteria

The decision was made based on:

1. **Sample Size**: Minimum 1,000 samples per variant required
   - Variant A: {variant_a.get('requests', 0):,} samples {'✅' if variant_a.get('requests', 0) >= 1000 else '❌'}
   - Variant B: {variant_b.get('requests', 0):,} samples {'✅' if variant_b.get('requests', 0) >= 1000 else '❌'}

2. **Statistical Significance**: P-value < 0.05
   - P-value: {test_results.get('p_value', 0):.6f} {'✅' if test_results.get('p_value', 0) < 0.05 else '❌'}

3. **Practical Significance**: |Effect Size| > 1 percentage point
   - Effect: {abs(test_results.get('delta', 0))*100:.2f}pp {'✅' if abs(test_results.get('delta', 0)) > 0.01 else '❌'}

---

## Next Steps

"""
    # Add next steps based on decision
    if decision == "ship_variant_b":
        report += """1. ✅ **Ship Variant B** to 100% of traffic
2. Update `MODEL_VERSION` environment variable to Variant B version
3. Monitor metrics for 24-48 hours post-rollout
4. Update baseline metrics for future experiments
"""
    elif decision == "ship_variant_a":
        report += """1. ✅ **Keep Variant A** (current production version)
2. Do not proceed with Variant B rollout
3. Investigate why Variant B underperformed
4. Consider alternative approaches
"""
    elif decision == "inconclusive":
        report += """1. ⏳ **Continue Experiment** - insufficient data
2. Run experiment for longer duration
3. Target: ≥1,000 samples per variant
4. Re-analyze after collecting more data
"""
    else:  # no_difference
        report += """1. ⚖️ **Either variant acceptable** - no significant difference
2. Can ship Variant B if preferred for other reasons (cost, maintainability, etc.)
3. Or keep Variant A if no compelling reason to change
4. Document decision rationale
"""

    report += f"""
---

## Raw Data

```json
{json.dumps(data, indent=2)}
```

---

**Generated by**: A/B Test Analysis Tool
**Timestamp**: {timestamp}
"""

    return report


def main():
    parser = argparse.ArgumentParser(description="Generate A/B test experiment report")
    parser.add_argument(
        "--api-url",
        default="http://localhost:8080",
        help="API base URL (default: http://localhost:8080)"
    )
    parser.add_argument(
        "--time-window",
        type=int,
        default=60,
        help="Time window in minutes (default: 60)"
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output file path (default: reports/ab_test_YYYY-MM-DD.md)"
    )

    args = parser.parse_args()

    # Fetch analysis
    print(f"📊 Fetching experiment analysis from {args.api_url}...")
    data = fetch_experiment_analysis(args.api_url, args.time_window)

    # Generate report
    print("📝 Generating markdown report...")
    report = generate_markdown_report(data, args.time_window)

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        reports_dir = Path("reports")
        reports_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d")
        output_path = reports_dir / f"ab_test_{timestamp}.md"

    # Write report
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report)

    print(f"✅ Report saved to: {output_path}")
    print(f"\n{'='*60}")
    print(report)
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
