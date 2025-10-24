"""Integration tests for Kafka consumer with schema validation."""
import json
import os
from unittest.mock import patch

import pytest
from dotenv import load_dotenv

from stream.consumer import consume_one_message
from recommender.schemas import WATCH_SCHEMA, RATE_SCHEMA

# Load environment variables from .env file
load_dotenv()

# Test messages
VALID_WATCH_MESSAGE = {
    "user_id": 123,
    "movie_id": 456,
    "timestamp": "2025-10-20T12:00:00"
}

VALID_RATE_MESSAGE = {
    "user_id": 123,
    "movie_id": 456,
    "rating": 4.5,
    "timestamp": "2025-10-20T12:00:00"
}

INVALID_WATCH_MESSAGE = {
    "user_id": "not_an_integer",
    "movie_id": 456
}

@pytest.fixture
def mock_kafka_env():
    """Mock Kafka environment variables loaded from .env file."""
    # Environment variables are already loaded from .env via load_dotenv()
    # This fixture just ensures they're available during tests
    required_vars = ["KAFKA_BOOTSTRAP", "KAFKA_API_KEY", "KAFKA_API_SECRET"]
    missing = [var for var in required_vars if not os.environ.get(var)]
    if missing:
        pytest.skip(f"Missing required environment variables: {', '.join(missing)}")
    
    # Set WATCH_TOPIC and RATE_TOPIC if not already set
    if not os.environ.get("WATCH_TOPIC"):
        os.environ["WATCH_TOPIC"] = f"{os.environ.get('KAFKA_TEAM', 'myteam')}.watch"
    if not os.environ.get("RATE_TOPIC"):
        os.environ["RATE_TOPIC"] = f"{os.environ.get('KAFKA_TEAM', 'myteam')}.rate"
    
    yield

def test_consume_valid_watch_message(mock_kafka_env):
    """Test consuming a valid watch message."""
    mock_msg = json.dumps(VALID_WATCH_MESSAGE)
    topic = os.environ.get("WATCH_TOPIC", "myteam.watch")
    
    with patch('confluent_kafka.Consumer') as MockConsumer:
        instance = MockConsumer.return_value
        instance.poll.return_value = type('MockMessage', (), {
            'value': lambda: mock_msg.encode('utf-8'),
            'error': lambda: None
        })
        
        result = consume_one_message(topic=topic)
        
        # Verify the message was validated and returned
        assert result == mock_msg
        instance.subscribe.assert_called_with([topic])
        instance.close.assert_called_once()

def test_consume_valid_rate_message(mock_kafka_env):
    """Test consuming a valid rate message."""
    mock_msg = json.dumps(VALID_RATE_MESSAGE)
    topic = os.environ.get("RATE_TOPIC", "myteam.rate")
    
    with patch('confluent_kafka.Consumer') as MockConsumer:
        instance = MockConsumer.return_value
        instance.poll.return_value = type('MockMessage', (), {
            'value': lambda: mock_msg.encode('utf-8'),
            'error': lambda: None
        })
        
        result = consume_one_message(topic=topic)
        
        # Verify the message was validated and returned
        assert result == mock_msg
        instance.subscribe.assert_called_with([topic])
        instance.close.assert_called_once()

def test_consume_invalid_message(mock_kafka_env):
    """Test consuming an invalid message."""
    mock_msg = json.dumps(INVALID_WATCH_MESSAGE)
    topic = os.environ.get("WATCH_TOPIC", "myteam.watch")
    
    with patch('confluent_kafka.Consumer') as MockConsumer:
        instance = MockConsumer.return_value
        instance.poll.return_value = type('MockMessage', (), {
            'value': lambda: mock_msg.encode('utf-8'),
            'error': lambda: None
        })
        
        result = consume_one_message(topic=topic)
        
        # Even with invalid schema, original message should be returned for backward compatibility
        assert result == mock_msg
        instance.subscribe.assert_called_with([topic])
        instance.close.assert_called_once()

def test_consume_no_kafka_credentials():
    """Test consumer fallback behavior when Kafka credentials are missing."""
    # Temporarily clear environment variables
    original_vars = {key: os.environ.get(key) for key in ["KAFKA_BOOTSTRAP", "KAFKA_API_KEY", "KAFKA_API_SECRET"]}
    
    try:
        for key in ["KAFKA_BOOTSTRAP", "KAFKA_API_KEY", "KAFKA_API_SECRET"]:
            if key in os.environ:
                del os.environ[key]
        
        result = consume_one_message(topic="myteam.watch")
        # Should return mock message
        assert "mock" in result.lower()
        assert "hello" in result.lower()
    finally:
        # Restore original environment variables
        for key, value in original_vars.items():
            if value is not None:
                os.environ[key] = value

def test_consume_kafka_error(mock_kafka_env):
    """Test handling of Kafka errors."""
    topic = os.environ.get("WATCH_TOPIC", "myteam.watch")
    
    with patch('confluent_kafka.Consumer') as MockConsumer:
        instance = MockConsumer.return_value
        instance.poll.side_effect = Exception("Kafka connection error")
        
        result = consume_one_message(topic=topic)
        
        # Should return fallback message
        assert "hello" in result.lower()
        assert "mock" in result.lower()
        assert "error" in result.lower()

def test_consume_timeout(mock_kafka_env):
    """Test handling of poll timeout."""
    topic = os.environ.get("WATCH_TOPIC", "myteam.watch")
    
    with patch('confluent_kafka.Consumer') as MockConsumer:
        instance = MockConsumer.return_value
        instance.poll.return_value = None
        
        result = consume_one_message(topic=topic, timeout_sec=0.1)
        
        # Should return timeout message
        assert "timeout" in result.lower()
        instance.close.assert_called_once()