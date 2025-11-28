#!/usr/bin/env python3
"""Simulate user traffic for the movie recommender system."""

import argparse
import random
import time
import requests
from concurrent.futures import ThreadPoolExecutor

API_URL = "http://ec2-54-221-101-86.compute-1.amazonaws.com:8080"

def make_request(user_id: int, k: int = 10) -> dict:
    """Make a recommendation request for a user."""
    try:
        resp = requests.get(f"{API_URL}/recommend/{user_id}", params={"k": k}, timeout=5)
        return {"user_id": user_id, "status": resp.status_code, "success": resp.ok}
    except Exception as e:
        return {"user_id": user_id, "status": 0, "success": False, "error": str(e)}

def simulate_traffic(
    num_requests: int = 100,
    num_users: int = 1000,
    concurrency: int = 5,
    delay: float = 0.2,
    burst: bool = False,
):
    """Simulate user traffic to the recommendation API."""
    print(f"Simulating {num_requests} requests from {num_users} users...")
    print(f"API: {API_URL}")
    print(f"Concurrency: {concurrency}, Delay: {delay}s, Burst mode: {burst}")
    print("-" * 50)

    success_count = 0
    error_count = 0
    start_time = time.time()

    def worker(i):
        nonlocal success_count, error_count
        user_id = random.randint(1, num_users)
        k = random.choice([5, 10, 20])
        result = make_request(user_id, k)

        if result["success"]:
            success_count += 1
        else:
            error_count += 1

        if (i + 1) % 10 == 0:
            print(f"  Progress: {i + 1}/{num_requests} requests")

        if not burst:
            time.sleep(delay + random.uniform(0, delay))

        return result

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        results = list(executor.map(worker, range(num_requests)))

    elapsed = time.time() - start_time
    rps = num_requests / elapsed if elapsed > 0 else 0

    print("-" * 50)
    print(f"Completed in {elapsed:.1f}s ({rps:.1f} req/s)")
    print(f"Success: {success_count}, Errors: {error_count}")
    print(f"Success rate: {100 * success_count / num_requests:.1f}%")

def continuous_simulation(users: int = 1000, rps: float = 2.0):
    """Run continuous simulation at a target requests-per-second rate."""
    print(f"Running continuous simulation at ~{rps} req/s")
    print(f"API: {API_URL}")
    print("Press Ctrl+C to stop")
    print("-" * 50)

    delay = 1.0 / rps
    request_count = 0
    start_time = time.time()

    try:
        while True:
            user_id = random.randint(1, users)
            k = random.choice([5, 10, 20])
            result = make_request(user_id, k)
            request_count += 1

            status = "OK" if result["success"] else f"ERR:{result.get('status', '?')}"
            if request_count % 10 == 0:
                elapsed = time.time() - start_time
                actual_rps = request_count / elapsed if elapsed > 0 else 0
                print(f"  [{request_count}] user={user_id} k={k} -> {status} ({actual_rps:.1f} req/s)")

            time.sleep(delay)
    except KeyboardInterrupt:
        elapsed = time.time() - start_time
        print(f"\nStopped. Total: {request_count} requests in {elapsed:.1f}s")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulate user traffic")
    parser.add_argument("--requests", "-n", type=int, default=100, help="Number of requests")
    parser.add_argument("--users", "-u", type=int, default=1000, help="Number of unique users")
    parser.add_argument("--concurrency", "-c", type=int, default=5, help="Concurrent requests")
    parser.add_argument("--delay", "-d", type=float, default=0.2, help="Delay between requests")
    parser.add_argument("--burst", "-b", action="store_true", help="Burst mode (no delay)")
    parser.add_argument("--continuous", action="store_true", help="Run continuously")
    parser.add_argument("--rps", type=float, default=2.0, help="Target requests/sec (continuous mode)")
    parser.add_argument("--url", type=str, help="Override API URL")

    args = parser.parse_args()

    if args.url:
        API_URL = args.url

    if args.continuous:
        continuous_simulation(users=args.users, rps=args.rps)
    else:
        simulate_traffic(
            num_requests=args.requests,
            num_users=args.users,
            concurrency=args.concurrency,
            delay=args.delay,
            burst=args.burst,
        )
