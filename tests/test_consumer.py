"""Integration tests for Kafka consumer with schema validation."""
import json
import os
from unittest.mock import patch

import pytest

from stream.consumer import consume_one_message
from recommender.schemas import WATCH_SCHEMA, RATE_SCHEMA

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
    """Mock Kafka environment variables."""
    with patch.dict(os.environ, {
        "KAFKA_BOOTSTRAP": "dummy",
        "KAFKA_API_KEY": "dummy",
        "KAFKA_API_SECRET": "dummy",
        "WATCH_TOPIC": "myteam.watch",
        "RATE_TOPIC": "myteam.rate"
    }):
        yield

def test_consume_valid_watch_message(mock_kafka_env):
    """Test consuming a valid watch message."""
    mock_msg = json.dumps(VALID_WATCH_MESSAGE)
    
    with patch('confluent_kafka.Consumer') as MockConsumer:
        instance = MockConsumer.return_value
        instance.poll.return_value = type('MockMessage', (), {
            'value': lambda: mock_msg.encode('utf-8'),
            'error': lambda: None
        })
        
        result = consume_one_message(topic="myteam.watch")
        
        # Verify the message was validated and returned
        assert result == mock_msg
        instance.subscribe.assert_called_with(["myteam.watch"])
        instance.close.assert_called_once()

def test_consume_valid_rate_message(mock_kafka_env):
    """Test consuming a valid rate message."""
    mock_msg = json.dumps(VALID_RATE_MESSAGE)
    
    with patch('confluent_kafka.Consumer') as MockConsumer:
        instance = MockConsumer.return_value
        instance.poll.return_value = type('MockMessage', (), {
            'value': lambda: mock_msg.encode('utf-8'),
            'error': lambda: None
        })
        
        result = consume_one_message(topic="myteam.rate")
        
        # Verify the message was validated and returned
        assert result == mock_msg
        instance.subscribe.assert_called_with(["myteam.rate"])
        instance.close.assert_called_once()

def test_consume_invalid_message(mock_kafka_env):
    """Test consuming an invalid message."""
    mock_msg = json.dumps(INVALID_WATCH_MESSAGE)
    
    with patch('confluent_kafka.Consumer') as MockConsumer:
        instance = MockConsumer.return_value
        instance.poll.return_value = type('MockMessage', (), {
            'value': lambda: mock_msg.encode('utf-8'),
            'error': lambda: None
        })
        
        result = consume_one_message(topic="myteam.watch")
        
        # Even with invalid schema, original message should be returned for backward compatibility
        assert result == mock_msg
        instance.subscribe.assert_called_with(["myteam.watch"])
        instance.close.assert_called_once()

def test_consume_no_kafka_credentials():
    """Test consumer fallback behavior when Kafka credentials are missing."""
    with patch.dict(os.environ, {}, clear=True):
        result = consume_one_message(topic="myteam.watch")
        # Should return mock message
        assert "mock" in result.lower()
        assert "hello" in result.lower()

def test_consume_kafka_error(mock_kafka_env):
    """Test handling of Kafka errors."""
    with patch('confluent_kafka.Consumer') as MockConsumer:
        instance = MockConsumer.return_value
        instance.poll.side_effect = Exception("Kafka connection error")
        
        result = consume_one_message(topic="myteam.watch")
        
        # Should return fallback message
        assert "hello" in result.lower()
        assert "mock" in result.lower()
        assert "error" in result.lower()

def test_consume_timeout(mock_kafka_env):
    """Test handling of poll timeout."""
    with patch('confluent_kafka.Consumer') as MockConsumer:
        instance = MockConsumer.return_value
        instance.poll.return_value = None
        
        result = consume_one_message(topic="myteam.watch", timeout_sec=0.1)
        
        # Should return timeout message
        assert "timeout" in result.lower()
        instance.close.assert_called_once()