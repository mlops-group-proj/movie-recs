"""
Stream ingestor that consumes Kafka messages, validates schemas, and writes to parquet.
Supports both local filesystem and S3 storage.
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

# S3 imports (optional - only used if USE_S3=true)
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
        
        # Initialize S3 client if needed
        if self.use_s3:
            if not S3_AVAILABLE:
                raise ImportError("boto3 is required for S3 storage. Install with: pip install boto3")
            if not self.s3_bucket:
                raise ValueError("S3_BUCKET must be set when USE_S3=true")
            
            self.s3_client = boto3.client(
                's3',
                region_name=os.environ.get("AWS_REGION", "us-east-1"),
                aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
                aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
            )
            print(f"S3 storage enabled: s3://{self.s3_bucket}/{self.s3_prefix}")
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
        """Write a batch of messages to a parquet file (local or S3)."""
        if not batch:
            return

        # Convert to DataFrame
        df = pd.DataFrame(batch)
        
        # Create timestamp-based partition path with year-month-day format
        now = datetime.now(UTC)
        date_str = now.strftime('%Y-%m-%d')
        filename = f"batch_{now.strftime('%Y%m%d_%H%M%S')}.parquet"
        
        if self.use_s3:
            # Write to S3
            s3_key = f"{self.s3_prefix}/{topic_type}/{date_str}/{filename}"
            try:
                # Write to bytes buffer
                import io
                buffer = io.BytesIO()
                df.to_parquet(buffer, index=False)
                buffer.seek(0)
                
                # Upload to S3
                self.s3_client.put_object(
                    Bucket=self.s3_bucket,
                    Key=s3_key,
                    Body=buffer.getvalue()
                )
                print(f"Wrote {len(batch)} records to s3://{self.s3_bucket}/{s3_key}")
            except ClientError as e:
                print(f"Error writing to S3: {e}")
                raise
        else:
            # Write to local filesystem
            partition_path = self.storage_path / topic_type / date_str
            partition_path.mkdir(parents=True, exist_ok=True)
            output_path = partition_path / filename
            df.to_parquet(output_path, index=False)
            print(f"Wrote {len(batch)} records to {output_path}")

    def _flush_batch(self, topic_type: str) -> None:
        """Flush a batch of messages to storage."""
        batch = self.batches[topic_type]
        if batch:
            self._write_batch_to_parquet(topic_type, batch)
            self.batches[topic_type] = []

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

def main():
    """Entry point for running the ingestor."""
    ingestor = StreamIngestor()
    ingestor.run()

if __name__ == "__main__":
    main()