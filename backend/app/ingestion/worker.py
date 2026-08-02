"""
backend/app/ingestion/worker.py

Drains the Redis telemetry queue and turns raw messages into pole state,
which is what the graph engine (app/graph/localize.py) actually consumes.

Two jobs, matching the brief's dirty-data rules directly:

1. DEBOUNCE: don't act on a single power_lost instantly. Buffer dark
   signals for a short window before running localization, so a burst of
   messages from one real fault gets processed together rather than
   triggering N separate localization runs (01-problem-context.md, the
   "Debounce (Wait)" pattern from the lying-sensor discussion).

2. DEDUP / ORDERING: use (device_id, seq) to drop duplicates and stale
   retries, per 02-data-and-systems.md §2 -- ts has up to ±90s skew and
   is NOT reliable for cross-device ordering, seq is.

This file intentionally knows nothing about HTTP or FastAPI -- it only
imports from ingestion.queue and graph.*, keeping it testable and
runnable standalone (`python -m app.ingestion.worker`).
"""

import time
from datetime import datetime, timedelta, timezone

from app.ingestion.queue import pop_telemetry

DEBOUNCE_SECONDS = 30       # per 01-problem-context.md's debounce guidance
STALE_RETRY_HOURS = 6        # discard power_lost older than this (§2, "Stale Retries")


class PoleStateTracker:
    """
    In-memory pole state, rebuilt from telemetry as it arrives. This is
    intentionally simple (a dict) rather than hitting the DB on every
    message -- the DB is the system of record for topology, not for live
    pole state, which changes far too fast for that.
    """

    def __init__(self):
        self.energized = {}          # pole_id -> bool
        self.last_seq = {}            # device_id -> last seen seq (dedup)
        self.pending_dark = {}        # pole_id -> first-seen timestamp (debounce buffer)

    def is_duplicate_or_stale(self, payload):
        device_id = payload["device_id"]
        seq = payload["seq"]

        last = self.last_seq.get(device_id)
        if last is not None and seq <= last:
            return True  # duplicate or out-of-order/old message for this device

        ts = datetime.fromisoformat(payload["ts"].replace("Z", "+00:00"))
        age = datetime.now(timezone.utc) - ts
        if age > timedelta(hours=STALE_RETRY_HOURS):
            return True  # stale retry from a long-past incident

        return False

    def apply(self, payload):
        """
        Updates in-memory pole state from one telemetry message. Returns
        True if this message changed a pole's energized state (worth
        re-running localization for), False otherwise (duplicate/no-op).
        """
        if self.is_duplicate_or_stale(payload):
            return False

        device_id = payload["device_id"]
        pole_id = payload["pole_id"]
        event = payload["event"]

        self.last_seq[device_id] = payload["seq"]

        if event == "power_lost":
            self.energized[pole_id] = False
            if pole_id not in self.pending_dark:
                self.pending_dark[pole_id] = time.time()
            return True

        if event in ("power_restored", "boot", "heartbeat"):
            self.energized[pole_id] = True
            self.pending_dark.pop(pole_id, None)
            return True

        return False

    def debounced_dark_poles(self):
        """
        Returns the set of pole_ids that have been continuously dark for
        at least DEBOUNCE_SECONDS -- i.e., ready to be run through
        localization rather than still "possibly about to be a duplicate
        burst we're still absorbing."
        """
        now = time.time()
        return {
            pole_id for pole_id, first_seen in self.pending_dark.items()
            if now - first_seen >= DEBOUNCE_SECONDS
        }


def run_worker_loop(tracker: PoleStateTracker, on_state_change=None, max_iterations=None):
    """
    Main consumer loop. Pops from the queue, updates pole state, and calls
    on_state_change(tracker) whenever something changed -- the caller
    decides what to do with that (e.g. re-run localization).

    max_iterations is for testing only -- lets us run a bounded number of
    pop attempts instead of looping forever.
    """
    iterations = 0
    while max_iterations is None or iterations < max_iterations:
        payload = pop_telemetry(timeout_seconds=1)
        iterations += 1
        if payload is None:
            continue  # timeout, no message -- loop again (allows clean shutdown checks)

        changed = tracker.apply(payload)
        if changed and on_state_change:
            on_state_change(tracker)


if __name__ == "__main__":
    tracker = PoleStateTracker()

    def on_change(t):
        dark = t.debounced_dark_poles()
        if dark:
            print(f"[worker] {len(dark)} pole(s) debounced-dark, ready for localization: {sorted(dark)[:5]}...")

    print("[worker] starting consumer loop (Ctrl+C to stop)...")
    run_worker_loop(tracker, on_state_change=on_change)