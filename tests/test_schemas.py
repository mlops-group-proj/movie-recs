"""Unit tests for schema validation."""
import json
from datetime import datetime

import pytest

from recommender.schemas import (
    validate_message,
    validate_schema,
    WATCH_SCHEMA,
    RATE_SCHEMA,
    RECO_REQUEST_SCHEMA,
    RECO_RESPONSE_SCHEMA,
)

# Valid test messages
VALID_WATCH = {
    "user_id": 123,
    "movie_id": 456
}

VALID_RATE = {
    "user_id": 123,
    "movie_id": 456,
    "rating": 4.5
}

VALID_RECO_REQUEST = {
    "user_id": 123
}

VALID_RECO_RESPONSE = {
    "user_id": 123,
    "movie_ids": [1, 2, 3],
    "scores": [0.9, 0.8, 0.7]
}

# Invalid test messages
INVALID_WATCH = {
    "user_id": "not_an_integer",  # Should be int
    "movie_id": 456
}

INVALID_RATE = {
    "user_id": 123,
    "movie_id": 456,
    "rating": "not_a_float"  # Should be float
}

INVALID_RECO_REQUEST = {
    "wrong_field": 123  # Missing required user_id
}

INVALID_RECO_RESPONSE = {
    "user_id": 123,
    "movie_ids": [1, 2, 3],
    "scores": [0.9, 0.8]  # Length mismatch with movie_ids
}

def test_watch_schema_valid():
    """Test valid watch event schema validation."""
    data = validate_schema(VALID_WATCH, "watch")
    assert "timestamp" in data  # Should add timestamp if missing
    assert data["user_id"] == 123
    assert data["movie_id"] == 456

def test_watch_schema_invalid():
    """Test invalid watch event schema validation."""
    with pytest.raises(ValueError):
        validate_schema(INVALID_WATCH, "watch")

def test_rate_schema_valid():
    """Test valid rate event schema validation."""
    data = validate_schema(VALID_RATE, "rate")
    assert "timestamp" in data
    assert data["rating"] == 4.5

def test_rate_schema_invalid():
    """Test invalid rate event schema validation."""
    with pytest.raises(ValueError):
        validate_schema(INVALID_RATE, "rate")

def test_reco_request_schema_valid():
    """Test valid recommendation request schema validation."""
    data = validate_schema(VALID_RECO_REQUEST, "reco_requests")
    assert "timestamp" in data
    assert data["user_id"] == 123

def test_reco_request_schema_invalid():
    """Test invalid recommendation request schema validation."""
    with pytest.raises(ValueError):
        validate_schema(INVALID_RECO_REQUEST, "reco_requests")

def test_reco_response_schema_valid():
    """Test valid recommendation response schema validation."""
    data = validate_schema(VALID_RECO_RESPONSE, "reco_responses")
    assert "timestamp" in data
    assert len(data["movie_ids"]) == len(data["scores"])

def test_reco_response_schema_invalid():
    """Test invalid recommendation response schema validation."""
    with pytest.raises(ValueError):
        validate_schema(INVALID_RECO_RESPONSE, "reco_responses")

def test_validate_message():
    """Test message string validation."""
    message = json.dumps(VALID_WATCH)
    data = validate_message(message, "watch")
    assert data["user_id"] == 123
    assert "timestamp" in data

def test_validate_message_invalid_json():
    """Test validation of invalid JSON string."""
    with pytest.raises(ValueError):
        validate_message("invalid json", "watch")

def test_validate_message_unknown_topic():
    """Test validation with unknown topic type."""
    message = json.dumps(VALID_WATCH)
    with pytest.raises(ValueError):
        validate_message(message, "unknown_topic")

def test_timestamp_format():
    """Test that added timestamps are in ISO format."""
    data = validate_schema(VALID_WATCH, "watch")
    # Verify the timestamp can be parsed
    timestamp = datetime.fromisoformat(data["timestamp"])
    assert isinstance(timestamp, datetime)