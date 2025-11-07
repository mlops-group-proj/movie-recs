import pandas as pd
from pathlib import Path
from recommender import drift

def test_drift_run(tmp_path: Path):
    """Unit test for drift detection with minimal CSVs."""
    # Create small synthetic train/test datasets
    train = pd.DataFrame({"user": [1, 2, 3], "item": [10, 20, 30]})
    test  = pd.DataFrame({"user": [1, 2, 2], "item": [10, 25, 35]})
    train.to_csv(tmp_path / "train.csv", index=False)
    test.to_csv(tmp_path / "test.csv", index=False)

    # Redirect drift.py data/output directories for isolation
    drift.DATA = tmp_path
    drift.OUT = tmp_path

    # Run drift analysis directly (no CLI exit)
    results, drift_flag, out_json = drift.run_drift(threshold=0.25, out_dir=tmp_path)

    # Verify schema validation and metrics output
    assert "drift_metrics" in results
    assert "aggregate" in results
    assert (tmp_path / "drift_metrics.json").exists()
    assert (tmp_path / "drift_plot.png").exists()

    # Ensure the JSON file actually contains data
    content = (tmp_path / "drift_metrics.json").read_text()
    assert "user" in content and "item" in content

    # Optionally check the drift flag value (not deterministic)
    assert isinstance(drift_flag, bool)
