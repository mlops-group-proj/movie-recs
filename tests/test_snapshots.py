"""
Test for generating actual snapshot files with the stream ingestor.

This test creates real parquet snapshot files to verify the complete
snapshot generation workflow including partitioning and file structure.
"""
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
UTC = timezone.utc
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd
import pytest
from dotenv import load_dotenv
import sys
from pathlib import Path as _Path

# Ensure project root is first on sys.path so local `stream` package is imported in CI
_project_root = str(_Path(__file__).resolve().parents[1])
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from stream.ingestor import StreamIngestor

# Load environment variables from .env file
load_dotenv()


@pytest.fixture
def snapshot_dir():
    """Create a temporary directory for snapshot testing."""
    temp_dir = tempfile.mkdtemp(prefix="snapshot_test_")
    yield temp_dir
    # Cleanup after test
    shutil.rmtree(temp_dir, ignore_errors=True)


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


def create_mock_kafka_message(topic: str, payload: dict):
    """Helper to create a mock Kafka message."""
    mock_msg = Mock()
    mock_msg.topic.return_value = topic
    mock_msg.value.return_value = json.dumps(payload).encode('utf-8')
    mock_msg.error.return_value = None
    return mock_msg


class TestSnapshotGeneration:
    """Tests for generating snapshot parquet files."""
    
    def test_generate_watch_snapshots(self, snapshot_dir, mock_kafka_env):
        """Test generating watch event snapshots."""
        with patch('stream.ingestor.Consumer') as MockConsumer:
            # Create ingestor with small batch size for testing
            ingestor = StreamIngestor(storage_path=snapshot_dir, batch_size=5)
            
            # Create mock watch messages
            watch_messages = [
                {"user_id": i, "movie_id": i * 10, "timestamp": datetime.now(UTC).isoformat()}
                for i in range(1, 11)
            ]
            
            # Add messages to batch manually
            for msg_data in watch_messages:
                ingestor.batches["watch"].append(msg_data)
            
            # Flush to create snapshot
            ingestor._flush_batch("watch")
            
            # Verify snapshot directory structure
            watch_dir = Path(snapshot_dir) / "watch"
            assert watch_dir.exists(), "Watch directory should exist"
            
            # Verify date partition exists
            date_dirs = list(watch_dir.iterdir())
            assert len(date_dirs) == 1, "Should have one date partition"
            
            # Verify parquet file exists
            parquet_files = list(date_dirs[0].glob("*.parquet"))
            assert len(parquet_files) == 1, "Should have one parquet file"
            
            # Verify parquet content
            df = pd.read_parquet(parquet_files[0])
            assert len(df) == 10, f"Expected 10 records, got {len(df)}"
            assert list(df["user_id"]) == list(range(1, 11))
            assert list(df["movie_id"]) == [i * 10 for i in range(1, 11)]
            
            print(f"\n*  Generated snapshot: {parquet_files[0]}")
            print(f"   Records: {len(df)}")
            print(f"   Size: {parquet_files[0].stat().st_size} bytes")
    
    def test_generate_rate_snapshots(self, snapshot_dir, mock_kafka_env):
        """Test generating rate event snapshots."""
        with patch('stream.ingestor.Consumer') as MockConsumer:
            ingestor = StreamIngestor(storage_path=snapshot_dir, batch_size=3)
            
            # Create mock rate messages
            rate_messages = [
                {
                    "user_id": i,
                    "movie_id": 100 + i,
                    "rating": 3.0 + (i * 0.5),
                    "timestamp": datetime.now(UTC).isoformat()
                }
                for i in range(1, 7)
            ]
            
            # Add messages to batch
            for msg_data in rate_messages:
                ingestor.batches["rate"].append(msg_data)
            
            # Manually flush to create snapshot
            ingestor._flush_batch("rate")
            
            # Verify snapshots created
            rate_dir = Path(snapshot_dir) / "rate"
            assert rate_dir.exists()
            
            # Get all parquet files
            parquet_files = list(rate_dir.rglob("*.parquet"))
            assert len(parquet_files) >= 1, f"Expected at least 1 parquet file, got {len(parquet_files)}"
            
            # Verify total records
            all_data = []
            for pf in parquet_files:
                df = pd.read_parquet(pf)
                all_data.extend(df.to_dict('records'))
            
            assert len(all_data) == 6, f"Expected 6 total records, got {len(all_data)}"
            
            print(f"\n*  Generated {len(parquet_files)} snapshot(s)")
            for pf in parquet_files:
                df = pd.read_parquet(pf)
                print(f"   {pf.name}: {len(df)} records")
    
    def test_generate_all_topic_snapshots(self, snapshot_dir, mock_kafka_env):
        """Test generating snapshots for all topic types."""
        with patch('stream.ingestor.Consumer') as MockConsumer:
            ingestor = StreamIngestor(storage_path=snapshot_dir, batch_size=5)
            
            # Generate data for all topics
            test_data = {
                "watch": [
                    {"user_id": i, "movie_id": i * 10, "timestamp": datetime.now(UTC).isoformat()}
                    for i in range(1, 6)
                ],
                "rate": [
                    {"user_id": i, "movie_id": i * 20, "rating": 4.0, "timestamp": datetime.now(UTC).isoformat()}
                    for i in range(1, 6)
                ],
                "reco_requests": [
                    {"user_id": i, "timestamp": datetime.now(UTC).isoformat()}
                    for i in range(1, 6)
                ],
                "reco_responses": [
                    {
                        "user_id": i,
                        "movie_ids": [i, i+1, i+2],
                        "scores": [0.9, 0.8, 0.7],
                        "timestamp": datetime.now(UTC).isoformat()
                    }
                    for i in range(1, 6)
                ]
            }
            
            # Add data and flush all topics
            for topic, messages in test_data.items():
                for msg_data in messages:
                    ingestor.batches[topic].append(msg_data)
                ingestor._flush_batch(topic)
            
            # Verify all topics have snapshots
            for topic in ["watch", "rate", "reco_requests", "reco_responses"]:
                topic_dir = Path(snapshot_dir) / topic
                assert topic_dir.exists(), f"{topic} directory should exist"
                
                parquet_files = list(topic_dir.rglob("*.parquet"))
                assert len(parquet_files) >= 1, f"{topic} should have at least one snapshot"
                
                # Verify data
                df = pd.read_parquet(parquet_files[0])
                assert len(df) == 5, f"{topic} should have 5 records"
                
                print(f"\n*  {topic}: {parquet_files[0]}")
                print(f"   Records: {len(df)}")
    
    def test_snapshot_date_partitioning(self, snapshot_dir, mock_kafka_env):
        """Test that snapshots are correctly partitioned by date."""
        with patch('stream.ingestor.Consumer') as MockConsumer:
            ingestor = StreamIngestor(storage_path=snapshot_dir, batch_size=3)
            
            # Create data
            messages = [
                {"user_id": i, "movie_id": i, "timestamp": datetime.now(UTC).isoformat()}
                for i in range(1, 4)
            ]
            
            for msg_data in messages:
                ingestor.batches["watch"].append(msg_data)
            
            ingestor._flush_batch("watch")
            
            # Verify directory structure
            watch_dir = Path(snapshot_dir) / "watch"
            date_dirs = list(watch_dir.iterdir())
            
            assert len(date_dirs) == 1
            
            # Verify date format (YYYY-MM-DD)
            date_dir_name = date_dirs[0].name
            assert len(date_dir_name) == 10
            assert date_dir_name[4] == '-'
            assert date_dir_name[7] == '-'
            
            # Should be today's date
            today = datetime.now(UTC).strftime('%Y-%m-%d')
            assert date_dir_name == today, f"Expected {today}, got {date_dir_name}"
            
            print(f"\n*  Date partition: {date_dir_name}")
    
    def test_snapshot_file_naming(self, snapshot_dir, mock_kafka_env):
        """Test that snapshot files have correct naming convention."""
        with patch('stream.ingestor.Consumer') as MockConsumer:
            ingestor = StreamIngestor(storage_path=snapshot_dir, batch_size=2)
            
            # Create data
            messages = [
                {"user_id": i, "movie_id": i, "timestamp": datetime.now(UTC).isoformat()}
                for i in range(1, 3)
            ]
            
            for msg_data in messages:
                ingestor.batches["watch"].append(msg_data)
            
            ingestor._flush_batch("watch")
            
            # Get parquet file
            parquet_files = list(Path(snapshot_dir).rglob("*.parquet"))
            assert len(parquet_files) == 1
            
            filename = parquet_files[0].name
            
            # Verify naming convention: batch_YYYYMMDDHHmmss.parquet
            assert filename.startswith("batch_")
            assert filename.endswith(".parquet")
            assert len(filename) == len("batch_20251024_120000.parquet")
            
            print(f"\n*  Snapshot filename: {filename}")
    
    def test_snapshot_readability(self, snapshot_dir, mock_kafka_env):
        """Test that generated snapshots can be read back correctly."""
        with patch('stream.ingestor.Consumer') as MockConsumer:
            ingestor = StreamIngestor(storage_path=snapshot_dir, batch_size=10)
            
            # Create comprehensive test data
            original_data = [
                {
                    "user_id": i,
                    "movie_id": 100 + i,
                    "rating": 3.0 + (i * 0.5),
                    "timestamp": datetime.now(UTC).isoformat()
                }
                for i in range(1, 11)
            ]
            
            for msg_data in original_data:
                ingestor.batches["rate"].append(msg_data)
            
            ingestor._flush_batch("rate")
            
            # Read back the snapshot
            parquet_files = list(Path(snapshot_dir).rglob("*.parquet"))
            df = pd.read_parquet(parquet_files[0])
            
            # Verify all fields are present
            assert "user_id" in df.columns
            assert "movie_id" in df.columns
            assert "rating" in df.columns
            assert "timestamp" in df.columns
            
            # Verify data integrity
            assert len(df) == 10
            assert df["user_id"].min() == 1
            assert df["user_id"].max() == 10
            assert df["rating"].min() == 3.5
            assert df["rating"].max() == 8.0
            
            print(f"\n*  Snapshot readable with {len(df)} records")
            print(f"   Columns: {list(df.columns)}")
            print(f"   Sample: {df.head(2).to_dict('records')}")


def test_snapshot_generation_manual():
    """
    Manual test to generate snapshots in a specific location.
    Run this test individually to create sample snapshots.
    
    Usage:
        pytest tests/test_snapshots.py::test_snapshot_generation_manual -v -s
    """
    # Load environment variables if not already loaded
    load_dotenv()
    
    # Ensure required environment variables are present
    required_vars = ["KAFKA_BOOTSTRAP", "KAFKA_API_KEY", "KAFKA_API_SECRET", "KAFKA_TEAM"]
    missing = [var for var in required_vars if not os.environ.get(var)]
    if missing:
        pytest.skip(f"Missing required environment variables: {', '.join(missing)}")
    
    output_dir = "data/test_snapshots"
    
    with patch('stream.ingestor.Consumer'):
        ingestor = StreamIngestor(storage_path=output_dir, batch_size=10)
        
        # Generate sample data for all topics
        print(f"\n📁 Generating snapshots in: {output_dir}")
        
        # Watch events
        for i in range(1, 21):
            ingestor.batches["watch"].append({
                "user_id": i,
                "movie_id": 100 + i,
                "timestamp": datetime.now(UTC).isoformat()
            })
        ingestor._flush_batch("watch")
        
        # Rate events
        for i in range(1, 16):
            ingestor.batches["rate"].append({
                "user_id": i,
                "movie_id": 200 + i,
                "rating": 3.0 + (i % 5) * 0.5,
                "timestamp": datetime.now(UTC).isoformat()
            })
        ingestor._flush_batch("rate")
        
        print(f"\n*  Snapshots generated successfully!")
        print(f"   Location: {Path(output_dir).absolute()}")
        
        # List generated files
        for topic in ["watch", "rate"]:
            topic_files = list(Path(output_dir).glob(f"{topic}/**/*.parquet"))
            for f in topic_files:
                df = pd.read_parquet(f)
                print(f"   📄 {f.relative_to(output_dir)}: {len(df)} records")
if __name__ == "__main__":
    # Run the manual test to generate sample snapshots
    test_snapshot_generation_manual()
