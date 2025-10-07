import os, time
from confluent_kafka import Consumer, KafkaException

conf = {
  'bootstrap.servers': os.environ.get('KAFKA_BOOTSTRAP'),
  'security.protocol': 'SASL_SSL',
  'sasl.mechanisms': 'PLAIN',
  'sasl.username': os.environ.get('KAFKA_API_KEY'),
  'sasl.password': os.environ.get('KAFKA_API_SECRET'),
  'group.id': os.environ.get('KAFKA_GROUP','ingestor'),
  'auto.offset.reset': 'earliest'
}

def main():
    watch = os.environ.get('WATCH_TOPIC','myteam.watch')
    rate = os.environ.get('RATE_TOPIC','myteam.rate')
    topics = [watch, rate]
    c = Consumer(conf)
    c.subscribe(topics)
    print(f"Subscribed to: {topics}")
    try:
        while True:
            msg = c.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                print(f"Err: {msg.error()}"); continue
            # TODO: validate schema → write parquet/csv to object storage
            print(msg.topic(), msg.value()[:120])
            c.commit(msg)
    finally:
        c.close()
        
def consume_one_message(topic: str | None = None):
    """
    Consume one message (mock-safe for CI).
    If no Kafka credentials are set, returns a mocked message.
    """
    conf = {
        'bootstrap.servers': os.environ.get('KAFKA_BOOTSTRAP'),
        'security.protocol': 'SASL_SSL',
        'sasl.mechanisms': 'PLAIN',
        'sasl.username': os.environ.get('KAFKA_API_KEY'),
        'sasl.password': os.environ.get('KAFKA_API_SECRET'),
        'group.id': os.environ.get('KAFKA_GROUP', 'ingestor'),
        'auto.offset.reset': 'earliest',
    }

    topic = topic or os.environ.get('WATCH_TOPIC', 'myteam.watch')

    if not conf.get('bootstrap.servers'):
        print(f"[mock-consume] returning dummy message from {topic}")
        return {"status": "mocked", "topic": topic, "message": {"user_id": 1, "movie_id": 50}}

    from confluent_kafka import Consumer, KafkaException
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
        return {"status": "error", "error": str(e)}
    finally:
        try:
            c.close()
        except Exception:
            pass

if __name__ == '__main__':
    main()