import os
import time
from confluent_kafka import Consumer, KafkaException


def get_kafka_config(group_id=None):
    """Build Kafka configuration from environment variables."""
    return {
        'bootstrap.servers': os.environ.get('KAFKA_BOOTSTRAP'),
        'security.protocol': 'SASL_SSL',
        'sasl.mechanisms': 'PLAIN',
        'sasl.username': os.environ.get('KAFKA_API_KEY'),
        'sasl.password': os.environ.get('KAFKA_API_SECRET'),
        'group.id': group_id or os.environ.get('KAFKA_GROUP', 'ingestor'),
        'auto.offset.reset': 'earliest'
    }


def main():
    """Main consumer loop for continuous message processing."""
    watch = os.environ.get('WATCH_TOPIC', 'myteam.watch')
    rate = os.environ.get('RATE_TOPIC', 'myteam.rate')
    topics = [watch, rate]
    
    conf = get_kafka_config()
    
    # Validate required configuration
    if not conf.get('bootstrap.servers'):
        print("[ERROR] KAFKA_BOOTSTRAP environment variable not set")
        return
    
    c = Consumer(conf)
    c.subscribe(topics)
    print(f"Subscribed to: {topics}")
    
    try:
        while True:
            msg = c.poll(1.0)
            if msg is None:
                continue
            
            if msg.error():
                # Check if it's a fatal error
                if msg.error().fatal():
                    print(f"[FATAL] {msg.error()}")
                    break
                else:
                    print(f"[WARN] {msg.error()}")
                    continue
            
            # TODO: validate schema → write parquet/csv to object storage
            print(msg.topic(), msg.value()[:120])
            c.commit(msg)
            
    except KeyboardInterrupt:
        print("\n[INFO] Shutting down consumer...")
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")
    finally:
        c.close()
        print("[INFO] Consumer closed")


def consume_one_message(topic: str | None = None):
    """
    Consume one message (mock-safe for CI).
    If no Kafka credentials are set, returns a mocked message.
    
    Returns:
        dict: Status dictionary with 'status', 'topic', and optional 'message' or 'error' keys
    """
    conf = get_kafka_config()
    topic = topic or os.environ.get('WATCH_TOPIC', 'myteam.watch')

    # Mock mode for CI/testing
    if not conf.get('bootstrap.servers'):
        print(f"[mock-consume] returning dummy message from {topic}")
        return {
            "status": "mocked",
            "topic": topic,
            "message": {"user_id": 1, "movie_id": 50, "text": "hello world"}
        }

    c = None
    try:
        c = Consumer(conf)
        c.subscribe([topic])
        msg = c.poll(2.0)
        
        if msg is None:
            return {"status": "timeout", "topic": topic}
        
        if msg.error():
            raise KafkaException(msg.error())
        
        record = msg.value().decode("utf-8")
        print(f"Consumed: {record}")
        return {"status": "ok", "topic": topic, "message": record}
        
    except Exception as e:
        print(f"[warn] Kafka consume failed: {e}")
        return {"status": "error", "topic": topic, "error": str(e)}
    finally:
        if c is not None:
            try:
                c.close()
            except Exception:
                pass


if __name__ == '__main__':
    main()