#!/usr/bin/env python3
"""Collect all evidence for deliverables PDF.

This script collects all required evidence including:
- Availability calculations
- Model update verification
- Screenshots/exports of dashboards
- Sample API responses with provenance
- Logs showing system operation
- Model registry contents
- Git commit history

Usage:
    python scripts/collect_evidence.py --output evidence/
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
import requests


def run_command(cmd: list, description: str) -> tuple:
    """Run a shell command and return output.

    Args:
        cmd: Command as list of strings
        description: Description of what the command does

    Returns:
        Tuple of (success: bool, output: str)
    """
    print(f"  → {description}...")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        print(f"    ❌ Failed: {e}")
        return False, e.stderr


def collect_availability_report(output_dir: Path, prometheus_url: str):
    """Collect availability calculation reports."""
    print("\n📊 Collecting Availability Reports...")

    reports_dir = output_dir / "availability"
    reports_dir.mkdir(parents=True, exist_ok=True)

    # 72 hours before submission
    success, _ = run_command(
        ["python", "scripts/calculate_availability.py",
         "--hours", "72",
         "--prometheus-url", prometheus_url,
         "--format", "json",
         "--output", str(reports_dir / "availability_72h.json")],
        "Calculate 72h availability"
    )

    if success:
        run_command(
            ["python", "scripts/calculate_availability.py",
             "--hours", "72",
             "--prometheus-url", prometheus_url,
             "--format", "text",
             "--output", str(reports_dir / "availability_72h.txt")],
            "Generate 72h text report"
        )

    # 144 hours after submission
    success, _ = run_command(
        ["python", "scripts/calculate_availability.py",
         "--hours", "144",
         "--prometheus-url", prometheus_url,
         "--format", "json",
         "--output", str(reports_dir / "availability_144h.json")],
        "Calculate 144h availability"
    )

    if success:
        run_command(
            ["python", "scripts/calculate_availability.py",
             "--hours", "144",
             "--prometheus-url", prometheus_url,
             "--format", "text",
             "--output", str(reports_dir / "availability_144h.txt")],
            "Generate 144h text report"
        )

    print("  ✅ Availability reports collected")


def collect_model_update_verification(output_dir: Path, prometheus_url: str):
    """Collect model update verification reports."""
    print("\n🔄 Collecting Model Update Verification...")

    reports_dir = output_dir / "model_updates"
    reports_dir.mkdir(parents=True, exist_ok=True)

    # Verify model updates
    success, _ = run_command(
        ["python", "scripts/verify_model_updates.py",
         "--prometheus-url", prometheus_url,
         "--format", "json",
         "--output", str(reports_dir / "model_updates_verification.json")],
        "Verify model updates"
    )

    if success:
        run_command(
            ["python", "scripts/verify_model_updates.py",
             "--prometheus-url", prometheus_url,
             "--format", "text",
             "--output", str(reports_dir / "model_updates_verification.txt")],
            "Generate verification text report"
        )

    print("  ✅ Model update verification collected")


def collect_sample_api_responses(output_dir: Path, api_url: str):
    """Collect sample API responses showing provenance."""
    print("\n🔍 Collecting Sample API Responses...")

    samples_dir = output_dir / "api_samples"
    samples_dir.mkdir(parents=True, exist_ok=True)

    # Test various endpoints
    endpoints = [
        ("/healthz", "healthz.json"),
        ("/recommend/123?k=10", "recommend_sample.json"),
        ("/rollout/status", "rollout_status.json"),
        ("/metrics", "metrics.txt"),
    ]

    for endpoint, filename in endpoints:
        try:
            print(f"  → GET {endpoint}")
            response = requests.get(f"{api_url}{endpoint}", timeout=10)

            if endpoint == "/metrics":
                # Save as text
                (samples_dir / filename).write_text(response.text)
            else:
                # Save as pretty JSON
                data = response.json()
                (samples_dir / filename).write_text(json.dumps(data, indent=2))

            print(f"    ✅ Saved to {filename}")

        except Exception as e:
            print(f"    ❌ Failed: {e}")

    # Get trace for the sample request
    try:
        # Make a request and capture request_id
        resp = requests.get(f"{api_url}/recommend/456?k=5", timeout=10)
        data = resp.json()

        # Save the response
        (samples_dir / "recommend_with_provenance.json").write_text(
            json.dumps(data, indent=2)
        )

        # Get the trace
        request_id = data.get("provenance", {}).get("request_id")
        if request_id:
            trace_resp = requests.get(f"{api_url}/trace/{request_id}", timeout=10)
            (samples_dir / "trace_sample.json").write_text(
                json.dumps(trace_resp.json(), indent=2)
            )
            print(f"  ✅ Collected trace for request_id={request_id}")

    except Exception as e:
        print(f"  ⚠️  Could not collect trace: {e}")

    print("  ✅ API samples collected")


def collect_model_registry_info(output_dir: Path):
    """Collect model registry metadata."""
    print("\n📦 Collecting Model Registry Info...")

    registry_dir = output_dir / "model_registry"
    registry_dir.mkdir(parents=True, exist_ok=True)

    # List all model versions
    model_registry_path = Path("model_registry")

    if not model_registry_path.exists():
        print("  ⚠️  Model registry not found")
        return

    versions = []
    for version_dir in sorted(model_registry_path.iterdir()):
        if version_dir.is_dir() and version_dir.name.startswith("v"):
            version_info = {"version": version_dir.name}

            # Read meta.json
            meta_file = version_dir / "meta.json"
            if meta_file.exists():
                with open(meta_file) as f:
                    version_info["metadata"] = json.load(f)

            versions.append(version_info)

    # Save summary
    (registry_dir / "versions_summary.json").write_text(
        json.dumps({"versions": versions}, indent=2)
    )

    print(f"  ✅ Found {len(versions)} model versions")


def collect_git_history(output_dir: Path):
    """Collect relevant git history."""
    print("\n📜 Collecting Git History...")

    git_dir = output_dir / "git_history"
    git_dir.mkdir(parents=True, exist_ok=True)

    # Get recent commits
    run_command(
        ["git", "log", "--oneline", "-50"],
        "Get recent commit history"
    )

    success, output = run_command(
        ["git", "log", "--pretty=format:%H|%an|%ae|%ad|%s", "--date=iso", "-50"],
        "Get detailed commit history"
    )

    if success:
        (git_dir / "commits.txt").write_text(output)

    # Get git SHA
    success, output = run_command(
        ["git", "rev-parse", "HEAD"],
        "Get current git SHA"
    )

    if success:
        (git_dir / "current_sha.txt").write_text(output.strip())

    # Get branch info
    success, output = run_command(
        ["git", "branch", "-v"],
        "Get branch information"
    )

    if success:
        (git_dir / "branches.txt").write_text(output)

    print("  ✅ Git history collected")


def collect_system_info(output_dir: Path):
    """Collect system and deployment information."""
    print("\n🖥️  Collecting System Info...")

    sys_dir = output_dir / "system_info"
    sys_dir.mkdir(parents=True, exist_ok=True)

    # Docker compose services
    success, output = run_command(
        ["docker", "compose", "ps"],
        "Get Docker Compose service status"
    )

    if success:
        (sys_dir / "docker_services.txt").write_text(output)

    # Docker images
    success, output = run_command(
        ["docker", "images"],
        "Get Docker images"
    )

    if success:
        (sys_dir / "docker_images.txt").write_text(output)

    # Requirements
    req_files = ["reqs-recommender.txt", "reqs-ingestor.txt"]
    for req_file in req_files:
        if Path(req_file).exists():
            content = Path(req_file).read_text()
            (sys_dir / req_file).write_text(content)

    print("  ✅ System info collected")


def collect_logs_sample(output_dir: Path):
    """Collect sample logs showing system operation."""
    print("\n📋 Collecting Log Samples...")

    logs_dir = output_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    # Get recent API logs
    success, output = run_command(
        ["docker", "compose", "logs", "--tail=500", "api"],
        "Get API logs (last 500 lines)"
    )

    if success:
        (logs_dir / "api_logs_sample.txt").write_text(output)

    # Get Prometheus logs
    success, output = run_command(
        ["docker", "compose", "logs", "--tail=200", "prometheus"],
        "Get Prometheus logs (last 200 lines)"
    )

    if success:
        (logs_dir / "prometheus_logs_sample.txt").write_text(output)

    print("  ✅ Log samples collected")


def create_evidence_summary(output_dir: Path):
    """Create a summary of all collected evidence."""
    print("\n📝 Creating Evidence Summary...")

    summary = {
        "collection_timestamp": datetime.utcnow().isoformat() + "Z",
        "evidence_collected": {
            "availability_reports": list((output_dir / "availability").glob("*.json")) if (output_dir / "availability").exists() else [],
            "model_update_verification": list((output_dir / "model_updates").glob("*.json")) if (output_dir / "model_updates").exists() else [],
            "api_samples": list((output_dir / "api_samples").glob("*.json")) if (output_dir / "api_samples").exists() else [],
            "model_registry_info": list((output_dir / "model_registry").glob("*.json")) if (output_dir / "model_registry").exists() else [],
            "git_history": list((output_dir / "git_history").glob("*.txt")) if (output_dir / "git_history").exists() else [],
            "system_info": list((output_dir / "system_info").glob("*.txt")) if (output_dir / "system_info").exists() else [],
            "logs": list((output_dir / "logs").glob("*.txt")) if (output_dir / "logs").exists() else []
        }
    }

    # Convert Path objects to strings for JSON serialization
    for key in summary["evidence_collected"]:
        summary["evidence_collected"][key] = [str(p.relative_to(output_dir)) for p in summary["evidence_collected"][key]]

    (output_dir / "EVIDENCE_SUMMARY.json").write_text(
        json.dumps(summary, indent=2)
    )

    print("  ✅ Evidence summary created")


def main():
    parser = argparse.ArgumentParser(description="Collect all evidence for deliverables")

    parser.add_argument(
        "--output",
        type=str,
        default="evidence",
        help="Output directory for evidence (default: evidence/)"
    )
    parser.add_argument(
        "--api-url",
        type=str,
        default="http://localhost:8080",
        help="API URL (default: http://localhost:8080)"
    )
    parser.add_argument(
        "--prometheus-url",
        type=str,
        default="http://localhost:9090",
        help="Prometheus URL (default: http://localhost:9090)"
    )

    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("╔══════════════════════════════════════════════════════════════════╗")
    print("║           EVIDENCE COLLECTION FOR DELIVERABLES                   ║")
    print("╚══════════════════════════════════════════════════════════════════╝")
    print(f"\nOutput directory: {output_dir.absolute()}\n")

    # Collect all evidence
    collect_availability_report(output_dir, args.prometheus_url)
    collect_model_update_verification(output_dir, args.prometheus_url)
    collect_sample_api_responses(output_dir, args.api_url)
    collect_model_registry_info(output_dir)
    collect_git_history(output_dir)
    collect_system_info(output_dir)
    collect_logs_sample(output_dir)
    create_evidence_summary(output_dir)

    print("\n" + "=" * 70)
    print("✅ Evidence collection complete!")
    print(f"📁 All evidence saved to: {output_dir.absolute()}")
    print("=" * 70)


if __name__ == "__main__":
    main()
