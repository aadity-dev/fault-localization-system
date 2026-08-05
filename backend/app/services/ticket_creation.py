"""
backend/app/services/ticket_creation.py

The missing link between ingestion and the ticket table: takes debounced
dark-pole state from the worker, runs it through the localization engine
(app/graph/*), and creates/updates Ticket rows -- without creating a new
ticket every time this runs for an incident that's already open.

Topology is loaded from the DATABASE (not CSV directly), since that's the
system of record once the app is running -- the CSVs are only how it gets
seeded on startup (see app/seed.py).
"""

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.graph.build_topology import build_full_topology
from app.graph.localize import localize_all
from app.graph.noise_filter import filter_scheduled_outages
from app.models import Pole, Ticket, Transformer
from app.services import scheduled_outages_store
from app.services.geocoding import resolve_pincode


def _pole_to_dict(p: Pole) -> dict:
    return {
        "pole_id": p.pole_id, "lat": p.lat, "lon": p.lon,
        "feeder_id": p.feeder_id, "dt_id": p.dt_id,
        "seq_on_line": p.seq_on_line, "parent_pole_id": p.parent_pole_id,
        "device_id": p.device_id,
    }


def _dt_to_dict(d: Transformer) -> dict:
    return {"dt_id": d.dt_id, "feeder_id": d.feeder_id, "lat": d.lat, "lon": d.lon}


def _incident_matches_open_ticket(incident: dict, open_tickets: list[Ticket]) -> Ticket | None:
    """
    Prevents creating a duplicate ticket every time this function runs
    for a fault that's already open. Matches on incident_type + location
    identity (span endpoints, or dt_id, or feeder_id).
    """
    for t in open_tickets:
        if t.incident_type != incident["incident_type"]:
            continue
        if incident["incident_type"] == "span":
            if t.upstream_pole == incident["upstream_pole"] and t.downstream_pole == incident["downstream_pole"]:
                return t
        elif incident["incident_type"] == "dt":
            if t.dt_id == incident["dt_id"]:
                return t
        elif incident["incident_type"] == "feeder":
            if t.feeder_id == incident["feeder_id"]:
                return t
    return None


def process_dark_poles_into_tickets(db: Session, dark_pole_ids: set):
    """
    Main entry point, called by the worker whenever the debounced-dark set
    changes. Loads current topology + poles from the DB, localizes, and
    creates a new Ticket for any incident that doesn't already have an
    open one.

    Returns the list of newly created Ticket objects (empty list if
    nothing new -- e.g. all current incidents already have open tickets).
    """
    if not dark_pole_ids:
        return []

    all_poles = db.query(Pole).all()
    poles = [_pole_to_dict(p) for p in all_poles]
    pole_lookup = {p.pole_id: p for p in all_poles}
    dts = [_dt_to_dict(d) for d in db.query(Transformer).all()]
    dt_lookup = {d["dt_id"]: d for d in dts}

    topology = build_full_topology(poles, dts)
    incidents = localize_all(topology, dark_pole_ids, poles, dts)

    # cross-check against the scheduled-outage feed BEFORE creating tickets --
    # a full-coverage incident matching an active scheduled outage is
    # suppressed; partial coverage (a real fault during maintenance) is kept.
    poles_by_dt = {}
    for p in poles:
        poles_by_dt.setdefault(p["dt_id"], []).append(p)

    scheduled = scheduled_outages_store.get_all()
    incidents, suppressed = filter_scheduled_outages(incidents, scheduled, poles_by_dt)

    open_tickets = db.query(Ticket).filter(Ticket.status != "closed").all()

    created = []
    for incident in incidents:
        existing = _incident_matches_open_ticket(incident, open_tickets)
        if existing:
            continue  # already ticketed, don't duplicate

        # Coordinates for the UI map / navigation: use the downstream
        # pole's surveyed GPS for span faults (most precise -- that's the
        # actual fault location), the DT's own coordinates for dt/feeder
        # faults (no single pole is "the" location for those).
        lat, lon, pincode = None, None, None
        if incident["incident_type"] == "span":
            p = pole_lookup.get(incident.get("downstream_pole"))
            if p:
                lat, lon = p.lat, p.lon
                pincode, _ = resolve_pincode(p.pincode, p.ward)
        elif incident["incident_type"] == "dt":
            d = dt_lookup.get(incident.get("dt_id"))
            if d:
                lat, lon = d["lat"], d["lon"]
        elif incident["incident_type"] == "feeder":
            # no single point for a feeder-wide fault -- leave coordinates
            # unset, UI should show this as a zone/list of DTs, not a pin
            pass

        ticket = Ticket(
            incident_type=incident["incident_type"],
            status="detected",
            dt_id=incident.get("dt_id"),
            feeder_id=incident.get("feeder_id"),
            upstream_pole=incident.get("upstream_pole"),
            downstream_pole=incident.get("downstream_pole"),
            fault_lat=lat,
            fault_lon=lon,
            pincode=pincode,
            affected_pole_count=incident["dark_pole_count"],
            affected_poles_json=json.dumps(incident.get("affected_poles", [])),
            topology_status=incident.get("topology_status"),
            confidence=incident.get("confidence", 0.5),
            detected_at=datetime.now(timezone.utc).isoformat(),
        )
        db.add(ticket)
        created.append(ticket)

    if created:
        db.commit()
        for t in created:
            db.refresh(t)

    return created