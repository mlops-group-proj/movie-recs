import os, time
from confluent_kafka import Consumer

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

if __name__ == '__main__':
    main()