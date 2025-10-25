import os, time, json, random, requests
from confluent_kafka import Producer

# ---------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------
API = os.environ.get("RECO_API", "http://localhost:8080")
BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP", "")
API_KEY = os.environ.get("KAFKA_API_KEY", "")
API_SECRET = os.environ.get("KAFKA_API_SECRET", "")
TEAM = os.environ.get("KAFKA_TEAM", "team")

RECO_REQ = f"{TEAM}.reco_requests"
RECO_RES = f"{TEAM}.reco_responses"

conf = {
    "bootstrap.servers": BOOTSTRAP,
    "security.protocol": "SASL_SSL",
    "sasl.mechanisms": "PLAIN",
    "sasl.username": API_KEY or "dummy",
    "sasl.password": API_SECRET or "dummy",
    "client.id": "probe",
}

# Lazily created producer (can be mocked in tests)
def get_producer():
    return Producer(conf)

p = None  # initialized at runtime


# ---------------------------------------------------------------------
# Helper to produce a message
# ---------------------------------------------------------------------
def produce(topic: str, value: dict):
    """Send a JSON-encoded message to Kafka (retries up to 3 times)."""
    global p
    if p is None:
        p = get_producer()
    for _ in range(3):
        try:
            p.produce(topic, json.dumps(value).encode("utf-8"))
            p.flush(3)
            return True
        except BufferError:
            time.sleep(1)
    print("failed to send", topic)
    return False



# ---------------------------------------------------------------------
# Core probe logic
# ---------------------------------------------------------------------
def run_probe_once():
    """Perform one probe iteration (used by main and tests)."""
    user = random.randint(1, 1000)
    start = time.time()

    # Record request event
    produce(RECO_REQ, {"ts": int(start * 1000), "user_id": user})

    try:
        # --- Real probe (uncomment for production) ---
        # r = requests.get(f"{API}/recommend/{user}", timeout=5)
        # latency = int((time.time() - start) * 1000)
        # status = r.status_code
        # movie_ids = [int(x) for x in r.text.split(",") if x.strip().isdigit()]

        # --- Simulated probe (used in tests) ---
        latency = random.randint(50, 300)
        status = 200
        movie_ids = [random.randint(1, 1000) for _ in range(5)]

        data = {
            "ts": int(time.time() * 1000),
            "user_id": user,
            "status": status,
            "latency_ms": latency,
            "k": 20,
            "movie_ids": movie_ids,
        }

        produce(RECO_RES, data)
        print("simulated probe ok", data)
        return data

    except Exception as e:
        print("probe error:", e)
        return None


# ---------------------------------------------------------------------
# CLI Entrypoints
# ---------------------------------------------------------------------
def main(loop: bool = True):
    """Run probe once or repeatedly (used for cron)."""
    if loop:
        while True:
            run_probe_once()
            time.sleep(60)  # one minute between probes
    else:
        run_probe_once()


def main_once():
    """Run exactly one iteration (for tests)."""
    return run_probe_once()


if __name__ == "__main__":
    try:
        main(loop=True)
    except Exception as e:
        print("fatal error:", e)
        exit(1)
