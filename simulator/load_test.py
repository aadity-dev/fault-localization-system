"""
simulator/load_test.py

Tests INGESTION THROUGHPUT, independent of how many real poles you generated.
This is deliberately separate from a "realistic fault scenario" -- see
DECISIONS.md for why: the brief's 5,000-msg/10s burst target describes
subdivision-wide message VOLUME (heartbeats + retries + duplicates across
many simultaneous events), not one fault producing 5,000 unique pole events.

We reuse real pole_ids from the generated grid (repeating/duplicating them,
which is realistic -- duplicate delivery is an explicit requirement) purely
to generate volume against the /telemetry endpoint, and measure whether the
ingestion pipeline (queue + async worker) keeps up.

Run:
    python simulator/load_test.py --target sustained   # ~500 msg/s for 10s
    python simulator/load_test.py --target burst        # 5000 msgs in 10s
"""

import argparse
import csv
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from telemetry_emitter import build_power_lost_payload, build_heartbeat_payload

INGEST_URL = "http://localhost:8000/telemetry"


def load_pole_sample(path="data/pole_registry.csv", n=500):
    with open(path) as f:
        poles = [p for p in csv.DictReader(f) if p.get("device_id")]
    return random.sample(poles, min(n, len(poles)))


def build_payload_batch(poles, count):
    """Builds `count` payloads by sampling (with repetition) from the pole pool,
    mixing heartbeats and power_lost events, matching realistic proportions."""
    batch = []
    for i in range(count):
        pole = random.choice(poles)
        seq = random.randint(1, 99000)
        if random.random() < 0.15:
            batch.append(build_power_lost_payload(pole, seq))
        else:
            batch.append(build_heartbeat_payload(pole, seq))
    random.shuffle(batch)
    return batch


def fire_batch(batch, url=INGEST_URL, max_workers=50):
    """Sends the whole batch concurrently, returns (success_count, fail_count, elapsed_seconds)."""
    start = time.time()
    successes, failures = 0, 0

    def send(payload):
        try:
            r = requests.post(url, json=payload, timeout=3)
            return r.status_code < 400
        except requests.RequestException:
            return False

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(send, p) for p in batch]
        for future in as_completed(futures):
            if future.result():
                successes += 1
            else:
                failures += 1

    elapsed = time.time() - start
    return successes, failures, elapsed


def run_sustained_test(poles, rate=500, duration=10):
    """Target: >= 500 msg/s sustained, per 02-data-and-systems.md §7."""
    print(f"\n--- Sustained throughput test: {rate} msg/s for {duration}s ---")
    total_sent = 0
    total_ok = 0
    overall_start = time.time()
    for second in range(duration):
        batch = build_payload_batch(poles, rate)
        ok, fail, elapsed = fire_batch(batch)
        total_sent += len(batch)
        total_ok += ok
        print(f"  t+{second}s: sent {len(batch)}, ok {ok}, failed {fail}, took {elapsed:.2f}s")
        sleep_for = max(0, 1 - elapsed)
        time.sleep(sleep_for)
    overall_elapsed = time.time() - overall_start
    print(f"\nTotal: {total_sent} messages, {total_ok} succeeded, "
          f"actual rate {total_sent / overall_elapsed:.1f} msg/s")


def run_burst_test(poles, total=5000, window=10):
    """Target: 5,000 messages in 10s tolerated without data loss, §7."""
    print(f"\n--- Burst test: {total} messages fired as fast as possible ---")
    batch = build_payload_batch(poles, total)
    ok, fail, elapsed = fire_batch(batch, max_workers=100)
    print(f"Sent {total} messages in {elapsed:.2f}s ({total / elapsed:.1f} msg/s achieved)")
    print(f"Succeeded: {ok}  Failed: {fail}  ({fail / total:.1%} loss)")
    if elapsed > window:
        print(f"WARNING: took {elapsed:.2f}s, target window was {window}s")
    if fail > 0:
        print(f"WARNING: {fail} messages failed -- check queue backpressure / timeouts")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=["sustained", "burst"], default="burst")
    parser.add_argument("--pole-file", default="data/pole_registry.csv")
    args = parser.parse_args()

    poles = load_pole_sample(args.pole_file, n=500)
    print(f"Loaded {len(poles)} poles with devices for load generation.")

    if args.target == "sustained":
        run_sustained_test(poles)
    else:
        run_burst_test(poles)