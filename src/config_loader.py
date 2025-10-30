# src/config_loader.py
import os
from pathlib import Path
import yaml

DEFAULT_CFG = {
    "data": {
        "ratings_path": r".\data\movielens\ratings.csv",
        "movielens_dir": r".\data\movielens",
    },
    "artifacts_dir": r".\artifacts",
    "train": {
        "model": "als",
        "factors": 64,
        "reg": 0.01,
        "epochs": 10,
    },
    "logging": {"level": "INFO"},
}

def _merge(a: dict, b: dict) -> dict:
    out = dict(a or {})
    for k, v in (b or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out

def _resolve_env(x):
    if isinstance(x, str) and x.startswith("${") and x.endswith("}"):
        return os.getenv(x[2:-1], "")
    if isinstance(x, dict):
        return {k: _resolve_env(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_resolve_env(v) for v in x]
    return x

def _read_yaml(p: Path) -> dict:
    if not p.exists():
        return {}
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data or {}

def load_config():
    repo_root = Path(__file__).resolve().parents[1]
    cfg_dir = repo_root / "configs"
    env = os.getenv("APP_ENV", "dev").lower()

    base_path = cfg_dir / "base.yaml"
    env_path = cfg_dir / f"{env}.yaml"

    base = _read_yaml(base_path)
    env_cfg = _read_yaml(env_path)

    # Apply defaults first, then base, then env
    cfg = _merge(DEFAULT_CFG, base)
    cfg = _merge(cfg, env_cfg)
    cfg = _resolve_env(cfg)

    # Minimal debug line so you know which files were read
    print(f"[config] env={env} base={base_path.exists()} env_file={env_path.name if env_path.exists() else 'N/A'}", flush=True)

    return cfg, env