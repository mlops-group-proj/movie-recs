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
    ing.batches["watch"].append({"id": 1})
    ing.batches["watch"].append({"id": 2})
    with patch.object(ing, "_write_local", return_value=None) as w:
        ing._flush_batches()
        w.assert_called_once()

def test_start_and_stop(monkeypatch, tmp_path):
    ing = StreamIngestor(storage_path=tmp_path, use_s3=False)
    monkeypatch.setattr(ing, "_consume_forever", lambda: None)
    ing.start()
    ing.stop()
    assert not ing._thread.is_alive()

def test_empty_flush_does_not_write(tmp_path):
    ing = StreamIngestor(storage_path=tmp_path, use_s3=False)
    with patch.object(ing, "_write_local", return_value=None) as w:
        ing._flush_batches()
        w.assert_not_called()
