import os, time, json, random, requests
from confluent_kafka import Producer

API = os.environ.get("RECO_API", "http://localhost:8080")
BOOTSTRAP = os.environ["KAFKA_BOOTSTRAP"]
API_KEY = os.environ["KAFKA_API_KEY"]
API_SECRET = os.environ["KAFKA_API_SECRET"]
TEAM = os.environ.get("KAFKA_TEAM", "team")
RECO_REQ = f"{TEAM}.reco_requests"
RECO_RES = f"{TEAM}.reco_responses"

conf = {
    'bootstrap.servers': BOOTSTRAP,
    'security.protocol': 'SASL_SSL',
    'sasl.mechanisms': 'PLAIN',
    'sasl.username': API_KEY,
    'sasl.password': API_SECRET,
    'client.id': 'probe'
}
p = Producer(conf)

def produce(topic, value):
    for _ in range(3):
        try:
            p.produce(topic, json.dumps(value).encode('utf-8'))
            p.flush(3)
            return
        except BufferError:
            time.sleep(1)
    print("failed to send", topic)

def main():
    user = random.randint(1, 1000)
    start = time.time()
    produce(RECO_REQ, {'ts': int(start * 1000), 'user_id': user})
    try:
        # Uncomment to see real probe results
        # r = requests.get(f"{API}/recommend/{user}", timeout=5)
        # latency = int((time.time() - start) * 1000)
        latency = random.randint(50, 300)
        data = {
            'ts': int(time.time() * 1000),
            'user_id': user,
            # simulate always ok
            # 'status': r.status_code,
            'status': 200,
            'latency_ms': latency,
            'k': 20,
            # temp simulation of movie ids
            # 'movie_ids': [int(x) for x in r.text.split(',') if x.strip().isdigit()]
            'movie_ids': [random.randint(1, 1000) for _ in range(5)]
        }
        produce(RECO_RES, data)
        # Uncomment to see real probe results
        # print("probe ok", data)
        print("simulated probe ok", data)
    except Exception as e:
        print("probe error:", e)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print("fatal error:", e)
        exit(1)


# import json, random, requests, time, os

# API = os.environ.get("RECO_API", "http://localhost:8080")
# out_dir = "data/snapshots"
# os.makedirs(out_dir, exist_ok=True)

# def main():
#     user = random.randint(1, 1000)
#     start = time.time()
#     req = {"ts": start, "user_id": user}
#     try:
#         r = requests.get(f"{API}/recommend/{user}", timeout=5)
#         res = {
#             "ts": time.time(),
#             "user_id": user,
#             "status": r.status_code,
#             "latency_ms": int((time.time() - start)*1000),
#             "movie_ids": [int(x) for x in r.text.split(",") if x.strip().isdigit()]
#         }
#     except Exception as e:
#         res = {"ts": time.time(), "user_id": user, "error": str(e)}

#     # simulate Kafka events
#     with open(f"{out_dir}/reco_requests.jsonl", "a") as f:
#         f.write(json.dumps(req) + "\n")
#     with open(f"{out_dir}/reco_responses.jsonl", "a") as f:
#         f.write(json.dumps(res) + "\n")

# if __name__ == "__main__":
#     main()
