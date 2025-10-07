# Optional: team-local event generator wrapper (implement if needed).
import os, json

# from streamlit import event
from confluent_kafka import Producer, KafkaException


conf = {
    'bootstrap.servers': os.environ.get('KAFKA_BOOTSTRAP'),
    'security.protocol': 'SASL_SSL',
    'sasl.mechanisms': 'PLAIN',
    'sasl.username': os.environ.get('KAFKA_API_KEY'),
    'sasl.password': os.environ.get('KAFKA_API_SECRET'),
}


def produce_test_message(topic: str | None = None):
    """
    Produce one test message to the WATCH_TOPIC (or a dummy message if Kafka is not configured).
    Allows optional topic override for test compatibility.
    """
    topic = topic or os.environ.get('WATCH_TOPIC', 'myteam.watch')
    event = {'ts': 1, 'user_id': 1, 'movie_id': 50, 'minute': 1}

    # Mock mode (for CI)
    if not conf.get('bootstrap.servers'):
        print(f"[mock-produce] {event} to {topic}")
        return f"Produced mock message to {topic}"
        #return {"status": "Produced (mock)", "topic": topic, "event": event}

    try:
        p = Producer(conf)
        p.produce(topic, json.dumps(event).encode('utf-8'))
        p.flush()
        print(f"Produced: {event} to {topic}")
        return {"status": "sent", "topic": topic, "event": event}
    except KafkaException as e:
        print(f"[warn] Kafka produce failed: {e}")
        return {"status": "error", "error": str(e), "topic": topic, "event": event}


def main():
    """Manual test entrypoint for local debugging."""
    return produce_test_message()


if __name__ == '__main__':
    main()
