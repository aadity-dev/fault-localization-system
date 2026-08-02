"""
backend/app/main.py

FastAPI entrypoint. Jobs:
  1. Seed the database on startup (satisfies G3).
  2. Expose a health check.
  3. Register routers.
  4. Run the ingestion worker as a background task IN THIS SAME PROCESS,
     so app.ingestion.worker.shared_tracker is genuinely shared memory
     between the worker loop and the /tickets/{id}/verify endpoint.
     Running the worker as a separate `python -m app.ingestion.worker`
     process (as we did for manual testing in Phase 3) does NOT share
     this state -- that's a distinct process with its own memory. See
     DECISIONS.md for why we chose in-process over a separate worker
     service at this scale, and what we'd change to scale further.
"""

import asyncio

from fastapi import FastAPI

from app.ingestion.worker import run_worker_loop, shared_tracker
from app.seed import seed_database

app = FastAPI(
    title="Fault Localization System",
    description="Karnataka State Power Distribution Board — fault localization API",
    version="0.1.0",
)


@app.on_event("startup")
def on_startup():
    seed_database()
    # run the blocking worker loop in a background thread so it doesn't
    # block FastAPI's event loop, while still sharing the same process
    # (and therefore the same shared_tracker memory) as the API.
    asyncio.get_event_loop().run_in_executor(None, run_worker_loop, shared_tracker)


@app.get("/health")
def health_check():
    return {"status": "ok"}


from app.routers import ingest, tickets

app.include_router(ingest.router, tags=["ingest"])
app.include_router(tickets.router, tags=["tickets"])

# --- Remaining routers get registered here as they're built (Phase 4/5) ---
# from app.routers import scheduled_outages, simulator
# app.include_router(scheduled_outages.router, prefix="/scheduled-outages", tags=["scheduled-outages"])
# app.include_router(simulator.router, prefix="/simulate", tags=["simulator"])