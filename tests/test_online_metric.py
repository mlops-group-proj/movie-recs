import json
import pandas as pd
from unittest.mock import MagicMock, patch
from scripts import online_metric

@patch("scripts.online_metric.Consumer")
def test_consume_topic(mock_consumer):
    m = MagicMock()
    m.error.return_value = False
    m.value.return_value = json.dumps(
        {"user_id": 1, "movie_ids": [2,3], "ts": 1731200000}
    ).encode()
    mock_consumer.return_value.poll.side_effect = [m, None]
    df = online_metric.consume_topic("b","k","s","topic",limit=1)
    assert not df.empty
    assert "user_id" in df.columns

def test_compute_success():
    df_reco = pd.DataFrame({
        "user_id": [1],
        "movie_ids": [[10, 20]],
        "ts": [1731200000],
        "model": ["demo"]
    })
    df_watch = pd.DataFrame({
        "user_id": [1],
        "movie_id": [20],
        "ts": [1731200500]
    })
    out = online_metric.compute_success(df_reco, df_watch)
    assert isinstance(out, pd.DataFrame)
    assert "success_rate" in out.columns
