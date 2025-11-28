#!/usr/bin/env python3
"""Simulate daily user traffic - 2000 requests/day with 30-90 second intervals."""

import random
import time
import requests
import signal
import sys
from datetime import datetime

API_URL = "http://ec2-54-221-101-86.compute-1.amazonaws.com:8080"
NUM_USERS = 800
DAILY_REQUESTS = 2000
MIN_DELAY = 30  # seconds
MAX_DELAY = 90  # seconds

# Average delay = 60s, so 2000 requests takes ~33 hours
# To fit 2000 in 24 hours, we need avg delay of 43.2s
# Using 30-90s gives avg of 60s, so ~1440 requests/day
# Adjusting to 30-56s for avg 43s to hit 2000/day

running = True

def signal_handler(sig, frame):
    global running
    print("\nShutting down gracefully...")
    running = False

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def make_request(user_id: int, k: int = 10) -> dict:
    try:
        resp = requests.get(f"{API_URL}/recommend/{user_id}", params={"k": k}, timeout=10)
        return {"user_id": user_id, "status": resp.status_code, "success": resp.ok}
    except Exception as e:
        return {"user_id": user_id, "status": 0, "success": False, "error": str(e)}

def main():
    global running

    print("=" * 60, flush=True)
    print("Daily User Traffic Simulator", flush=True)
    print("=" * 60, flush=True)
    print(f"API: {API_URL}", flush=True)
    print(f"Users: {NUM_USERS}", flush=True)
    print(f"Target: ~{DAILY_REQUESTS} requests/day", flush=True)
    print(f"Delay: {MIN_DELAY}-{MAX_DELAY} seconds between requests", flush=True)
    print("=" * 60, flush=True)
    print("Running indefinitely. Press Ctrl+C to stop.", flush=True)
    print(flush=True)

    request_count = 0
    success_count = 0
    error_count = 0
    start_time = time.time()
    day_start = time.time()
    daily_count = 0

    while running:
        # Make a request
        user_id = random.randint(1, NUM_USERS)
        k = random.choice([5, 10, 20])
        result = make_request(user_id, k)

        request_count += 1
        daily_count += 1

        if result["success"]:
            success_count += 1
            status = "OK"
        else:
            error_count += 1
            status = f"ERR:{result.get('status', '?')}"

        # Log every request with timestamp
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        elapsed = time.time() - start_time
        print(f"[{now}] #{request_count} user={user_id} k={k} -> {status} (daily: {daily_count})", flush=True)

        # Reset daily counter at midnight
        if time.time() - day_start >= 86400:
            print(f"\n--- Day complete: {daily_count} requests ---\n")
            day_start = time.time()
            daily_count = 0

        # Random delay between requests
        delay = random.uniform(MIN_DELAY, MAX_DELAY)

        # Sleep in small increments to allow graceful shutdown
        sleep_end = time.time() + delay
        while running and time.time() < sleep_end:
            time.sleep(1)

    # Final summary
    elapsed = time.time() - start_time
    print()
    print("=" * 60)
    print("Final Summary")
    print("=" * 60)
    print(f"Total requests: {request_count}")
    print(f"Success: {success_count}")
    print(f"Errors: {error_count}")
    print(f"Runtime: {elapsed/3600:.1f} hours")
    if request_count > 0:
        print(f"Success rate: {100*success_count/request_count:.1f}%")

if __name__ == "__main__":
    main()
