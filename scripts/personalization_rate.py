# scripts/personalization_rate.py
import os, json, time, random
from datetime import datetime, timedelta
from confluent_kafka import Consumer

# Environment setup
BOOTSTRAP = os.environ["KAFKA_BOOTSTRAP"]
API_KEY = os.environ["KAFKA_API_KEY"]
API_SECRET = os.environ["KAFKA_API_SECRET"]
TEAM = os.environ.get("KAFKA_TEAM", "team")
TOPIC = f"{TEAM}.reco_responses"

conf = {
    'bootstrap.servers': BOOTSTRAP,
    'security.protocol': 'SASL_SSL',
    'sasl.mechanisms': 'PLAIN',
    'sasl.username': API_KEY,
    'sasl.password': API_SECRET,
    'group.id': 'personalization-metrics',
    'auto.offset.reset': 'earliest'
}
c = Consumer(conf)

# Mock personalization rule for testing
def is_personalized(record):
    # Treat even user_ids as personalized, odd as non-personalized
    return record["user_id"] % 2 == 0

# Main aggregation logic
def main():
    cutoff = int((datetime.utcnow() - timedelta(hours=24)).timestamp() * 1000)
    total = personalized = 0

    c.subscribe([TOPIC])
    start = time.time()

    # Collect up to 100 messages or stop after 10 s
    while total < 100 and (time.time() - start) < 10:
        msg = c.poll(1.0)
        if msg is None:
            continue
        raw = msg.value()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            print("Skipping invalid message:", raw)
            continue
        if data["ts"] < cutoff:
            continue
        total += 1
        if is_personalized(data):
            personalized += 1

    c.close()
    pct = (personalized / total * 100) if total else 0
    print(f"Personalized responses in last 24 h: {personalized}/{total} ({pct:.1f} %)")


if __name__ == "__main__":
    main()
