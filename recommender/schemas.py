"""Schema validation utilities for Kafka messages."""
from __future__ import annotations

import json
from datetime import datetime, timezone
UTC = timezone.utc
from pathlib import Path
from typing import Any, Dict

import fastavro

# Schema definitions for different event types
WATCH_SCHEMA = {
    "type": "record",
    "name": "WatchEvent",
    "fields": [
        {"name": "user_id", "type": "int"},
        {"name": "movie_id", "type": "int"},
        {"name": "timestamp", "type": ["null", "string"], "default": None},
    ],
}

RATE_SCHEMA = {
    "type": "record",
    "name": "RateEvent",
    "fields": [
        {"name": "user_id", "type": "int"},
        {"name": "movie_id", "type": "int"},
        {"name": "rating", "type": "float"},
        {"name": "timestamp", "type": ["null", "string"], "default": None},
    ],
}

RECO_REQUEST_SCHEMA = {
    "type": "record",
    "name": "RecoRequest",
    "fields": [
        {"name": "user_id", "type": "int"},
        {"name": "timestamp", "type": ["null", "string"], "default": None},
    ],
}

RECO_RESPONSE_SCHEMA = {
    "type": "record",
    "name": "RecoResponse",
    "fields": [
        {"name": "user_id", "type": "int"},
        {"name": "movie_ids", "type": {"type": "array", "items": "int"}},
        {"name": "scores", "type": {"type": "array", "items": "float"}},
        {"name": "timestamp", "type": ["null", "string"], "default": None},
    ],
}

# Map topic names to their schemas
TOPIC_SCHEMAS = {
    "watch": WATCH_SCHEMA,
    "rate": RATE_SCHEMA,
    "reco_requests": RECO_REQUEST_SCHEMA,
    "reco_responses": RECO_RESPONSE_SCHEMA,
}


def validate_schema(data: Dict[str, Any], topic_type: str) -> Dict[str, Any]:
    """
    Validate a message against its Avro schema.

    Args:
        data: Dictionary containing the message data
        topic_type: Type of topic (watch, rate, reco_requests, reco_responses)

    Returns:
        Validated (and possibly cleaned) data dictionary

    Raises:
        ValueError: If validation fails or schema not found
    """
    schema = TOPIC_SCHEMAS.get(topic_type)
    if not schema:
        raise ValueError(f"No schema found for topic type {topic_type}")

    # Add timestamp if not present
    if "timestamp" not in data:
        data["timestamp"] = datetime.now(UTC).isoformat()

    try:
        # Additional validation for recommendation responses
        if topic_type == "reco_responses":
            if len(data.get("movie_ids", [])) != len(data.get("scores", [])):
                raise ValueError(
                    "movie_ids and scores arrays must have the same length"
                )

        # Validate schema then validate data with fastavro
        fastavro.parse_schema(schema)  # validates the schema itself
        fastavro.validation.validate(data, schema)  # validates the data
        return data
    except Exception as e:
        raise ValueError(f"Schema validation failed for {topic_type}: {e}")


def validate_message(message: str, topic_type: str) -> Dict[str, Any]:
    """
    Validate a raw message string against its schema.

    Args:
        message: JSON string containing the message
        topic_type: Type of topic (watch, rate, reco_requests, reco_responses)

    Returns:
        Validated and possibly cleaned data dictionary

    Raises:
        ValueError: If validation fails
    """
    try:
        data = json.loads(message)
        return validate_schema(data, topic_type)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in message: {e}")
