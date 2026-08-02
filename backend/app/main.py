"""
backend/app/main.py

FastAPI entrypoint. Jobs:
  1. Seed the database on startup (satisfies G3 -- reviewer must see a
     populated system immediately, not a blank one).
  2. Expose a health check so we (and the reviewer) can confirm the stack
     actually came up.
  3. Register routers as they're built -- ingest is live as of Phase 3.

Remaining routers (tickets, scheduled_outages, simulator) get registered
here as Phase 4 builds them -- see the commented-out block below.
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


from app.routers import ingest

app.include_router(ingest.router, tags=["ingest"])

# --- Remaining routers get registered here as they're built (Phase 4) ---
# from app.routers import tickets, scheduled_outages, simulator
# app.include_router(tickets.router, prefix="/tickets", tags=["tickets"])
# app.include_router(scheduled_outages.router, prefix="/scheduled-outages", tags=["scheduled-outages"])
# app.include_router(simulator.router, prefix="/simulate", tags=["simulator"])