import builtins
import json
import pytest
from stream.ingestor import StreamIngestor, TOPIC_SCHEMAS

def test_validate_message_error(monkeypatch):
    ing = StreamIngestor(use_s3=False)
    # force json error
    bad = ing._validate_and_deserialize("team.watch", b"{bad json}")
    assert bad is None

def test_s3_write_branch(monkeypatch, tmp_path):
    import io
    import types

    class DummyS3:
        def put_object(self, **kwargs):  # pretend S3 upload succeeds
            return True

    ing = StreamIngestor(storage_path=str(tmp_path), use_s3=True,
                         s3_bucket="bucket", s3_prefix="snapshots")
    ing.s3_client = DummyS3()

    # fake a simple batch
    batch = [{"user_id": 1, "movie_id": 2, "timestamp": "2025-01-01T00:00:00Z"}]
    ing._write_batch_to_parquet("watch", batch)

def test_run_interrupt(monkeypatch, tmp_path):
    ing = StreamIngestor(storage_path=str(tmp_path), use_s3=False)

    class DummyConsumer:
        def poll(self, timeout): raise KeyboardInterrupt()
        def close(self): pass
    ing.consumer = DummyConsumer()

    # should hit KeyboardInterrupt and flush
    ing.run(timeout_sec=0.01)

def test_main_entrypoint(monkeypatch):
    import stream.ingestor as ingmod
    called = {}
    def fake_run(self): called["ok"] = True
    monkeypatch.setattr(ingmod.StreamIngestor, "run", fake_run)
    ingmod.main()
    assert "ok" in called
