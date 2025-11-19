"""scripts/export_model.py
Promote freshly trained artifacts into the versioned model registry.

Usage example:
    python scripts/export_model.py \
        --source artifacts/latest/als \
        --registry model_registry \
        --model-name als \
        --data-path data/ml1m_prepared/ratings.csv

The script copies the source directory into model_registry/vX.Y/<model-name>/,
creates/updates metadata, and writes the latest version pointer.
"""

from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Dict, Tuple

SEMVER_RE = re.compile(r"^v(?P<major>\d+)\.(?P<minor>\d+)$")


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Export trained artifacts into the registry")
    ap.add_argument("--source", required=True, help="Directory with trained model artifacts")
    ap.add_argument("--registry", default="model_registry", help="Model registry root")
    ap.add_argument("--model-name", default="als", help="Model subdirectory name")
    ap.add_argument("--version", help="Explicit version (vX.Y). Auto-increments when omitted")
    ap.add_argument("--data-path", help="File used for training; SHA256 becomes data_snapshot_id")
    ap.add_argument("--data-snapshot", help="Override for data snapshot id")
    ap.add_argument("--git-sha", help="Git SHA to record (defaults to env or `git rev-parse`)")
    ap.add_argument("--image-digest", default=os.getenv("IMAGE_DIGEST", ""), help="Container image digest")
    ap.add_argument("--dry-run", action="store_true", help="Print actions without writing")
    return ap.parse_args()


def _find_versions(registry: Path) -> list[Tuple[int, int, str]]:
    versions: list[Tuple[int, int, str]] = []
    if not registry.exists():
        return versions
    for child in registry.iterdir():
        if not child.is_dir():
            continue
        m = SEMVER_RE.match(child.name)
        if m:
            versions.append((int(m.group("major")), int(m.group("minor")), child.name))
    versions.sort()
    return versions


def _next_version(registry: Path) -> str:
    versions = _find_versions(registry)
    if not versions:
        return "v0.1"
    major, minor, _ = versions[-1]
    return f"v{major}.{minor + 1}"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_dir(path: Path) -> str:
    h = hashlib.sha256()
    for file in sorted(p for p in path.rglob("*") if p.is_file()):
        rel = file.relative_to(path).as_posix().encode()
        h.update(rel)
        with file.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
    return h.hexdigest()


def _git_sha() -> str:
    env_sha = os.getenv("GITHUB_SHA")
    if env_sha:
        return env_sha
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def _read_model_meta(src: Path) -> Dict:
    meta_path = src / "meta.json"
    if meta_path.exists():
        return json.loads(meta_path.read_text())
    return {}


def export_model(args: argparse.Namespace) -> str:
    source = Path(args.source).resolve()
    registry = Path(args.registry).resolve()
    if not source.exists() or not source.is_dir():
        raise FileNotFoundError(f"Source directory not found: {source}")

    if not registry.exists():
        registry.mkdir(parents=True)

    version = args.version or _next_version(registry)
    if not SEMVER_RE.match(version):
        raise ValueError("Version must match vX.Y (e.g., v0.3)")

    model_dir = registry / version / args.model_name
    if model_dir.exists():
        raise FileExistsError(f"Target directory already exists: {model_dir}")

    version_dir = model_dir.parent
    version_dir.mkdir(parents=True, exist_ok=True)
    snapshot_id = args.data_snapshot
    if snapshot_id is None and args.data_path:
        data_path = Path(args.data_path)
        if not data_path.exists():
            raise FileNotFoundError(f"Training data path missing: {data_path}")
        snapshot_id = _sha256_file(data_path)
    snapshot_id = snapshot_id or ""

    git_sha = args.git_sha or _git_sha()
    exported_by = os.getenv("GITHUB_ACTOR", getpass.getuser())

    if args.dry_run:
        print(f"[dry-run] Would copy {source} -> {model_dir} as version {version}")
        return version

    shutil.copytree(source, model_dir)

    artifact_digest = _sha256_dir(model_dir)
    artifact_size = sum(p.stat().st_size for p in model_dir.rglob("*") if p.is_file())
    metrics = _read_model_meta(model_dir)

    manifest = {
        "version": version,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model_name": args.model_name,
        "artifact_path": str(model_dir),
        "git_sha": git_sha,
        "data_snapshot_id": snapshot_id,
        "image_digest": args.image_digest or "",
        "exported_by": exported_by,
        "artifact_sha": artifact_digest,
        "artifact_size": artifact_size,
        "metrics": metrics,
    }

    (version_dir / "meta.json").write_text(json.dumps(manifest, indent=2))
    (registry / "latest.txt").write_text(version)
    print(f"✅ Exported {args.model_name} -> {model_dir} ({version})")
    return version


def main() -> None:
    args = parse_args()
    export_model(args)


if __name__ == "__main__":
    main()
