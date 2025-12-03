import pytest
from unittest.mock import patch, MagicMock
from stream.ingestor import StreamIngestor


def test_flush_batches_triggers_write(tmp_path):
    mock_consumer = MagicMock()
    ing = StreamIngestor(
        storage_path=tmp_path,
        batch_size=2,
        flush_interval_sec=1,
        use_s3=False,
    )
    ing.consumer = mock_consumer
    ing.batches["watch"].append({"user_id": 1, "movie_id": 10, "timestamp": "2025-01-01T00:00:00Z"})
    ing.batches["watch"].append({"user_id": 2, "movie_id": 20, "timestamp": "2025-01-01T00:00:00Z"})
    with patch.object(ing, "_write_batch_to_parquet", return_value=None) as w:
        ing._flush_all_batches()
        w.assert_called_once()


def test_start_and_stop(monkeypatch, tmp_path):
    ing = StreamIngestor(storage_path=tmp_path, use_s3=False)
    # Mock run to return immediately
    monkeypatch.setattr(ing, "run", lambda: None)
    ing.start()
    ing.stop()
    assert not ing._thread.is_alive()


def test_empty_flush_does_not_write(tmp_path):
    ing = StreamIngestor(storage_path=tmp_path, use_s3=False)
    with patch.object(ing, "_write_batch_to_parquet", return_value=None) as w:
        ing._flush_all_batches()
        w.assert_not_called()
