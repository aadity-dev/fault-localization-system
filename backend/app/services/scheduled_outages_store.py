"""
backend/app/services/scheduled_outages_store.py

Shared in-memory store for the mocked scheduled-outage feed. Both
routers/scheduled_outages.py (HTTP GET/POST) and services/ticket_creation.py
(the noise-filter check before creating a ticket) read/write the SAME
list -- pulled out into its own module so ticket_creation doesn't need to
reach into router internals.
"""

from datetime import datetime, timedelta, timezone

_outages: list[dict] = [
    {
        "id": "SO-2026-08-02-001",
        "scope": "dt",
        "target_id": "D-010101",
        "start": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
        "end": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        "reason": "Load shedding (demo seed data)",
    },
]


def get_all():
    return _outages


def add(outage: dict):
    _outages.append(outage)
    return outage


def clear():
    _outages.clear()