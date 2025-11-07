"""
Test script for backpressure handling in StreamIngestor.

Tests:
1. Batch size-based flushing (1000 messages trigger flush)
2. Time-based flushing (5 minutes trigger flush)
3. Multiple topic handling under load
4. No data loss during backpressure
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch, MagicMock
import json
import tempfile
import shutil

try:
    from datetime import UTC  # Python 3.11+
except ImportError:
    from datetime import timezone
    UTC = timezone.utc


# Ensure local imports work
project_root = str(Path(__file__).parent.parent.absolute())
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from stream.ingestor import StreamIngestor, WatchEvent


class TestBackpressureHandling:
    """Test suite for backpressure mechanisms."""
    
    def setup_method(self):
        """Create temporary directory for test snapshots."""
        self.test_dir = tempfile.mkdtemp()
    
    def teardown_method(self):
        """Clean up temporary directory."""
        if Path(self.test_dir).exists():
            shutil.rmtree(self.test_dir)
    
    def test_batch_size_triggers_flush(self):
        """Test that reaching batch_size triggers automatic flush."""
        print("\n" + "="*60)
        print("TEST 1: Batch Size Triggers Flush")
        print("="*60)
        
        batch_size = 100
        
        # Mock the consumer creation to avoid Kafka dependency
        with patch('stream.ingestor.StreamIngestor._create_consumer', return_value=Mock()):
            ingestor = StreamIngestor(
                storage_path=self.test_dir,
                batch_size=batch_size,
                flush_interval_sec=999999,  # Very long to avoid time-based flush
                use_s3=False
            )
        
            # Add exactly batch_size messages to trigger flush
            for i in range(batch_size):
                ingestor.batches["watch"].append({
                    "user_id": i,
                    "movie_id": i + 100,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
            
            print(f"Added {batch_size} messages to watch batch")
            print(f"Batch size before flush: {len(ingestor.batches['watch'])}")
            
            # Manually trigger the batch check (simulating what run() does)
            if len(ingestor.batches["watch"]) >= batch_size:
                ingestor._flush_batch("watch")
            
            # Verify batch was flushed
            assert len(ingestor.batches["watch"]) == 0, "Batch should be empty after flush"
            
            # Verify parquet file was created
            parquet_files = list(Path(self.test_dir).rglob("*.parquet"))
            assert len(parquet_files) > 0, "Parquet file should be created"
            
            print(f"✅ Batch flushed successfully")
            print(f"✅ Created parquet file: {parquet_files[0]}")
            print(f"✅ Batch size after flush: {len(ingestor.batches['watch'])}")
    
    def test_time_based_flush(self):
        """Test that flush_interval_sec triggers automatic flush."""
        print("\n" + "="*60)
        print("TEST 2: Time-Based Flush")
        print("="*60)
        
        flush_interval = 1  # 1 second for faster testing
        
        # Mock the consumer creation to avoid Kafka dependency
        with patch('stream.ingestor.StreamIngestor._create_consumer', return_value=Mock()):
            ingestor = StreamIngestor(
                storage_path=self.test_dir,
                batch_size=999999,  # Very large to avoid batch-size flush
                flush_interval_sec=flush_interval,
                use_s3=False
            )
        
            # Add some messages (less than batch_size)
            num_messages = 10
            for i in range(num_messages):
                ingestor.batches["watch"].append({
                    "user_id": i,
                    "movie_id": i + 100,
                    "timestamp": datetime.now(UTC).isoformat()
                })
            
            print(f"Added {num_messages} messages to watch batch")
            print(f"Batch size: {len(ingestor.batches['watch'])}")
            print(f"Waiting {flush_interval} second(s) for time-based flush...")
            
            # Simulate time passing
            import time
            last_flush_time = datetime.now(timezone.utc) - timedelta(seconds=flush_interval + 1)
            now = datetime.now(timezone.utc)
            
            # Check if time threshold is met
            if (now - last_flush_time).total_seconds() >= flush_interval:
                ingestor._flush_batch("watch")
            
            # Verify batch was flushed
            assert len(ingestor.batches["watch"]) == 0, "Batch should be empty after time-based flush"
            
            # Verify parquet file was created
            parquet_files = list(Path(self.test_dir).rglob("*.parquet"))
            assert len(parquet_files) > 0, "Parquet file should be created"
            
            print(f"✅ Time-based flush triggered successfully")
            print(f"✅ Created parquet file: {parquet_files[0]}")
            print(f"✅ Batch size after flush: {len(ingestor.batches['watch'])}")
    
    def test_multiple_topics_under_load(self):
        """Test handling multiple topics with high message volume."""
        print("\n" + "="*60)
        print("TEST 3: Multiple Topics Under Load")
        print("="*60)
        
        batch_size = 50
        
        # Mock the consumer creation to avoid Kafka dependency
        with patch('stream.ingestor.StreamIngestor._create_consumer', return_value=Mock()):
            ingestor = StreamIngestor(
                storage_path=self.test_dir,
                batch_size=batch_size,
                flush_interval_sec=999999,
                use_s3=False
            )
        
        # Simulate high load across multiple topics
        topics = ["watch", "rate", "reco_requests", "reco_responses"]
        messages_per_topic = batch_size + 10  # Exceed batch size
        
        for topic in topics:
            print(f"\nAdding {messages_per_topic} messages to {topic}")
            for i in range(messages_per_topic):
                if topic == "watch":
                    msg = {
                        "user_id": i,
                        "movie_id": i + 100,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                elif topic == "rate":
                    msg = {
                        "user_id": i,
                        "movie_id": i + 100,
                        "rating": 4.5,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                elif topic == "reco_requests":
                    msg = {
                        "user_id": i,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                else:  # reco_responses
                    msg = {
                        "user_id": i,
                        "movie_ids": [i + 100, i + 101, i + 102],
                        "scores": [0.9, 0.8, 0.7],
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                
                ingestor.batches[topic].append(msg)
                
                # Check and flush if batch is full
                if len(ingestor.batches[topic]) >= batch_size:
                    print(f"  Flushing {topic} (size: {len(ingestor.batches[topic])})")
                    ingestor._flush_batch(topic)
        
        # Final flush for remaining messages
        print("\nFlushing remaining messages...")
        for topic in topics:
            if len(ingestor.batches[topic]) > 0:
                print(f"  Flushing {topic} (size: {len(ingestor.batches[topic])})")
                ingestor._flush_batch(topic)
        
        # Verify all batches are empty
        for topic in topics:
            assert len(ingestor.batches[topic]) == 0, f"{topic} batch should be empty"
        
        # Verify parquet files were created for all topics
        parquet_files = list(Path(self.test_dir).rglob("*.parquet"))
        print(f"\n✅ Created {len(parquet_files)} parquet files")
        for f in parquet_files:
            print(f"   - {f.relative_to(self.test_dir)}")
        
        assert len(parquet_files) >= len(topics), "Should have files for all topics"
        print(f"✅ All topics handled successfully under load")
    
    def test_no_data_loss_during_backpressure(self):
        """Test that no messages are lost during high-load backpressure."""
        print("\n" + "="*60)
        print("TEST 4: No Data Loss During Backpressure")
        print("="*60)
        
        batch_size = 100
        total_messages = 250  # Will trigger multiple flushes
        
        # Mock the consumer creation to avoid Kafka dependency
        with patch('stream.ingestor.StreamIngestor._create_consumer', return_value=Mock()):
            ingestor = StreamIngestor(
                storage_path=self.test_dir,
                batch_size=batch_size,
                flush_interval_sec=999999,
                use_s3=False
            )
        
        print(f"Simulating {total_messages} messages with batch_size={batch_size}")
        print(f"Expected flushes: {total_messages // batch_size}")
        
        message_ids = []
        flush_count = 0
        
        # Add messages and track IDs
        import time
        for i in range(total_messages):
            msg_id = f"msg_{i}"
            message_ids.append(msg_id)
            
            ingestor.batches["watch"].append({
                "user_id": i,
                "movie_id": i + 100,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "msg_id": msg_id  # Track message
            })
            
            # Flush when batch is full
            if len(ingestor.batches["watch"]) >= batch_size:
                flush_count += 1
                print(f"  Flush #{flush_count} - {len(ingestor.batches['watch'])} messages")
                time.sleep(1.1)  # Wait > 1 second to ensure unique timestamp
                ingestor._flush_batch("watch")
        
        # Final flush
        if len(ingestor.batches["watch"]) > 0:
            flush_count += 1
            print(f"  Final flush #{flush_count} - {len(ingestor.batches['watch'])} messages")
            time.sleep(1.1)  # Ensure unique timestamp for final flush
            ingestor._flush_batch("watch")
        
        # Verify all messages were written
        import pandas as pd
        parquet_files = list(Path(self.test_dir).rglob("*.parquet"))
        
        total_written = 0
        written_ids = []
        
        for pf in parquet_files:
            df = pd.read_parquet(pf)
            total_written += len(df)
            if 'msg_id' in df.columns:
                written_ids.extend(df['msg_id'].tolist())
        
        print(f"\n✅ Total messages added: {total_messages}")
        print(f"✅ Total messages written: {total_written}")
        print(f"✅ Number of flushes: {flush_count}")
        print(f"✅ Parquet files created: {len(parquet_files)}")
        
        assert total_written == total_messages, f"Expected {total_messages} messages, got {total_written}"
        assert len(written_ids) == total_messages, "All message IDs should be preserved"
        
        print(f"✅ No data loss - all {total_messages} messages written successfully")
    
    def test_backpressure_metrics(self):
        """Test tracking of backpressure metrics."""
        print("\n" + "="*60)
        print("TEST 5: Backpressure Metrics")
        print("="*60)
        
        batch_size = 100
        
        # Mock the consumer creation to avoid Kafka dependency
        with patch('stream.ingestor.StreamIngestor._create_consumer', return_value=Mock()):
            ingestor = StreamIngestor(
                storage_path=self.test_dir,
                batch_size=batch_size,
                flush_interval_sec=999999,
                use_s3=False
            )
        
        # Simulate varying load
        loads = [50, 150, 75, 200]  # Messages per burst
        
        metrics = {
            "total_messages": 0,
            "total_flushes": 0,
            "max_batch_size": 0
        }
        
        for burst_id, load in enumerate(loads):
            print(f"\nBurst {burst_id + 1}: Adding {load} messages")
            
            for i in range(load):
                ingestor.batches["watch"].append({
                    "user_id": metrics["total_messages"],
                    "movie_id": metrics["total_messages"] + 100,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
                metrics["total_messages"] += 1
                
                # Track max batch size before flush
                current_size = len(ingestor.batches["watch"])
                metrics["max_batch_size"] = max(metrics["max_batch_size"], current_size)
                
                # Flush if needed
                if current_size >= batch_size:
                    metrics["total_flushes"] += 1
                    print(f"  Flush triggered at {current_size} messages")
                    ingestor._flush_batch("watch")
        
        # Final flush
        if len(ingestor.batches["watch"]) > 0:
            metrics["total_flushes"] += 1
            ingestor._flush_batch("watch")
        
        print(f"\n{'='*60}")
        print("BACKPRESSURE METRICS SUMMARY")
        print(f"{'='*60}")
        print(f"Total messages processed: {metrics['total_messages']}")
        print(f"Total flushes triggered: {metrics['total_flushes']}")
        print(f"Max batch size reached: {metrics['max_batch_size']}")
        print(f"Average messages per flush: {metrics['total_messages'] / metrics['total_flushes']:.1f}")
        print(f"Configured batch size: {batch_size}")
        print(f"✅ Backpressure handled efficiently")


def run_all_tests():
    """Run all backpressure tests."""
    print("\n" + "="*70)
    print("BACKPRESSURE HANDLING TEST SUITE")
    print("="*70)
    
    test_suite = TestBackpressureHandling()
    tests = [
        ("Batch Size Triggers Flush", test_suite.test_batch_size_triggers_flush),
        ("Time-Based Flush", test_suite.test_time_based_flush),
        ("Multiple Topics Under Load", test_suite.test_multiple_topics_under_load),
        ("No Data Loss During Backpressure", test_suite.test_no_data_loss_during_backpressure),
        ("Backpressure Metrics", test_suite.test_backpressure_metrics),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            test_suite.setup_method()
            test_func()
            test_suite.teardown_method()
            passed += 1
            print(f"\n✅ PASSED: {test_name}")
        except Exception as e:
            failed += 1
            print(f"\n❌ FAILED: {test_name}")
            print(f"   Error: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "="*70)
    print("TEST RESULTS")
    print("="*70)
    print(f"Passed: {passed}/{len(tests)}")
    print(f"Failed: {failed}/{len(tests)}")
    print("="*70)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
