#!/usr/bin/env python3
"""
Generate comprehensive fairness and security analysis report with visualizations.

Usage:
    python scripts/generate_fairness_security_report.py \
        --reco-responses deliverables/evidence/reco_responses.jsonl \
        --rate-events deliverables/evidence/rate_events.jsonl \
        --output-dir deliverables/evidence/analysis
"""
import argparse
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, pstdev
from typing import Dict, Any, List, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def load_jsonl(path: Path) -> List[Dict]:
    """Load JSONL file into list of dicts."""
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return records


def gini(values: List[int]) -> float:
    """Calculate Gini coefficient."""
    vals = sorted([v for v in values if v >= 0])
    if not vals or sum(vals) == 0:
        return 0.0
    n = len(vals)
    cum = sum((i + 1) * v for i, v in enumerate(vals))
    return (2 * cum) / (n * sum(vals)) - (n + 1) / n


def analyze_fairness(reco_responses: List[Dict], catalog_size: int = 3883) -> Dict[str, Any]:
    """Compute fairness metrics from recommendation responses."""
    exposures = Counter()
    segment_counts = defaultdict(int)
    total_recs = 0

    for rec in reco_responses:
        movies = rec.get("movie_ids", [])
        user_id = rec.get("user_id")

        seg = "even" if user_id and user_id % 2 == 0 else "odd"

        for m in movies:
            exposures[m] += 1
        segment_counts[seg] += 1
        total_recs += len(movies)

    if not exposures:
        return {"error": "No recommendations found"}

    # Calculate metrics
    sorted_items = sorted(exposures.items(), key=lambda x: x[1], reverse=True)
    total_exposure = sum(exposures.values())

    # Top-k popularity analysis
    top_10_pct = max(1, int(len(sorted_items) * 0.1))
    top_20_pct = max(1, int(len(sorted_items) * 0.2))

    top_10_exposure = sum(cnt for _, cnt in sorted_items[:top_10_pct])
    top_20_exposure = sum(cnt for _, cnt in sorted_items[:top_20_pct])

    return {
        "total_recommendations": total_recs,
        "unique_items": len(exposures),
        "catalog_size": catalog_size,
        "catalog_coverage": len(exposures) / catalog_size,
        "gini_coefficient": gini(list(exposures.values())),
        "top_10_pct_share": top_10_exposure / total_exposure,
        "top_20_pct_share": top_20_exposure / total_exposure,
        "tail_share": 1 - (top_10_exposure / total_exposure),
        "segment_counts": dict(segment_counts),
        "exposures": dict(exposures),
        "sorted_items": sorted_items[:50],  # Top 50 for visualization
        "zero_exposure_items": catalog_size - len(exposures),
    }


def analyze_security(rate_events: List[Dict]) -> Dict[str, Any]:
    """Detect anomalies in rating events."""
    user_counts = Counter()
    schema_errors = 0

    for rec in rate_events:
        if "user_id" not in rec or "movie_id" not in rec:
            schema_errors += 1
            continue
        user_counts[rec["user_id"]] += 1

    if not user_counts:
        return {"error": "No valid events found"}

    vals = list(user_counts.values())
    avg = mean(vals)
    std = pstdev(vals) if len(vals) > 1 else 0
    threshold = avg + 3 * std

    flagged = [
        {"user_id": uid, "count": cnt, "multiple_of_avg": round(cnt / avg, 2)}
        for uid, cnt in user_counts.items()
        if cnt > threshold
    ]

    return {
        "total_events": sum(vals),
        "unique_users": len(user_counts),
        "schema_errors": schema_errors,
        "mean_events_per_user": avg,
        "std_events_per_user": std,
        "threshold": threshold,
        "flagged_users": sorted(flagged, key=lambda x: x["count"], reverse=True),
        "user_counts": dict(user_counts),
    }


def analyze_feedback_loop(fairness_results: Dict, catalog_size: int = 3883) -> Dict[str, Any]:
    """Analyze potential feedback loop indicators."""
    exposures = fairness_results.get("exposures", {})
    if not exposures:
        return {"error": "No exposure data"}

    # Group items by exposure tier
    tiers = {
        "high": [],      # Top 10%
        "medium": [],    # 10-50%
        "low": [],       # 50-90%
        "tail": [],      # Bottom 10%
        "zero": [],      # No exposure
    }

    sorted_items = sorted(exposures.items(), key=lambda x: x[1], reverse=True)
    n = len(sorted_items)

    for i, (item, count) in enumerate(sorted_items):
        pct = i / n
        if pct < 0.1:
            tiers["high"].append((item, count))
        elif pct < 0.5:
            tiers["medium"].append((item, count))
        elif pct < 0.9:
            tiers["low"].append((item, count))
        else:
            tiers["tail"].append((item, count))

    tiers["zero"] = [(i, 0) for i in range(1, catalog_size + 1) if i not in exposures]

    # Calculate amplification factors
    total_exposure = sum(exposures.values())
    tier_stats = {}

    for tier_name, items in tiers.items():
        if items:
            exposure_sum = sum(c for _, c in items)
            tier_stats[tier_name] = {
                "count": len(items),
                "catalog_pct": len(items) / catalog_size,
                "exposure_pct": exposure_sum / total_exposure if total_exposure > 0 else 0,
                "amplification": (exposure_sum / total_exposure) / (len(items) / catalog_size) if len(items) > 0 else 0,
            }

    return {
        "tier_stats": tier_stats,
        "zero_exposure_count": len(tiers["zero"]),
        "starvation_index": len(tiers["zero"]) / catalog_size,
    }


def plot_exposure_distribution(fairness_results: Dict, output_path: Path):
    """Plot item exposure distribution."""
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    exposures = fairness_results.get("exposures", {})
    counts = list(exposures.values())

    # 1. Histogram of exposures
    ax1 = axes[0, 0]
    ax1.hist(counts, bins=30, edgecolor='black', alpha=0.7)
    ax1.set_xlabel('Number of Exposures')
    ax1.set_ylabel('Number of Items')
    ax1.set_title('Distribution of Item Exposures')
    ax1.axvline(np.mean(counts), color='red', linestyle='--', label=f'Mean: {np.mean(counts):.1f}')
    ax1.legend()

    # 2. Top-N items bar chart
    ax2 = axes[0, 1]
    top_items = fairness_results.get("sorted_items", [])[:20]
    if top_items:
        items, item_counts = zip(*top_items)
        ax2.barh(range(len(items)), item_counts, color='steelblue')
        ax2.set_yticks(range(len(items)))
        ax2.set_yticklabels([f'Movie {i}' for i in items])
        ax2.set_xlabel('Exposures')
        ax2.set_title('Top 20 Most Recommended Movies')
        ax2.invert_yaxis()

    # 3. Lorenz curve (inequality visualization)
    ax3 = axes[1, 0]
    sorted_counts = sorted(counts)
    cumulative = np.cumsum(sorted_counts) / sum(sorted_counts)
    x = np.linspace(0, 1, len(cumulative))
    ax3.plot(x, cumulative, 'b-', linewidth=2, label='Actual Distribution')
    ax3.plot([0, 1], [0, 1], 'r--', linewidth=1, label='Perfect Equality')
    ax3.fill_between(x, cumulative, x, alpha=0.3)
    ax3.set_xlabel('Cumulative % of Items')
    ax3.set_ylabel('Cumulative % of Exposures')
    ax3.set_title(f'Lorenz Curve (Gini = {fairness_results["gini_coefficient"]:.3f})')
    ax3.legend()
    ax3.set_xlim(0, 1)
    ax3.set_ylim(0, 1)

    # 4. Segment comparison
    ax4 = axes[1, 1]
    segments = fairness_results.get("segment_counts", {})
    if segments:
        seg_names = list(segments.keys())
        seg_values = list(segments.values())
        bars = ax4.bar(seg_names, seg_values, color=['#2ecc71', '#3498db'])
        ax4.set_ylabel('Number of Requests')
        ax4.set_title('Recommendations by User Segment')
        for bar, val in zip(bars, seg_values):
            ax4.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5,
                    str(val), ha='center', va='bottom')

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Saved exposure distribution plot to {output_path}")


def plot_security_analysis(security_results: Dict, output_path: Path):
    """Plot security analysis visualizations."""
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    user_counts = security_results.get("user_counts", {})
    counts = list(user_counts.values())
    threshold = security_results.get("threshold", 0)

    # 1. Histogram of events per user
    ax1 = axes[0]
    ax1.hist(counts, bins=20, edgecolor='black', alpha=0.7, color='steelblue')
    ax1.axvline(threshold, color='red', linestyle='--', linewidth=2,
                label=f'Threshold: {threshold:.1f}')
    ax1.axvline(security_results["mean_events_per_user"], color='green',
                linestyle='--', label=f'Mean: {security_results["mean_events_per_user"]:.1f}')
    ax1.set_xlabel('Events per User')
    ax1.set_ylabel('Number of Users')
    ax1.set_title('Distribution of Rating Events per User')
    ax1.legend()

    # 2. Flagged users
    ax2 = axes[1]
    flagged = security_results.get("flagged_users", [])
    if flagged:
        user_ids = [f"User {f['user_id']}" for f in flagged]
        user_event_counts = [f['count'] for f in flagged]
        colors = ['#e74c3c' if c > threshold * 1.5 else '#f39c12' for c in user_event_counts]
        bars = ax2.barh(user_ids, user_event_counts, color=colors)
        ax2.axvline(threshold, color='red', linestyle='--', linewidth=2, label=f'Threshold: {threshold:.1f}')
        ax2.set_xlabel('Event Count')
        ax2.set_title('Flagged Users (Potential Spam)')
        ax2.legend()

        for bar, count in zip(bars, user_event_counts):
            ax2.text(bar.get_width() + 1, bar.get_y() + bar.get_height()/2,
                    f'{count}', va='center')
    else:
        ax2.text(0.5, 0.5, 'No anomalies detected', ha='center', va='center',
                transform=ax2.transAxes, fontsize=14)
        ax2.set_title('Flagged Users')

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Saved security analysis plot to {output_path}")


def plot_feedback_loop(loop_results: Dict, output_path: Path):
    """Plot feedback loop analysis."""
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    tier_stats = loop_results.get("tier_stats", {})

    # 1. Amplification by tier
    ax1 = axes[0]
    tiers = ['high', 'medium', 'low', 'tail']
    amplifications = [tier_stats.get(t, {}).get('amplification', 0) for t in tiers]
    colors = ['#e74c3c', '#f39c12', '#3498db', '#2ecc71']
    bars = ax1.bar(tiers, amplifications, color=colors)
    ax1.axhline(1.0, color='black', linestyle='--', label='No Amplification (1.0x)')
    ax1.set_ylabel('Amplification Factor')
    ax1.set_xlabel('Item Tier')
    ax1.set_title('Recommendation Amplification by Popularity Tier')
    ax1.legend()

    for bar, val in zip(bars, amplifications):
        ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.05,
                f'{val:.2f}x', ha='center', va='bottom')

    # 2. Exposure share vs catalog share
    ax2 = axes[1]
    catalog_pcts = [tier_stats.get(t, {}).get('catalog_pct', 0) * 100 for t in tiers]
    exposure_pcts = [tier_stats.get(t, {}).get('exposure_pct', 0) * 100 for t in tiers]

    x = np.arange(len(tiers))
    width = 0.35

    bars1 = ax2.bar(x - width/2, catalog_pcts, width, label='% of Catalog', color='#3498db')
    bars2 = ax2.bar(x + width/2, exposure_pcts, width, label='% of Exposures', color='#e74c3c')

    ax2.set_ylabel('Percentage')
    ax2.set_xlabel('Item Tier')
    ax2.set_title('Catalog Share vs Exposure Share by Tier')
    ax2.set_xticks(x)
    ax2.set_xticklabels(tiers)
    ax2.legend()

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Saved feedback loop plot to {output_path}")


def generate_summary_table(fairness: Dict, security: Dict, loop: Dict) -> str:
    """Generate markdown summary table."""
    lines = [
        "## Analysis Summary",
        "",
        "### Fairness Metrics",
        "",
        "| Metric | Value | Threshold | Status |",
        "|--------|-------|-----------|--------|",
        f"| Catalog Coverage | {fairness['catalog_coverage']*100:.1f}% | >= 40% | {'PASS' if fairness['catalog_coverage'] >= 0.4 else 'FAIL'} |",
        f"| Gini Coefficient | {fairness['gini_coefficient']:.3f} | <= 0.35 | {'PASS' if fairness['gini_coefficient'] <= 0.35 else 'FAIL'} |",
        f"| Top-10% Share | {fairness['top_10_pct_share']*100:.1f}% | <= 30% | {'PASS' if fairness['top_10_pct_share'] <= 0.30 else 'FAIL'} |",
        f"| Tail Share | {fairness['tail_share']*100:.1f}% | >= 70% | {'PASS' if fairness['tail_share'] >= 0.70 else 'FAIL'} |",
        "",
        "### Feedback Loop Indicators",
        "",
        "| Tier | Amplification | Interpretation |",
        "|------|---------------|----------------|",
    ]

    tier_stats = loop.get("tier_stats", {})
    for tier in ['high', 'medium', 'low', 'tail']:
        amp = tier_stats.get(tier, {}).get('amplification', 0)
        interp = "Over-represented" if amp > 1.5 else "Under-represented" if amp < 0.5 else "Balanced"
        lines.append(f"| {tier.capitalize()} | {amp:.2f}x | {interp} |")

    lines.extend([
        "",
        f"| Starvation Index | {loop.get('starvation_index', 0)*100:.1f}% | Items with zero exposure |",
        "",
        "### Security Analysis",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total Events | {security['total_events']} |",
        f"| Unique Users | {security['unique_users']} |",
        f"| Schema Errors | {security['schema_errors']} |",
        f"| Detection Threshold | {security['threshold']:.1f} events |",
        f"| Flagged Users | {len(security['flagged_users'])} |",
    ])

    if security['flagged_users']:
        lines.extend([
            "",
            "**Flagged Accounts:**",
            "",
            "| User ID | Event Count | Multiple of Avg | Risk Level |",
            "|---------|-------------|-----------------|------------|",
        ])
        for user in security['flagged_users']:
            risk = "HIGH" if user['multiple_of_avg'] > 10 else "MEDIUM"
            lines.append(f"| {user['user_id']} | {user['count']} | {user['multiple_of_avg']}x | {risk} |")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate fairness and security analysis report")
    parser.add_argument("--reco-responses", type=Path, required=True,
                       help="Path to reco_responses JSONL file")
    parser.add_argument("--rate-events", type=Path, required=True,
                       help="Path to rate_events JSONL file")
    parser.add_argument("--output-dir", type=Path, default=Path("deliverables/evidence/analysis"),
                       help="Output directory for results")
    parser.add_argument("--catalog-size", type=int, default=3883,
                       help="Total catalog size")
    args = parser.parse_args()

    # Create output directory
    args.output_dir.mkdir(parents=True, exist_ok=True)

    print("Loading data...")
    reco_responses = load_jsonl(args.reco_responses)
    rate_events = load_jsonl(args.rate_events)

    print(f"Loaded {len(reco_responses)} recommendation responses")
    print(f"Loaded {len(rate_events)} rating events")

    # Run analyses
    print("\nAnalyzing fairness metrics...")
    fairness_results = analyze_fairness(reco_responses, args.catalog_size)

    print("Analyzing security anomalies...")
    security_results = analyze_security(rate_events)

    print("Analyzing feedback loop indicators...")
    loop_results = analyze_feedback_loop(fairness_results, args.catalog_size)

    # Save JSON results
    with open(args.output_dir / "fairness_analysis.json", "w") as f:
        # Remove large fields for JSON output
        fairness_output = {k: v for k, v in fairness_results.items()
                         if k not in ["exposures", "sorted_items"]}
        json.dump(fairness_output, f, indent=2)

    with open(args.output_dir / "security_analysis.json", "w") as f:
        security_output = {k: v for k, v in security_results.items()
                          if k != "user_counts"}
        json.dump(security_output, f, indent=2)

    with open(args.output_dir / "feedback_loop_analysis.json", "w") as f:
        json.dump(loop_results, f, indent=2)

    # Generate visualizations
    print("\nGenerating visualizations...")
    plot_exposure_distribution(fairness_results, args.output_dir / "exposure_distribution.png")
    plot_security_analysis(security_results, args.output_dir / "security_analysis.png")
    plot_feedback_loop(loop_results, args.output_dir / "feedback_loop.png")

    # Generate summary
    summary = generate_summary_table(fairness_results, security_results, loop_results)
    with open(args.output_dir / "SUMMARY.md", "w") as f:
        f.write(summary)

    print(f"\nResults saved to {args.output_dir}/")
    print("\nKey Findings:")
    print(f"  - Gini Coefficient: {fairness_results['gini_coefficient']:.3f} (threshold: 0.35)")
    print(f"  - Catalog Coverage: {fairness_results['catalog_coverage']*100:.1f}% (threshold: 40%)")
    print(f"  - Starvation Index: {loop_results['starvation_index']*100:.1f}%")
    print(f"  - Flagged Users: {len(security_results['flagged_users'])}")

    if security_results['flagged_users']:
        print("\n  Anomalous accounts detected:")
        for user in security_results['flagged_users']:
            print(f"    - User {user['user_id']}: {user['count']} events ({user['multiple_of_avg']}x avg)")


if __name__ == "__main__":
    main()
