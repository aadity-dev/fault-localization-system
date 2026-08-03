"""
backend/app/routers/scheduled_outages.py

Mocks the department's scheduled-outage feed, per 02-data-and-systems.md
§4. Backed by services/scheduled_outages_store.py, which is also read
directly by services/ticket_creation.py's noise filter -- same data,
no HTTP round-trip needed since it's all one process.
"""

from fastapi import APIRouter, Query

from app.services import scheduled_outages_store as store

router = APIRouter(prefix="/scheduled-outages")


@router.get("")
def get_scheduled_outages(
    from_: str = Query(None, alias="from"),
    to: str = Query(None),
):
    """GET /scheduled-outages?from=...&to=... -- matches the brief's mock contract."""
    return store.get_all()


@router.post("")
def add_scheduled_outage(outage: dict):
    """Lets the simulator/demo inject a scheduled outage on demand."""
    return store.add(outage)


@router.delete("")
def clear_scheduled_outages():
    store.clear()
    return {"cleared": True}