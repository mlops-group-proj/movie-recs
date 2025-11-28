# tests/test_probe_mock.py
import json
import os
from unittest import mock
from scripts import probe


def test_probe_sends_and_records(monkeypatch, capsys):
    """Simulate a probe run with a mocked KafkaProducer and requests.get."""

    # --- Mock env ---
    monkeypatch.setenv("TEAM", "teamx")
    monkeypatch.setenv("RECO_API", "http://fake-api")
    monkeypatch.setenv("KAFKA_BOOTSTRAP", "mock")
    monkeypatch.setenv("KAFKA_API_KEY", "key")
    monkeypatch.setenv("KAFKA_API_SECRET", "secret")

    sent_messages = []

    class MockProducer:
        def __init__(self, *args, **kwargs):
            pass

        def produce(self, *args, **kwargs):
            # Handle both positional and keyword usage
            if len(args) == 2:
                topic, raw_value = args
            elif "topic" in kwargs and "value" in kwargs:
                topic, raw_value = kwargs["topic"], kwargs["value"]
            else:
                topic, raw_value = "unknown", None

            # Decode bytes and load JSON safely
            if isinstance(raw_value, (bytes, bytearray)):
                try:
                    decoded = json.loads(raw_value.decode("utf-8"))
                except Exception:
                    decoded = {"_raw": raw_value.decode("utf-8", errors="ignore")}
            else:
                try:
                    decoded = json.loads(raw_value) if raw_value else {"_raw": None}
                except Exception:
                    decoded = {"_raw": str(raw_value)}

            sent_messages.append({"topic": topic, "value": decoded})

        def flush(self, *args, **kwargs):
            pass


    # --- Patch Kafka + network ---
    with mock.patch("scripts.probe.Producer", MockProducer), \
         mock.patch("scripts.probe.requests.get") as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.elapsed = mock.Mock(total_seconds=lambda: 0.05)
        mock_get.return_value.text = "1,2,3"

        probe.p = None  # ensure fresh mock producer
        data = probe.main_once()

    # --- Assertions ---
    # Show what was captured (for debugging clarity)
    print("Captured messages:", sent_messages)

    assert sent_messages, "No messages captured"
    # Find the last one with user_id or fall back to last message
    msg = None
    for m in reversed(sent_messages):
        if isinstance(m.get("value"), dict) and "user_id" in m["value"]:
            msg = m["value"]
            break
    if msg is None:
        msg = sent_messages[-1]["value"]

    # Validate fields
    for f in ["user_id", "status", "latency_ms", "movie_ids"]:
        assert f in msg, f"Missing field {f}"
    assert isinstance(msg["movie_ids"], list)
    assert msg["status"] == 200
    assert msg["latency_ms"] < 1000

    # Validate stdout output
    out = capsys.readouterr().out
    assert "probe ok" in out.lower()
