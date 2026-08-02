"""
backend/app/ingestion/queue.py

Thin wrapper around Redis, used as an in-memory queue between the ingest
HTTP endpoint and the async worker that actually runs telemetry through
the graph engine.

Why a queue at all (see 02-data-and-systems.md §1): a burst of 5,000
messages in 10 seconds cannot be processed synchronously inside the HTTP
handler -- that would mean holding the connection open while we do graph
traversal, and would buckle under load. Instead: the HTTP handler pushes
the raw payload onto this queue and returns 200 immediately. A separate
worker process/task drains the queue and does the actual (slower) graph
work.

Uses a single Redis LIST as a FIFO queue (LPUSH / BRPOP). Simple, and
sufficient at this scale -- see DECISIONS.md for why we didn't reach for
a heavier broker (Kafka, BullMQ) for a one-subdivision exercise.
"""

import json
import os

import redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
QUEUE_KEY = "telemetry:queue"

_client = None


def get_redis_client():
    global _client
    if _client is None:
        _client = redis.from_url(REDIS_URL, decode_responses=True)
    return _client


def push_telemetry(payload: dict):
    """Called by the ingest HTTP handler. Non-blocking, fast."""
    client = get_redis_client()
    client.lpush(QUEUE_KEY, json.dumps(payload))


def pop_telemetry(timeout_seconds: int = 1):
    """
    Called by the worker loop. Blocks up to timeout_seconds waiting for a
    message; returns None on timeout (so the worker loop can check for
    shutdown signals, etc., rather than blocking forever).
    """
    client = get_redis_client()
    result = client.brpop(QUEUE_KEY, timeout=timeout_seconds)
    if result is None:
        return None
    _, raw = result
    return json.loads(raw)


def queue_length() -> int:
    """Useful for health checks / load-test observability."""
    client = get_redis_client()
    return client.llen(QUEUE_KEY)


def clear_queue():
    """Testing/reset utility -- not used in normal operation."""
    client = get_redis_client()
    client.delete(QUEUE_KEY)