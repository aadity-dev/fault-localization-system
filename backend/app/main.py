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
import json
from datetime import datetime, timezone

from fastapi import FastAPI

from app.database import SessionLocal
from app.ingestion.worker import PoleStateTracker, run_worker_loop, shared_tracker
from app.models import Ticket
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
    Two jobs:
    1. Run the (small, debounced) set of confirmed-dark poles through
       localization and create tickets for any new incident.
    2. Auto-verify: scan resolved tickets and verify them automatically
       when all affected poles are confirmed live from telemetry.
       This satisfies the brief's requirement: "When the affected poles
       come back to life, the system should say so on its own."

    Opens its own DB session since this runs in a background thread,
    separate from FastAPI's request-scoped sessions.
    """
    db = SessionLocal()
    try:
        # --- 1. Create new tickets for debounced dark poles ---
        dark_poles = tracker.debounced_dark_poles()
        if dark_poles:
            created = process_dark_poles_into_tickets(db, dark_poles)
            if created:
                print(f"[tickets] created {len(created)} new ticket(s): "
                      f"{[(t.id, t.incident_type) for t in created]}")

        # --- 2. Auto-verify resolved tickets ---
        resolved_tickets = db.query(Ticket).filter(Ticket.status == "resolved").all()
        for ticket in resolved_tickets:
            affected_poles = json.loads(ticket.affected_poles_json)
            still_dark = [
                p for p in affected_poles
                if not tracker.energized.get(p, False)
            ]
            if not still_dark:
                ticket.status = "verified"
                ticket.verified_at = datetime.now(timezone.utc).isoformat()
                db.commit()
                print(f"[auto-verify] ticket {ticket.id} ({ticket.incident_type}) "
                      f"auto-verified — all {len(affected_poles)} affected poles confirmed live")
    finally:
        db.close()


@app.on_event("startup")
def on_startup():
    from sqlalchemy import text, inspect
    db = SessionLocal()
    try:
        inspector = inspect(db.get_bind())
        if "tickets" in inspector.get_table_names():
            columns = [c["name"] for c in inspector.get_columns("tickets")]
            if "closed_by" not in columns:
                db.execute(text("ALTER TABLE tickets ADD COLUMN closed_by VARCHAR;"))
                db.commit()
                print("[startup] Migrated schema: added closed_by column")
    except Exception as e:
        print(f"[startup] Migration error (ignoring): {e}")
        db.rollback()
    finally:
        db.close()
        
    seed_database()
    asyncio.get_event_loop().run_in_executor(
        None, run_worker_loop, shared_tracker, on_pole_state_change
    )


@app.get("/health")
def health_check():
    return {"status": "ok"}

from app.routers import ingest, tickets, scheduled_outages, simulator

app.include_router(ingest.router, tags=["ingest"])
app.include_router(tickets.router, tags=["tickets"])
app.include_router(scheduled_outages.router, tags=["scheduled-outages"])
app.include_router(simulator.router, tags=["simulator"])