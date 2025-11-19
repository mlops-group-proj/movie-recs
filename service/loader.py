"""Model loading utilities for the FastAPI service.

This module keeps a cached copy of loaded recommenders so that the
`/switch?model=` endpoint can hot-swap model versions without restarting
the container.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Tuple

from recommender.factory import get_recommender

META_FILES = ("meta.json", "meta.yaml", "meta.yml")


class ModelRegistryError(RuntimeError):
    """Raised when a requested model version cannot be loaded."""


def _parse_lightweight_yaml(text: str) -> Dict[str, str]:
    """Parse simple `key: value` YAML without bringing an extra dependency."""
    meta: Dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip().strip("'\"")
    return meta


class ModelManager:
    """Keeps track of loaded recommenders and active version."""

    def __init__(
        self,
        model_name: str,
        version: str,
        registry: str | None = None,
    ) -> None:
        self.model_name = model_name.lower()
        self.registry = Path(registry or os.getenv("MODEL_REGISTRY", "model_registry"))
        self._lock = Lock()
        self._cache: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self._active_key = (self.model_name, version)
        self._activate(self.model_name, version)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _artifact_dir(self, model_name: str, version: str) -> Path:
        path = self.registry / version / model_name
        if not path.exists():
            raise ModelRegistryError(f"Model {model_name} version {version} not found at {path}")
        return path

    def _load_meta(self, model_name: str, version: str) -> Dict[str, Any]:
        model_dir = self._artifact_dir(model_name, version)
        meta: Dict[str, Any] = {}

        model_meta = model_dir / "meta.json"
        if model_meta.exists():
            meta["model"] = json.loads(model_meta.read_text())

        version_dir = model_dir.parent
        for fname in META_FILES:
            candidate = version_dir / fname
            if not candidate.exists():
                continue
            if candidate.suffix == ".json":
                meta["version"] = json.loads(candidate.read_text())
            else:
                meta["version"] = _parse_lightweight_yaml(candidate.read_text())
            break

        meta.setdefault("version", {"version": version})

        # Enrich with container image digest from environment if available
        # This can be set during Docker build or deployment
        container_digest = os.getenv("CONTAINER_IMAGE_DIGEST", meta["version"].get("image_digest", ""))
        meta["version"]["image_digest"] = container_digest

        return meta

    def _activate(self, model_name: str, version: str) -> None:
        key = (model_name, version)
        if key not in self._cache:
            recommender = get_recommender(model_name, version)
            meta = self._load_meta(model_name, version)
            self._cache[key] = {"instance": recommender, "meta": meta}
        self._active_key = key
        os.environ["MODEL_VERSION"] = version

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @property
    def current_version(self) -> str:
        return self._active_key[1]

    def describe_active(self) -> Dict[str, Any]:
        entry = self._cache[self._active_key]
        return {
            "model_name": self._active_key[0],
            "model_version": self._active_key[1],
            "meta": entry.get("meta", {}),
        }

    def recommend(self, user_id: int, k: int = 20) -> Any:
        recommender = self._cache[self._active_key]["instance"]
        return recommender.recommend(user_id, k)

    def switch(self, version: str, model_name: str | None = None) -> Dict[str, Any]:
        model = (model_name or self.model_name).lower()
        with self._lock:
            previous_version = self.current_version
            self._activate(model, version)
            return {
                "model_name": model,
                "model_version": version,
                "previous_version": previous_version,
                "meta": self._cache[(model, version)]["meta"],
            }


def load_model(version: str | None = None) -> ModelManager:
    """Convenience helper primarily for tests."""
    model_name = os.getenv("MODEL_NAME", "als")
    model_version = version or os.getenv("MODEL_VERSION", "v0.3")
    registry = os.getenv("MODEL_REGISTRY", "model_registry")
    return ModelManager(model_name, model_version, registry)
