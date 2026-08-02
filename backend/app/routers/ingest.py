"""
backend/app/routers/ingest.py

POST /telemetry -- the endpoint device payloads (and simulator/telemetry_emitter.py's
--live mode) hit. Deliberately thin: validate, push to queue, return. All
the actual graph work happens later, in the worker (ingestion/worker.py),
not in this request handler -- this is what lets the endpoint survive a
5,000-message/10s burst without buckling (02-data-and-systems.md §1).
"""

from fastapi import APIRouter, status

from app.ingestion.queue import push_telemetry, queue_length
from app.schemas.telemetry import TelemetryPayload

router = APIRouter()


@router.post("/telemetry", status_code=status.HTTP_202_ACCEPTED)
def ingest_telemetry(payload: TelemetryPayload):
    """
    Accepts one device telemetry message, pushes it onto the Redis queue,
    and returns immediately. Does NOT do graph traversal here -- see
    ingestion/worker.py for that.
    """
    push_telemetry(payload.model_dump())
    return {"accepted": True}


@router.get("/telemetry/queue-status")
def queue_status():
    """Observability endpoint -- lets us watch queue depth during a load test."""
    return {"queue_length": queue_length()}