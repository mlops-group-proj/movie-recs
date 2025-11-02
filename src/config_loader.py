# src/config_loader.py
import os
from pathlib import Path
import yaml
from dotenv import load_dotenv

class DotDict(dict):
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__

def _to_dotdict(d):
    if isinstance(d, dict):
        return DotDict({k: _to_dotdict(v) for k, v in d.items()})
    if isinstance(d, list):
        return [_to_dotdict(x) for x in d]
    return d

def load_config(env: str | None = None):
    """
    Load config with environment override:
      - loads .env
      - resolves env = arg or APP_ENV or 'dev'
      - reads src/config.yaml (or your files) and returns a dot-accessible dict
    """
    load_dotenv()  # enables APP_ENV and other vars from .env

    env = (env or os.getenv("APP_ENV") or "dev").lower()

    # adjust to your layout; here we assume a single config.yaml with sections
    cfg_path = Path(__file__).resolve().parent / "config.yaml"
    with open(cfg_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    # Merge base with env section if you have both
    base = raw.get("base", {})
    env_cfg = raw.get(env, {})
    merged = {**base, **env_cfg}  # shallow merge; deepen if you need

    # allow RATINGS_PATH override
    ratings_override = os.getenv("RATINGS_PATH")
    if ratings_override:
        merged.setdefault("data", {})["ratings_path"] = ratings_override

    merged["env"] = env
    return _to_dotdict(merged)
