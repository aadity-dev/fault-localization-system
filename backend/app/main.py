"""
backend/app/main.py

FastAPI entrypoint. Two jobs today:
  1. Seed the database on startup (satisfies G3 -- reviewer must see a
     populated system immediately, not a blank one).
  2. Expose a health check so we (and the reviewer) can confirm the stack
     actually came up.

Routers (ingest, tickets, scheduled_outages, simulator) get imported and
registered here as Phase 2/3 build them -- see the commented-out block
below for exactly where that wiring goes. Don't uncomment until those
files actually exist, or this file will fail to import.
"""

from fastapi import FastAPI

from app.seed import seed_database

app = FastAPI(
    title="Fault Localization System",
    description="Karnataka State Power Distribution Board — fault localization API",
    version="0.1.0",
)


@app.on_event("startup")
def on_startup():
    seed_database()


@app.get("/health")
def health_check():
    return {"status": "ok"}


# --- Routers get registered here as they're built (Phase 3 onward) ---
# from app.routers import ingest, tickets, scheduled_outages, simulator
# app.include_router(ingest.router, prefix="/telemetry", tags=["ingest"])
# app.include_router(tickets.router, prefix="/tickets", tags=["tickets"])
# app.include_router(scheduled_outages.router, prefix="/scheduled-outages", tags=["scheduled-outages"])
# app.include_router(simulator.router, prefix="/simulate", tags=["simulator"])