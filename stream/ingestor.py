"""
Stream ingestor that consumes Kafka messages, validates schemas, and writes to parquet.
Supports both local filesystem and S3-compatible storage (MinIO).
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
UTC = timezone.utc
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from confluent_kafka import Consumer, KafkaException
from pydantic import BaseModel, Field
import threading

# S3-compatible storage imports (MinIO uses the same API as S3)
try:
    import boto3
    from botocore.exceptions import ClientError
    S3_AVAILABLE = True
except ImportError:
    S3_AVAILABLE = False

class WatchEvent(BaseModel):
    user_id: int
    movie_id: int
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

class RateEvent(BaseModel):
    user_id: int
    movie_id: int
    rating: float
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

class RecoRequest(BaseModel):
    user_id: int
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

class RecoResponse(BaseModel):
    user_id: int
    movie_ids: List[int]
    scores: List[float]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

# Map topics to their schema models
TOPIC_SCHEMAS = {
    "watch": WatchEvent,
    "rate": RateEvent,
    "reco_requests": RecoRequest,
    "reco_responses": RecoResponse
}

class StreamIngestor:
    def __init__(
        self,
        storage_path: str = "data/snapshots",
        batch_size: int = 1000,
        flush_interval_sec: int = 300,  # 5 minutes
        use_s3: bool = False,
        s3_bucket: Optional[str] = None,
        s3_prefix: str = "snapshots",
    ):
        # Storage configuration
        self.use_s3 = use_s3 or os.environ.get("USE_S3", "").lower() == "true"
        self.s3_bucket = s3_bucket or os.environ.get("S3_BUCKET")
        self.s3_prefix = s3_prefix or os.environ.get("S3_PREFIX", "snapshots")
        self._running = False   # track lifecycle state

        # Initialize S3-compatible client (MinIO) if needed
        if self.use_s3:
            if not S3_AVAILABLE:
                raise ImportError("boto3 is required for S3/MinIO storage. Install with: pip install boto3")
            if not self.s3_bucket:
                raise ValueError("S3_BUCKET must be set when USE_S3=true")

            # MinIO endpoint - defaults to localhost:9000 for local development
            endpoint_url = os.environ.get("S3_ENDPOINT_URL", "http://localhost:9000")

            self.s3_client = boto3.client(
                's3',
                endpoint_url=endpoint_url,
                aws_access_key_id=os.environ.get("MINIO_ACCESS_KEY", os.environ.get("AWS_ACCESS_KEY_ID", "minioadmin")),
                aws_secret_access_key=os.environ.get("MINIO_SECRET_KEY", os.environ.get("AWS_SECRET_ACCESS_KEY", "minioadmin")),
                region_name=os.environ.get("S3_REGION", "us-east-1"),
            )
            print(f"S3-compatible storage enabled: {endpoint_url}/{self.s3_bucket}/{self.s3_prefix}")
        else:
            self.s3_client = None
            self.storage_path = Path(storage_path)
            self.storage_path.mkdir(parents=True, exist_ok=True)
            print(f"Local storage enabled: {self.storage_path}")

        self.batch_size = batch_size
        self.flush_interval_sec = flush_interval_sec
        self.batches: Dict[str, List[Dict[str, Any]]] = {
            "watch": [],
            "rate": [],
            "reco_requests": [],
            "reco_responses": []
        }
        self.consumer = self._create_consumer()

    def _create_consumer(self) -> Consumer:
        """Create a Kafka consumer with the configured settings."""
        conf = {
            "bootstrap.servers": os.environ["KAFKA_BOOTSTRAP"],
            "security.protocol": "SASL_SSL",
            "sasl.mechanisms": "PLAIN",
            "sasl.username": os.environ["KAFKA_API_KEY"],
            "sasl.password": os.environ["KAFKA_API_SECRET"],
            "group.id": "ingestor",
            "auto.offset.reset": "earliest",
        }

        # Subscribe to all topics
        consumer = Consumer(conf)
        topics = [f"{os.environ['KAFKA_TEAM']}.{topic}" for topic in TOPIC_SCHEMAS.keys()]
        consumer.subscribe(topics)
        return consumer

    def _validate_message(self, topic: str, payload: str) -> Optional[Dict[str, Any]]:
        """Validate a message against its schema."""
        try:
            # Remove topic prefix (e.g., "myteam.watch" -> "watch")
            topic_type = topic.split(".")[-1]
            schema = TOPIC_SCHEMAS.get(topic_type)
            if not schema:
                print(f"No schema found for topic {topic}")
                return None

            # Parse JSON and validate against schema
            data = json.loads(payload)
            validated = schema(**data)
            return validated.model_dump()

        except Exception as e:
            print(f"Validation error for topic {topic}: {e}")
            return None

    def _write_batch_to_parquet(self, topic_type: str, batch: List[Dict[str, Any]]) -> None:
        """Write a batch of messages to a parquet file (local or S3/MinIO)."""
        if not batch:
            return

        # Convert to DataFrame
        df = pd.DataFrame(batch)

        # Create timestamp-based partition path with year-month-day format
        now = datetime.now(UTC)
        date_str = now.strftime('%Y-%m-%d')
        filename = f"batch_{now.strftime('%Y%m%d_%H%M%S')}.parquet"

        if self.use_s3:
            # Write to S3/MinIO
            s3_key = f"{self.s3_prefix}/{topic_type}/{date_str}/{filename}"
            try:
                # Write to bytes buffer
                import io
                buffer = io.BytesIO()
                df.to_parquet(buffer, index=False)
                buffer.seek(0)

                # Upload to S3/MinIO
                self.s3_client.put_object(
                    Bucket=self.s3_bucket,
                    Key=s3_key,
                    Body=buffer.getvalue()
                )
                print(f"Wrote {len(batch)} records to s3://{self.s3_bucket}/{s3_key}")
            except ClientError as e:
                print(f"Error writing to S3/MinIO: {e}")
                raise
        else:
            # Write to local filesystem
            partition_path = self.storage_path / topic_type / date_str
            partition_path.mkdir(parents=True, exist_ok=True)
            output_path = partition_path / filename
            df.to_parquet(output_path, index=False)
            print(f"Wrote {len(batch)} records to {output_path}")

    def _flush_batch(self, topic_type: str) -> None:
        """Flush a batch of messages to Parquet storage."""
        batch = self.batches[topic_type]
        if not batch:
            return

        if self.use_s3:
            self._write_batch_to_parquet(topic_type, batch)
        else:
            # Write to Parquet
            self._write_batch_to_parquet(topic_type, batch)
            # Also keep JSONL for inspection/debugging
            self._write_local(topic_type)

        self.batches[topic_type] = []


    def _flush_batches(self) -> None:
        """Flush all topic batches to storage."""
        for topic_type in list(self.batches.keys()):
            self._flush_batch(topic_type)

    def run(self, timeout_sec: float = 1.0) -> None:
        """Main ingestion loop."""
        print("Starting ingestion...")
        last_flush_time = datetime.now(UTC)

        try:
            while True:
                msg = self.consumer.poll(timeout_sec)

                # Handle timeouts
                if msg is None:
                    continue

                # Handle errors
                if msg.error():
                    raise KafkaException(msg.error())

                # Process message
                topic = msg.topic()
                payload = msg.value().decode("utf-8")
                topic_type = topic.split(".")[-1]

                # Validate and store message
                validated = self._validate_message(topic, payload)
                if validated:
                    self.batches[topic_type].append(validated)

                # Check if any batch is full
                for topic_type, batch in self.batches.items():
                    if len(batch) >= self.batch_size:
                        self._flush_batch(topic_type)

                # Check if we need to flush based on time
                now = datetime.now(UTC)
                if (now - last_flush_time).total_seconds() >= self.flush_interval_sec:
                    for topic_type in self.batches:
                        self._flush_batch(topic_type)
                    last_flush_time = now

        except KeyboardInterrupt:
            print("Shutting down...")
        finally:
            # Flush any remaining messages
            for topic_type in self.batches:
                self._flush_batch(topic_type)
            self.consumer.close()

    def _write_local(self, topic: str) -> None:
        """
        Write the current batch for a topic to local storage as JSONL.
        Called automatically when batch_size or flush_interval is reached.
        """
        if topic not in self.batches or not self.batches[topic]:
            return  # nothing to write

        # Ensure storage path exists
        Path(self.storage_path).mkdir(parents=True, exist_ok=True)
        file_path = Path(self.storage_path) / f"{topic}.jsonl"

        # Custom serializer for datetime
        def default_serializer(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

        # Write JSONL
        with open(file_path, "a", encoding="utf-8") as f:
            for msg in self.batches[topic]:
                json.dump(msg, f, default=default_serializer)
                f.write("\n")

        # Clear the batch after writing
        self.batches[topic] = []

        print(f"[Ingestor] Wrote local batch for '{topic}' → {file_path}")

    def _consume_forever(self) -> None:
        """
        Placeholder for continuous Kafka consumption loop.
        In production this would run until stopped.
        """
        print("[Ingestor] _consume_forever() called (mocked in tests)")
        while getattr(self, "_running", False):
            pass


    def start(self):
        """
        Start the ingestion process in a background thread.
        """
        print("[Ingestor] start() called → beginning message consumption")
        self._running = True

        # Launch background thread for _consume_forever
        self._thread = threading.Thread(target=self._consume_forever, daemon=True)
        self._thread.start()

    def stop(self):
        """
        Stop the ingestion process gracefully.
        """
        print("[Ingestor] stop() called → shutting down consumer")
        self._running = False

        # Join thread if it exists
        if hasattr(self, "_thread") and self._thread.is_alive():
            self._thread.join(timeout=2)


    def is_running(self) -> bool:
        """Return True if the ingestor has been started and not stopped."""
        return getattr(self, "_running", False)

    def flush_and_stop(self) -> None:
        """
        Immediately flush all topic batches and stop ingestion.
        Used in unit tests to avoid long loops.
        """
        print("[Ingestor] flush_and_stop() called")
        self._flush_batches()
        self.stop()



def main():
    """Entry point for running the ingestor."""
    ingestor = StreamIngestor()
    ingestor.run()

if __name__ == "__main__":
    main()
