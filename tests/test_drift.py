import pandas as pd
from pathlib import Path
from recommender import drift

def test_drift_main(tmp_path: Path):
    # Create minimal train/test CSVs
    train = pd.DataFrame({"user": [1,2,3], "item": [10,20,30]})
    test  = pd.DataFrame({"user": [1,2,2], "item": [10,25,35]})
    train.to_csv(tmp_path / "train.csv", index=False)
    test.to_csv(tmp_path / "test.csv", index=False)

    # Redirect drift paths
    drift.DATA = tmp_path
    drift.OUT = tmp_path

    drift.main()

    # Verify output files
    assert (tmp_path / "drift_metrics.json").exists()
    assert (tmp_path / "drift_plot.png").exists()
