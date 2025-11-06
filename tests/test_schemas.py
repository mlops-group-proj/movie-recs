import json, pathlib
from stream.validate_avro import validate_record

DATA = {
    "watch": {"ts": 1, "user_id": 10, "movie_id": 100, "minute": 5},
    "rate": {"ts": 1, "user_id": 10, "movie_id": 100, "rating": 4},
    "reco_response": {"ts": 1, "user_id": 10, "status": 200,
                      "latency_ms": 120, "k": 10, "movie_ids": [1, 2, 3]},
}

def test_valid_schemas():
    for name, record in DATA.items():
        assert validate_record(record, name), f"{name} schema invalid"

def test_invalid_schema_fails():
    bad = {"ts": "not_a_long"}  # invalid type
    assert not validate_record(bad, "watch")
