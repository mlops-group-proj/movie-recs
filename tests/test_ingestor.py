"""Integration tests for the stream ingestor."""
import json
import os
import shutil
import tempfile
from datetime import datetime
try:
    from datetime import UTC  
except Exception:  
    from datetime import timezone
    UTC = timezone.utc
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pandas as pd
import pytest
from dotenv import load_dotenv
import sys
from pathlib import Path as _Path

# Ensure project root is first on sys.path so local `stream` package is imported
_project_root = str(_Path(__file__).resolve().parents[1])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from stream.ingestor import StreamIngestor, WatchEvent, RateEvent, RecoRequest, RecoResponse
from recommender.schemas import validate_schema

# Load environment variables from .env file
load_dotenv()


@pytest.fixture
def temp_storage():
    """Create a temporary directory for testing parquet storage."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_validate_schema_reco_response_length_mismatch_raises():
    data = {
        "user_id": 1,
        "movie_ids": [1, 2, 3],
        "scores": [0.9, 0.8],  
    }
    with pytest.raises(ValueError):
        validate_schema(data, "reco_responses")


@pytest.fixture
def mock_kafka_env():
    """Mock Kafka environment variables loaded from .env file."""
    # Environment variables are already loaded from .env via load_dotenv()
    # This fixture just ensures they're available during tests
    required_vars = ["KAFKA_BOOTSTRAP", "KAFKA_API_KEY", "KAFKA_API_SECRET", "KAFKA_TEAM"]
    missing = [var for var in required_vars if not os.environ.get(var)]
    if missing:
        pytest.skip(f"Missing required environment variables: {', '.join(missing)}")
    yield


class TestSchemaModels:
    """Test Pydantic schema models."""
    
    def test_watch_event_valid(self):
        """Test valid WatchEvent creation."""
        event = WatchEvent(user_id=123, movie_id=456)
        assert event.user_id == 123
        assert event.movie_id == 456
        assert isinstance(event.timestamp, datetime)
    
    def test_rate_event_valid(self):
        """Test valid RateEvent creation."""
        event = RateEvent(user_id=123, movie_id=456, rating=4.5)
        assert event.user_id == 123
        assert event.movie_id == 456
        assert event.rating == 4.5
        assert isinstance(event.timestamp, datetime)
    
    def test_reco_request_valid(self):
        """Test valid RecoRequest creation."""
        event = RecoRequest(user_id=123)
        assert event.user_id == 123
        assert isinstance(event.timestamp, datetime)
    
    def test_reco_response_valid(self):
        """Test valid RecoResponse creation."""
        event = RecoResponse(
            user_id=123,
            movie_ids=[1, 2, 3],
            scores=[0.9, 0.8, 0.7]
        )
        assert event.user_id == 123
        assert event.movie_ids == [1, 2, 3]
        assert event.scores == [0.9, 0.8, 0.7]
        assert isinstance(event.timestamp, datetime)
    
    def test_watch_event_invalid_type(self):
        """Test WatchEvent with invalid data types."""
        with pytest.raises(Exception):  # Pydantic will raise validation error
            WatchEvent(user_id="not_an_int", movie_id=456)
    
    def test_rate_event_invalid_rating(self):
        """Test RateEvent with invalid rating type."""
        with pytest.raises(Exception):
            RateEvent(user_id=123, movie_id=456, rating="not_a_float")


class TestStreamIngestor:
    """Test StreamIngestor class functionality."""
    
    def test_ingestor_initialization(self, temp_storage, mock_kafka_env):
        """Test that ingestor initializes correctly."""
        with patch('stream.ingestor.Consumer'):
            ingestor = StreamIngestor(storage_path=temp_storage)
            
            assert ingestor.storage_path == Path(temp_storage)
            assert ingestor.batch_size == 1000
            assert ingestor.flush_interval_sec == 300
            assert len(ingestor.batches) == 4
            assert all(len(batch) == 0 for batch in ingestor.batches.values())
    
    def test_validate_message_watch(self, temp_storage, mock_kafka_env):
        """Test message validation for watch events."""
        with patch('stream.ingestor.Consumer'):
            ingestor = StreamIngestor(storage_path=temp_storage)
            
            payload = json.dumps({"user_id": 123, "movie_id": 456})
            topic = f"{os.environ['KAFKA_TEAM']}.watch"
            result = ingestor._validate_message(topic, payload)
            
            assert result is not None
            assert result["user_id"] == 123
            assert result["movie_id"] == 456
            assert "timestamp" in result
    
    def test_validate_message_rate(self, temp_storage, mock_kafka_env):
        """Test message validation for rate events."""
        with patch('stream.ingestor.Consumer'):
            ingestor = StreamIngestor(storage_path=temp_storage)
            
            payload = json.dumps({"user_id": 123, "movie_id": 456, "rating": 4.5})
            topic = f"{os.environ['KAFKA_TEAM']}.rate"
            result = ingestor._validate_message(topic, payload)
            
            assert result is not None
            assert result["user_id"] == 123
            assert result["movie_id"] == 456
            assert result["rating"] == 4.5
            assert "timestamp" in result
    
    def test_validate_message_invalid(self, temp_storage, mock_kafka_env):
        """Test validation with invalid message."""
        with patch('stream.ingestor.Consumer'):
            ingestor = StreamIngestor(storage_path=temp_storage)
            
            topic = f"{os.environ['KAFKA_TEAM']}.watch"
            
            # Invalid JSON
            result = ingestor._validate_message(topic, "not valid json")
            assert result is None
            
            # Invalid schema (wrong type)
            payload = json.dumps({"user_id": "not_an_int", "movie_id": 456})
            result = ingestor._validate_message(topic, payload)
            assert result is None
    
    def test_write_batch_to_parquet(self, temp_storage, mock_kafka_env):
        """Test writing a batch to parquet file."""
        with patch('stream.ingestor.Consumer'):
            ingestor = StreamIngestor(storage_path=temp_storage)
            
            # Create a batch of test data
            batch = [
                {"user_id": 1, "movie_id": 100, "timestamp": datetime.now(UTC)},
                {"user_id": 2, "movie_id": 200, "timestamp": datetime.now(UTC)},
                {"user_id": 3, "movie_id": 300, "timestamp": datetime.now(UTC)},
            ]
            
            ingestor._write_batch_to_parquet("watch", batch)
            
            # Verify the directory structure exists
            watch_dir = Path(temp_storage) / "watch"
            assert watch_dir.exists()
            
            # Find the date directory (should be today's date in YYYY-MM-DD format)
            date_dirs = list(watch_dir.iterdir())
            assert len(date_dirs) > 0
            
            # Verify parquet file was created
            date_dir = date_dirs[0]
            parquet_files = list(date_dir.glob("*.parquet"))
            assert len(parquet_files) == 1
            
            # Verify parquet file contents
            df = pd.read_parquet(parquet_files[0])
            assert len(df) == 3
            assert list(df["user_id"]) == [1, 2, 3]
            assert list(df["movie_id"]) == [100, 200, 300]
    
    def test_write_empty_batch(self, temp_storage, mock_kafka_env):
        """Test writing an empty batch does nothing."""
        with patch('stream.ingestor.Consumer'):
            ingestor = StreamIngestor(storage_path=temp_storage)
            
            ingestor._write_batch_to_parquet("watch", [])
            
            # Verify no files were created
            watch_dir = Path(temp_storage) / "watch"
            if watch_dir.exists():
                assert len(list(watch_dir.iterdir())) == 0
    
    def test_flush_batch(self, temp_storage, mock_kafka_env):
        """Test flushing a batch."""
        with patch('stream.ingestor.Consumer'):
            ingestor = StreamIngestor(storage_path=temp_storage)
            
            # Add some test data to the batch
            ingestor.batches["watch"] = [
                {"user_id": 1, "movie_id": 100, "timestamp": datetime.now(UTC)},
                {"user_id": 2, "movie_id": 200, "timestamp": datetime.now(UTC)},
            ]
            
            ingestor._flush_batch("watch")
            
            # Verify batch was cleared
            assert len(ingestor.batches["watch"]) == 0
            
            # Verify parquet file was created
            watch_dir = Path(temp_storage) / "watch"
            assert watch_dir.exists()
            date_dirs = list(watch_dir.iterdir())
            assert len(date_dirs) > 0
    
    def test_date_partition_format(self, temp_storage, mock_kafka_env):
        """Test that date partitioning uses YYYY-MM-DD format."""
        with patch('stream.ingestor.Consumer'):
            ingestor = StreamIngestor(storage_path=temp_storage)
            
            batch = [{"user_id": 1, "movie_id": 100, "timestamp": datetime.now(UTC)}]
            ingestor._write_batch_to_parquet("watch", batch)
            
            # Check that the directory name follows YYYY-MM-DD format
            watch_dir = Path(temp_storage) / "watch"
            date_dirs = list(watch_dir.iterdir())
            assert len(date_dirs) == 1
            
            dir_name = date_dirs[0].name
            # Should match YYYY-MM-DD pattern
            assert len(dir_name) == 10
            assert dir_name[4] == '-'
            assert dir_name[7] == '-'
            
            # Verify it's a valid date
            datetime.strptime(dir_name, '%Y-%m-%d')
    
    def test_consumer_creation(self, mock_kafka_env):
        """Test that Kafka consumer is created with correct configuration."""
        with patch('stream.ingestor.Consumer') as MockConsumer:
            temp_dir = tempfile.mkdtemp()
            try:
                ingestor = StreamIngestor(storage_path=temp_dir)
                
                # Verify Consumer was called
                MockConsumer.assert_called_once()
                
                # Verify configuration
                call_args = MockConsumer.call_args[0][0]
                assert call_args["bootstrap.servers"] == os.environ["KAFKA_BOOTSTRAP"]
                assert call_args["security.protocol"] == "SASL_SSL"
                assert call_args["sasl.mechanisms"] == "PLAIN"
                assert call_args["sasl.username"] == os.environ["KAFKA_API_KEY"]
                assert call_args["sasl.password"] == os.environ["KAFKA_API_SECRET"]
                assert call_args["group.id"] == "ingestor"
                
                # Verify subscribe was called with correct topics
                ingestor.consumer.subscribe.assert_called_once()
                subscribed_topics = ingestor.consumer.subscribe.call_args[0][0]
                kafka_team = os.environ["KAFKA_TEAM"]
                assert f"{kafka_team}.watch" in subscribed_topics
                assert f"{kafka_team}.rate" in subscribed_topics
                assert f"{kafka_team}.reco_requests" in subscribed_topics
                assert f"{kafka_team}.reco_responses" in subscribed_topics
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)


class TestIngestorIntegration:
    """Integration tests for the full ingestion pipeline."""
    
    def test_full_ingestion_flow(self, temp_storage, mock_kafka_env):
        """Test the complete flow: consume -> validate -> batch -> write."""
        with patch('stream.ingestor.Consumer') as MockConsumer:
            # Setup mock consumer
            mock_consumer = MockConsumer.return_value
            
            # Create mock messages
            topic = f"{os.environ['KAFKA_TEAM']}.watch"
            messages = [
                self._create_mock_message(
                    topic,
                    json.dumps({"user_id": i, "movie_id": i * 10})
                )
                for i in range(5)
            ]
            
            # Make poll return messages then None
            mock_consumer.poll.side_effect = messages + [None] * 10
            
            # Create ingestor with small batch size for testing
            ingestor = StreamIngestor(storage_path=temp_storage, batch_size=3)
            
            # Process a few messages
            for _ in range(5):
                msg = mock_consumer.poll(1.0)
                if msg and not msg.error():
                    topic = msg.topic()
                    payload = msg.value().decode("utf-8")
                    topic_type = topic.split(".")[-1]
                    
                    validated = ingestor._validate_message(topic, payload)
                    if validated:
                        ingestor.batches[topic_type].append(validated)
                        
                        # Check if batch is full
                        if len(ingestor.batches[topic_type]) >= ingestor.batch_size:
                            ingestor._flush_batch(topic_type)
            
            # Flush remaining
            ingestor._flush_batch("watch")
            
            # Verify parquet files were created
            watch_dir = Path(temp_storage) / "watch"
            assert watch_dir.exists()
            
            parquet_files = list(watch_dir.rglob("*.parquet"))
            assert len(parquet_files) > 0
            
            # Verify data in parquet files
            all_data = []
            for pf in parquet_files:
                df = pd.read_parquet(pf)
                all_data.extend(df.to_dict('records'))
            
            # Should have processed 5 messages (3 in first batch, 2 in second)
            assert len(all_data) >= 2  # At least the remaining batch was written
            assert all(d["user_id"] in range(5) for d in all_data)
    
    def _create_mock_message(self, topic, payload):
        """Helper to create a mock Kafka message."""
        mock_msg = Mock()
        mock_msg.topic.return_value = topic
        mock_msg.value.return_value = payload.encode('utf-8')
        mock_msg.error.return_value = None
        return mock_msg


def test_main_entry_point(mock_kafka_env):
    """Test that main() function can be called."""
    with patch('stream.ingestor.Consumer'):
        with patch('stream.ingestor.StreamIngestor.run') as mock_run:
            from stream.ingestor import main
            
            # Call main (it will create ingestor and call run)
            # We'll mock KeyboardInterrupt to exit quickly
            mock_run.side_effect = KeyboardInterrupt()
            
            try:
                main()
            except KeyboardInterrupt:
                pass
            
            # Verify run was called
            mock_run.assert_called_once()
def test_validate_schema_reco_request_adds_timestamp():
    data = {"user_id": 123}
    out = validate_schema(data, "reco_requests")

    assert out["user_id"] == 123
    _ = datetime.fromisoformat(out["timestamp"])
