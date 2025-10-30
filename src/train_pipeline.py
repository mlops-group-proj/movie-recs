# src/train_pipeline.py
print(">>> train_pipeline imported", flush=True)

import os
from pathlib import Path

# Load .env if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# Support both module and script execution styles
try:
    from .config_loader import load_config   # python -m src.train_pipeline
except ImportError:
    from config_loader import load_config    # python src/train_pipeline.py

def main():
    print(">>> main() reached", flush=True)

    cfg, env = load_config()

    data = cfg.get("data", {})
    train = cfg.get("train", {})
    logging_cfg = cfg.get("logging", {})
    artifacts_dir = cfg.get("artifacts_dir", r".\artifacts")

    print("=== Training Pipeline ===", flush=True)
    print(f"Environment       : {env}", flush=True)
    print(f"PYTHONPATH        : {os.getenv('PYTHONPATH')}", flush=True)
    print(f"RATINGS_PATH      : {data.get('ratings_path')}", flush=True)
    print(f"Artifacts dir     : {artifacts_dir}", flush=True)
    print(f"Model             : {train.get('model')}", flush=True)
    print(f"Epochs            : {train.get('epochs')}", flush=True)
    print(f"Log level         : {logging_cfg.get('level')}", flush=True)

    # Optional: show the whole resolved config once while debugging
    # print("Resolved config:", cfg, flush=True)

    # Prove env split by writing artifacts/<env>/touch.ok
    repo_root = Path(__file__).resolve().parents[1]
    out_dir = repo_root / artifacts_dir / env
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "touch.ok").write_text("ok", encoding="utf-8")
    print(f"[OK] Wrote {out_dir}\\touch.ok", flush=True)

if __name__ == "__main__":
    print(">>> __main__ guard executing", flush=True)
    main()
