"""
backend/app/routers/simulator.py

POST /simulate/fault, POST /simulate/restore -- lets the operator UI (or
a single documented curl command) drive the simulator without a separate
terminal session. This is what satisfies G5.

Reuses the exact same fault-injection and telemetry-emission logic as
simulator/*.py (imported directly, not reimplemented).

Rather than round-tripping over HTTP to our own /telemetry endpoint, this
pushes directly onto the Redis queue via app.ingestion.queue -- the same
queue /telemetry uses, so behavior is identical from the worker's
perspective.
"""

import os
import sys

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.ingestion.queue import push_telemetry
from app.models import Pole

router = APIRouter(prefix="/simulate")

_DOCKER_SIMULATOR_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "simulator"))
_LOCAL_SIMULATOR_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "simulator"))

_SIMULATOR_PATH = _DOCKER_SIMULATOR_PATH if os.path.exists(_DOCKER_SIMULATOR_PATH) else _LOCAL_SIMULATOR_PATH

if _SIMULATOR_PATH not in sys.path:
    sys.path.insert(0, _SIMULATOR_PATH)

from inject_fault import (  # noqa: E402
    inject_dt_fault,
    inject_feeder_fault,
    load_ground_truth,
    pick_random_span_fault,
)
from telemetry_emitter import emit_outage_telemetry, build_restoration_payloads  # noqa: E402


def _poles_as_dicts(db: Session):
    return [
        {"pole_id": p.pole_id, "lat": p.lat, "lon": p.lon, "feeder_id": p.feeder_id,
         "dt_id": p.dt_id, "seq_on_line": p.seq_on_line, "parent_pole_id": p.parent_pole_id,
         "device_id": p.device_id}
        for p in db.query(Pole).all()
    ]


@router.post("/fault/span")
def simulate_span_fault(db: Session = Depends(get_db)):
    poles = _poles_as_dicts(db)
    ground_truth = load_ground_truth()
    result = pick_random_span_fault(poles, ground_truth)

    by_id = {p["pole_id"]: p for p in poles}
    dark_dicts = [by_id[pid] for pid in result["dark_poles"] if pid in by_id]

    payloads = emit_outage_telemetry(dark_dicts, dry_run=True)
    for p in payloads:
        push_telemetry(p)

    return {
        "fault_type": "span",
        "fault_location": result["fault_location"],
        "poles_should_go_dark": len(result["dark_poles"]),
        "telemetry_messages_queued": len(payloads),
    }


@router.post("/fault/dt/{dt_id}")
def simulate_dt_fault(dt_id: str, db: Session = Depends(get_db)):
    poles = _poles_as_dicts(db)
    result = inject_dt_fault(dt_id, poles)

    by_id = {p["pole_id"]: p for p in poles}
    dark_dicts = [by_id[pid] for pid in result["dark_poles"] if pid in by_id]

    payloads = emit_outage_telemetry(dark_dicts, dry_run=True)
    for p in payloads:
        push_telemetry(p)

    return {
        "fault_type": "dt",
        "fault_location": dt_id,
        "poles_should_go_dark": len(result["dark_poles"]),
        "telemetry_messages_queued": len(payloads),
    }


@router.post("/fault/feeder/{feeder_id}")
def simulate_feeder_fault(feeder_id: str, db: Session = Depends(get_db)):
    poles = _poles_as_dicts(db)
    result = inject_feeder_fault(feeder_id, poles)

    by_id = {p["pole_id"]: p for p in poles}
    dark_dicts = [by_id[pid] for pid in result["dark_poles"] if pid in by_id]

    payloads = emit_outage_telemetry(dark_dicts, dry_run=True)
    for p in payloads:
        push_telemetry(p)

    return {
        "fault_type": "feeder",
        "fault_location": feeder_id,
        "poles_should_go_dark": len(result["dark_poles"]),
        "telemetry_messages_queued": len(payloads),
    }


@router.post("/restore-ticket/{ticket_id}")
def simulate_restore_ticket(ticket_id: int, db: Session = Depends(get_db)):
    """Sends boot + power_restored for all poles affected by a ticket, for the demo video."""
    import json
    from app.models import Ticket

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        return {"error": "ticket not found"}

    affected_poles = json.loads(ticket.affected_poles_json)
    poles = db.query(Pole).filter(Pole.pole_id.in_(affected_poles)).all()

    total_queued = 0
    for pole in poles:
        if not pole.device_id:
            continue
        pole_dict = {"pole_id": pole.pole_id, "device_id": pole.device_id}
        payloads = build_restoration_payloads(pole_dict, seq_start=0)
        for p in payloads:
            push_telemetry(p)
        total_queued += len(payloads)

    return {"ticket_id": ticket_id, "restored_poles": len(poles), "messages_queued": total_queued}