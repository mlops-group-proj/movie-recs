#!/usr/bin/env python3
"""Simulate all Kafka events - watch, rate, reco_requests, reco_responses."""

import os
import json
import random
import time
import signal
import sys
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Kafka configuration
KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP")
KAFKA_API_KEY = os.environ.get("KAFKA_API_KEY")
KAFKA_API_SECRET = os.environ.get("KAFKA_API_SECRET")
KAFKA_TEAM = os.environ.get("KAFKA_TEAM", "myteam")

# Topics
TOPICS = {
    "watch": f"{KAFKA_TEAM}.watch",
    "rate": f"{KAFKA_TEAM}.rate",
    "reco_requests": f"{KAFKA_TEAM}.reco_requests",
    "reco_responses": f"{KAFKA_TEAM}.reco_responses",
}

NUM_USERS = 800
NUM_MOVIES = 5000
MIN_DELAY = 10  # seconds between event batches
MAX_DELAY = 30  # seconds

running = True

def signal_handler(sig, frame):
    global running
    print("\nShutting down gracefully...", flush=True)
    running = False

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def create_producer():
    """Create Kafka producer with Confluent Cloud config."""
    if not all([KAFKA_BOOTSTRAP, KAFKA_API_KEY, KAFKA_API_SECRET]):
        print("ERROR: Missing Kafka credentials in environment.", flush=True)
        print("Required: KAFKA_BOOTSTRAP, KAFKA_API_KEY, KAFKA_API_SECRET", flush=True)
        sys.exit(1)

    try:
        from confluent_kafka import Producer
        conf = {
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "security.protocol": "SASL_SSL",
            "sasl.mechanisms": "PLAIN",
            "sasl.username": KAFKA_API_KEY,
            "sasl.password": KAFKA_API_SECRET,
        }
        return Producer(conf)
    except ImportError:
        print("ERROR: confluent-kafka not installed. Run: pip install confluent-kafka", flush=True)
        sys.exit(1)

def generate_watch_event(user_id: int = None, movie_id: int = None) -> dict:
    """Generate a watch event - user watched a movie."""
    return {
        "user_id": user_id or random.randint(1, NUM_USERS),
        "movie_id": movie_id or random.randint(1, NUM_MOVIES),
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

def generate_rate_event(user_id: int = None, movie_id: int = None) -> dict:
    """Generate a rate event - user rated a movie."""
    return {
        "user_id": user_id or random.randint(1, NUM_USERS),
        "movie_id": movie_id or random.randint(1, NUM_MOVIES),
        "rating": random.choice([1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]),
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

def generate_reco_request(user_id: int = None) -> dict:
    """Generate a recommendation request event."""
    return {
        "user_id": user_id or random.randint(1, NUM_USERS),
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

def generate_reco_response(user_id: int = None) -> dict:
    """Generate a recommendation response event."""
    num_recs = random.randint(5, 20)
    movie_ids = random.sample(range(1, NUM_MOVIES), num_recs)
    scores = [round(random.uniform(0.5, 1.0), 3) for _ in range(num_recs)]
    return {
        "user_id": user_id or random.randint(1, NUM_USERS),
        "movie_ids": movie_ids,
        "scores": scores,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

def delivery_callback(err, msg):
    """Callback for Kafka delivery reports."""
    if err:
        print(f"  Delivery failed: {err}", flush=True)

def main():
    global running

    print("=" * 60, flush=True)
    print("Kafka Multi-Topic Event Simulator", flush=True)
    print("=" * 60, flush=True)
    print(f"Bootstrap: {KAFKA_BOOTSTRAP[:30]}..." if KAFKA_BOOTSTRAP else "Not set", flush=True)
    print(f"Topics:", flush=True)
    for name, topic in TOPICS.items():
        print(f"  - {name}: {topic}", flush=True)
    print(f"Users: 1-{NUM_USERS}, Movies: 1-{NUM_MOVIES}", flush=True)
    print(f"Delay: {MIN_DELAY}-{MAX_DELAY}s between batches", flush=True)
    print("=" * 60, flush=True)
    print("Running indefinitely. Press Ctrl+C to stop.", flush=True)
    print(flush=True)

    producer = create_producer()
    batch_count = 0
    event_counts = {name: 0 for name in TOPICS}
    start_time = time.time()

    while running:
        batch_count += 1
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Simulate a user session: request -> response -> watch -> maybe rate
        user_id = random.randint(1, NUM_USERS)

        # 1. Reco request
        event = generate_reco_request(user_id)
        producer.produce(TOPICS["reco_requests"], json.dumps(event).encode(), callback=delivery_callback)
        event_counts["reco_requests"] += 1

        # 2. Reco response
        event = generate_reco_response(user_id)
        recommended_movies = event["movie_ids"][:5]  # Take top 5 for watch simulation
        producer.produce(TOPICS["reco_responses"], json.dumps(event).encode(), callback=delivery_callback)
        event_counts["reco_responses"] += 1

        # 3. Watch events (user watches 1-3 of the recommended movies)
        num_watches = random.randint(1, 3)
        for movie_id in random.sample(recommended_movies, min(num_watches, len(recommended_movies))):
            event = generate_watch_event(user_id, movie_id)
            producer.produce(TOPICS["watch"], json.dumps(event).encode(), callback=delivery_callback)
            event_counts["watch"] += 1

        # 4. Rate event (30% chance user rates a movie they watched)
        if random.random() < 0.3 and recommended_movies:
            movie_id = random.choice(recommended_movies)
            event = generate_rate_event(user_id, movie_id)
            producer.produce(TOPICS["rate"], json.dumps(event).encode(), callback=delivery_callback)
            event_counts["rate"] += 1

        producer.poll(0)  # Trigger callbacks

        # Log progress
        total = sum(event_counts.values())
        print(f"[{now}] Batch #{batch_count} user={user_id} | Total events: {total} "
              f"(watch:{event_counts['watch']} rate:{event_counts['rate']} "
              f"req:{event_counts['reco_requests']} resp:{event_counts['reco_responses']})", flush=True)

        # Random delay between batches
        delay = random.uniform(MIN_DELAY, MAX_DELAY)
        sleep_end = time.time() + delay
        while running and time.time() < sleep_end:
            time.sleep(1)
            producer.poll(0)

    # Flush remaining messages
    print("\nFlushing remaining messages...", flush=True)
    producer.flush(timeout=10)

    elapsed = time.time() - start_time
    total = sum(event_counts.values())
    print(f"\nTotal: {total} events in {elapsed/60:.1f} minutes", flush=True)
    print(f"  watch: {event_counts['watch']}", flush=True)
    print(f"  rate: {event_counts['rate']}", flush=True)
    print(f"  reco_requests: {event_counts['reco_requests']}", flush=True)
    print(f"  reco_responses: {event_counts['reco_responses']}", flush=True)

if __name__ == "__main__":
    main()
