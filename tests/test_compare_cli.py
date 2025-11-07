import subprocess, sys

def test_compare_help():
    result = subprocess.run(
        [sys.executable, "experiments/ml1m_baselines/compare.py", "--help"],
        capture_output=True, text=True
    )
    assert "usage" in result.stdout.lower()
