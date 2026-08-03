"""
backend/app/main.py

FastAPI entrypoint. Jobs:
  1. Seed the database on startup (satisfies G3).
  2. Expose a health check.
  3. Register routers.
  4. Run the ingestion worker as a background task IN THIS SAME PROCESS,
     wired all the way through to ticket creation: telemetry -> worker
     dedup/debounce -> localization -> Ticket rows. Same-process is what
     lets /tickets/{id}/verify read live pole state directly from
     shared_tracker (see DECISIONS.md for the scaling tradeoff this
     implies).
"""

import asyncio

from fastapi import FastAPI

from app.database import SessionLocal
from app.ingestion.worker import PoleStateTracker, run_worker_loop, shared_tracker
from app.seed import seed_database
from app.services.ticket_creation import process_dark_poles_into_tickets

app = FastAPI(
    title="Fault Localization System",
    description="Karnataka State Power Distribution Board — fault localization API",
    version="0.1.0",
)


def on_pole_state_change(tracker: PoleStateTracker):
    """
    Called by the worker loop whenever telemetry changes pole state.
    Runs the (small, debounced) set of confirmed-dark poles through
    localization and creates tickets for any new incident.

    Opens its own DB session since this runs in a background thread,
    separate from FastAPI's request-scoped sessions.
    """
    dark_poles = tracker.debounced_dark_poles()
    if not dark_poles:
        return

    db = SessionLocal()
    try:
        created = process_dark_poles_into_tickets(db, dark_poles)
        if created:
            print(f"[tickets] created {len(created)} new ticket(s): "
                  f"{[(t.id, t.incident_type) for t in created]}")
    finally:
        db.close()


@app.on_event("startup")
def on_startup():
    seed_database()
    asyncio.get_event_loop().run_in_executor(
        None, run_worker_loop, shared_tracker, on_pole_state_change
    )


@app.get("/health")
def health_check():
    return {"status": "ok"}


from app.routers import ingest, tickets

app.include_router(ingest.router, tags=["ingest"])
app.include_router(tickets.router, tags=["tickets"])

# --- Remaining routers get registered here as they're built (Phase 5) ---
# from app.routers import scheduled_outages, simulator
# app.include_router(scheduled_outages.router, prefix="/scheduled-outages", tags=["scheduled-outages"])
# app.include_router(simulator.router, prefix="/simulate", tags=["simulator"])