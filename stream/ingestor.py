"""
Stream ingestor that consumes Kafka messages, validates against Avro schemas
from Confluent Schema Registry, and writes hourly Parquet snapshots to S3.
"""
from __future__ import annotations

import io
import json
import os
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv(override=True)
UTC = timezone.utc
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from pydantic import BaseModel, Field


# -------------------------------------------------------------------------
# Pydantic models for Kafka events
# -------------------------------------------------------------------------
class WatchEvent(BaseModel):
    """A user watched a movie."""
    user_id: int
    movie_id: int
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RateEvent(BaseModel):
    """A user rated a movie."""
    user_id: int
    movie_id: int
    rating: float
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RecoRequest(BaseModel):
    """A recommendation request."""
    user_id: int
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RecoResponse(BaseModel):
    """A recommendation response."""
    user_id: int
    movie_ids: List[int]
    scores: List[float]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
from confluent_kafka import Consumer, KafkaException
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer
from confluent_kafka.serialization import SerializationContext, MessageField
import threading

# S3 storage imports
try:
    import boto3
    from botocore.exceptions import ClientError
    S3_AVAILABLE = True
except ImportError:
    S3_AVAILABLE = False

# Topics to consume (watch and rate only for training data)
TOPICS_TO_CONSUME = ["watch", "rate"]

# Schema definitions for each topic type
TOPIC_SCHEMAS = {
    "watch": {
        "type": "record",
        "name": "WatchEvent",
        "fields": [
            {"name": "user_id", "type": "int"},
            {"name": "movie_id", "type": "int"},
            {"name": "ts", "type": "long"}
        ]
    },
    "rate": {
        "type": "record",
        "name": "RateEvent",
        "fields": [
            {"name": "user_id", "type": "int"},
            {"name": "movie_id", "type": "int"},
            {"name": "rating", "type": "float"},
            {"name": "ts", "type": "long"}
        ]
    }
}


class StreamIngestor:
    def __init__(
        self,
        storage_path: str = "data/snapshots",
        batch_size: int = 1000,
        flush_interval_sec: int = 3600,  # 1 hour
        use_s3: bool = False,
        s3_bucket: Optional[str] = None,
        s3_prefix: str = "snapshots",
    ):
        # Storage configuration
        self.use_s3 = use_s3 or os.environ.get("USE_S3", "").lower() == "true"
        self.s3_bucket = s3_bucket or os.environ.get("S3_BUCKET")
        self.s3_prefix = s3_prefix or os.environ.get("S3_PREFIX", "snapshots")
        self._running = False

        # Initialize S3 client if needed
        if self.use_s3:
            if not S3_AVAILABLE:
                raise ImportError("boto3 is required for S3 storage. Install with: pip install boto3")
            if not self.s3_bucket:
                raise ValueError("S3_BUCKET must be set when USE_S3=true")

            # S3 endpoint - use AWS S3 by default, or custom endpoint for MinIO
            endpoint_url = os.environ.get("S3_ENDPOINT_URL")

            self.s3_client = boto3.client(
                's3',
                endpoint_url=endpoint_url,
                aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
                aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
                region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
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
            topic: [] for topic in TOPICS_TO_CONSUME
        }

        # Initialize Schema Registry client for Avro validation
        self.schema_registry = self._create_schema_registry()
        self.deserializers = self._create_deserializers()

        # Create Kafka consumer
        self.consumer = self._create_consumer()

    def _create_schema_registry(self) -> SchemaRegistryClient:
        """Create Schema Registry client for Avro schema validation."""
        sr_url = os.environ.get("SCHEMA_REGISTRY_URL")
        sr_key = os.environ.get("SCHEMA_REGISTRY_API_KEY")
        sr_secret = os.environ.get("SCHEMA_REGISTRY_API_SECRET")

        if not all([sr_url, sr_key, sr_secret]):
            print("WARNING: Schema Registry credentials not set. Avro validation disabled.")
            return None

        conf = {
            "url": sr_url,
            "basic.auth.user.info": f"{sr_key}:{sr_secret}"
        }
        return SchemaRegistryClient(conf)

    def _create_deserializers(self) -> Dict[str, AvroDeserializer]:
        """Create Avro deserializers for each topic."""
        if not self.schema_registry:
            return {}

        deserializers = {}
        kafka_team = os.environ.get("KAFKA_TEAM", "myteam")

        for topic in TOPICS_TO_CONSUME:
            subject = f"{kafka_team}.{topic}-value"
            try:
                # Get latest schema from registry
                schema = self.schema_registry.get_latest_version(subject)
                deserializers[topic] = AvroDeserializer(
                    self.schema_registry,
                    schema.schema.schema_str
                )
                print(f"Loaded Avro schema for {subject} (ID: {schema.schema_id})")
            except Exception as e:
                print(f"WARNING: Could not load schema for {subject}: {e}")

        return deserializers

    def _create_consumer(self) -> Consumer:
        """Create a Kafka consumer with the configured settings."""
        conf = {
            "bootstrap.servers": os.environ["KAFKA_BOOTSTRAP"],
            "security.protocol": "SASL_SSL",
            "sasl.mechanisms": "PLAIN",
            "sasl.username": os.environ["KAFKA_API_KEY"],
            "sasl.password": os.environ["KAFKA_API_SECRET"],
            "group.id": os.environ.get("KAFKA_GROUP", "ingestor"),
            "auto.offset.reset": "earliest",
        }

        consumer = Consumer(conf)
        kafka_team = os.environ.get("KAFKA_TEAM", "myteam")
        topics = [f"{kafka_team}.{topic}" for topic in TOPICS_TO_CONSUME]
        consumer.subscribe(topics)
        print(f"Subscribed to topics: {topics}")
        return consumer

    def _validate_and_deserialize(self, topic: str, payload: bytes) -> Optional[Dict[str, Any]]:
        """Validate and deserialize a message using Avro schema."""
        topic_type = topic.split(".")[-1]

        # If we have an Avro deserializer, use it
        if topic_type in self.deserializers:
            try:
                ctx = SerializationContext(topic, MessageField.VALUE)
                return self.deserializers[topic_type](payload, ctx)
            except Exception:
                # Fall back to JSON parsing (messages may be plain JSON, not Avro wire format)
                pass

        # Fallback: parse as JSON (for messages not using Avro wire format)
        try:
            data = json.loads(payload.decode("utf-8"))
            # Basic validation
            if topic_type == "watch":
                if "user_id" in data and "movie_id" in data:
                    return {
                        "user_id": int(data["user_id"]),
                        "movie_id": int(data["movie_id"]),
                        "timestamp": data.get("timestamp", datetime.now(UTC).isoformat())
                    }
            elif topic_type == "rate":
                if "user_id" in data and "movie_id" in data and "rating" in data:
                    return {
                        "user_id": int(data["user_id"]),
                        "movie_id": int(data["movie_id"]),
                        "rating": float(data["rating"]),
                        "timestamp": data.get("timestamp", datetime.now(UTC).isoformat())
                    }
            return None
        except Exception as e:
            print(f"JSON parsing error for {topic}: {e}")
            return None

    def _write_batch_to_parquet(self, topic_type: str, batch: List[Dict[str, Any]]) -> None:
        """Write a batch of messages to a parquet file."""
        if not batch:
            return

        df = pd.DataFrame(batch)

        # Create hourly partition path
        now = datetime.now(UTC)
        date_str = now.strftime('%Y-%m-%d')
        hour_str = now.strftime('%H')
        filename = f"batch_{now.strftime('%Y%m%d_%H%M%S')}.parquet"

        if self.use_s3:
            s3_key = f"{self.s3_prefix}/{topic_type}/{date_str}/{hour_str}/{filename}"
            try:
                buffer = io.BytesIO()
                df.to_parquet(buffer, index=False)
                buffer.seek(0)

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
            partition_path = self.storage_path / topic_type / date_str / hour_str
            partition_path.mkdir(parents=True, exist_ok=True)
            output_path = partition_path / filename
            df.to_parquet(output_path, index=False)
            print(f"Wrote {len(batch)} records to {output_path}")

    def _flush_batch(self, topic_type: str) -> None:
        """Flush a batch of messages to Parquet storage."""
        batch = self.batches.get(topic_type, [])
        if not batch:
            return

        self._write_batch_to_parquet(topic_type, batch)
        self.batches[topic_type] = []

    def _flush_all_batches(self) -> None:
        """Flush all topic batches to storage."""
        for topic_type in TOPICS_TO_CONSUME:
            self._flush_batch(topic_type)

    def run(self, timeout_sec: float = 1.0) -> None:
        """Main ingestion loop."""
        print("=" * 60)
        print("Stream Ingestor Starting")
        print("=" * 60)
        print(f"Topics: {TOPICS_TO_CONSUME}")
        print(f"Batch size: {self.batch_size}")
        print(f"Flush interval: {self.flush_interval_sec}s ({self.flush_interval_sec/3600:.1f}h)")
        print(f"Storage: {'S3' if self.use_s3 else 'Local'}")
        print("=" * 60)

        self._running = True
        last_flush_time = datetime.now(UTC)
        message_count = 0

        try:
            while self._running:
                msg = self.consumer.poll(timeout_sec)

                if msg is None:
                    # Check if we need to flush based on time
                    now = datetime.now(UTC)
                    if (now - last_flush_time).total_seconds() >= self.flush_interval_sec:
                        print(f"Hourly flush triggered at {now.isoformat()}")
                        self._flush_all_batches()
                        last_flush_time = now
                    continue

                if msg.error():
                    print(f"Kafka error: {msg.error()}")
                    continue

                # Process message
                topic = msg.topic()
                topic_type = topic.split(".")[-1]

                validated = self._validate_and_deserialize(topic, msg.value())
                if validated:
                    self.batches[topic_type].append(validated)
                    message_count += 1

                    if message_count % 100 == 0:
                        print(f"Processed {message_count} messages", flush=True)

                # Check if any batch is full
                for t, batch in self.batches.items():
                    if len(batch) >= self.batch_size:
                        print(f"Batch full for {t}, flushing {len(batch)} records")
                        self._flush_batch(t)

                # Check hourly flush
                now = datetime.now(UTC)
                if (now - last_flush_time).total_seconds() >= self.flush_interval_sec:
                    print(f"Hourly flush triggered at {now.isoformat()}")
                    self._flush_all_batches()
                    last_flush_time = now

        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            print(f"Total messages processed: {message_count}")
            self._flush_all_batches()
            self.consumer.close()

    def start(self):
        """Start the ingestion process in a background thread."""
        print("[Ingestor] Starting background ingestion")
        self._running = True
        self._thread = threading.Thread(target=self.run, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the ingestion process gracefully."""
        print("[Ingestor] Stopping...")
        self._running = False
        if hasattr(self, "_thread") and self._thread.is_alive():
            self._thread.join(timeout=5)

    def is_running(self) -> bool:
        """Return True if the ingestor is running."""
        return self._running

    def flush_and_stop(self) -> None:
        """Flush all batches and stop."""
        self._flush_all_batches()
        self.stop()


def main():
    """Entry point for running the ingestor."""
    ingestor = StreamIngestor()
    ingestor.run()


if __name__ == "__main__":
    main()
