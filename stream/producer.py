import os
import json
from confluent_kafka import Producer, KafkaException


def get_kafka_config():
    """Build Kafka producer configuration from environment variables."""
    return {
        'bootstrap.servers': os.environ.get('KAFKA_BOOTSTRAP'),
        'security.protocol': 'SASL_SSL',
        'sasl.mechanisms': 'PLAIN',
        'sasl.username': os.environ.get('KAFKA_API_KEY'),
        'sasl.password': os.environ.get('KAFKA_API_SECRET'),
    }


def delivery_report(err, msg):
    """Callback for message delivery reports."""
    if err:
        print(f'[ERROR] Delivery failed for {msg.key()}: {err}')
    else:
        print(f'[SUCCESS] Message delivered to {msg.topic()} [{msg.partition()}]')


def produce_test_message(topic: str | None = None):
    """
    Produce one test message to the WATCH_TOPIC (or a dummy message if Kafka is not configured).
    Allows optional topic override for test compatibility.
    
    Returns:
        dict: Status dictionary with 'status', 'topic', 'event', and optional 'error' keys
    """
    topic = topic or os.environ.get('WATCH_TOPIC', 'myteam.watch')
    event = {'ts': 1, 'user_id': 1, 'movie_id': 50, 'minute': 1}
    
    conf = get_kafka_config()

    # Mock mode (for CI/testing)
    if not conf.get('bootstrap.servers'):
        print(f"[mock-produce] {event} to {topic}")
        return {"status": "mocked", "topic": topic, "event": event}

    try:
        p = Producer(conf)
        p.produce(
            topic,
            value=json.dumps(event).encode('utf-8'),
            callback=delivery_report
        )
        p.flush()
        print(f"Produced: {event} to {topic}")
        return {"status": "sent", "topic": topic, "event": event}
        
    except KafkaException as e:
        print(f"[warn] Kafka produce failed: {e}")
        return {"status": "error", "topic": topic, "event": event, "error": str(e)}
    except Exception as e:
        print(f"[error] Unexpected error: {e}")
        return {"status": "error", "topic": topic, "event": event, "error": str(e)}


def main():
    """Manual test entrypoint for local debugging."""
    result = produce_test_message()
    print(f"Result: {result}")
    return result


if __name__ == '__main__':
    main()