"""
backend/app/routers/tickets.py

GET /tickets, PATCH /tickets/{id}/status (ordinary lifecycle moves), and
POST /tickets/{id}/verify (the telemetry-enforced resolved->verified
transition -- this is the endpoint that refuses to believe a human who
claims a fault is fixed if the affected poles are still reporting dark).
"""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.ingestion.worker import shared_tracker
from app.models import Ticket
from app.schemas.ticket import TicketOut, TicketStatusUpdate
from app.services.ai_feature import summarize_ticket
from app.services.ticket_lifecycle import (
    InvalidTransition,
    VerificationFailed,
    apply_manual_transition,
    verify_ticket,
)

router = APIRouter(prefix="/tickets")


@router.get("", response_model=list[TicketOut])
def list_tickets(status: str | None = None, db: Session = Depends(get_db)):
    query = db.query(Ticket)
    if status:
        query = query.filter(Ticket.status == status)
    return query.order_by(Ticket.detected_at.desc()).all()


@router.get("/{ticket_id}", response_model=TicketOut)
def get_ticket(ticket_id: int, db: Session = Depends(get_db)):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


@router.patch("/{ticket_id}/status", response_model=TicketOut)
def update_ticket_status(ticket_id: int, body: TicketStatusUpdate, db: Session = Depends(get_db)):
    """
    Ordinary lifecycle moves: detected -> acknowledged -> crew_assigned ->
    resolved. Attempting to set status="verified" here is rejected --
    that transition only happens via POST /tickets/{id}/verify.
    """
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    try:
        new_status = apply_manual_transition(ticket.status, body.new_status)
    except InvalidTransition as e:
        raise HTTPException(status_code=400, detail=str(e))

    ticket.status = new_status
    now = datetime.now(timezone.utc).isoformat()
    if new_status == "acknowledged":
        ticket.acknowledged_at = now
    elif new_status == "crew_assigned":
        ticket.crew_assigned_at = now
    elif new_status == "resolved":
        ticket.resolved_at = now
    elif new_status == "closed":
        ticket.closed_at = now
        if body.closed_by:
            ticket.closed_by = body.closed_by

    db.commit()
    db.refresh(ticket)
    return ticket


@router.post("/{ticket_id}/verify", response_model=TicketOut)
def verify_ticket_endpoint(ticket_id: int, db: Session = Depends(get_db)):
    """
    Attempts resolved -> verified using CURRENT telemetry-derived pole
    state, not the crew's say-so. Returns 409 (not a generic 400) if the
    affected poles are still dark -- distinct status code so a UI can
    show "not yet confirmed" rather than a generic error.

    Uses app.ingestion.worker.shared_tracker -- the same in-memory
    PoleStateTracker instance the ingestion worker updates as telemetry
    arrives. This is the actual source of truth for "is this pole live
    right now," not the database (which only holds static topology).
    """
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    affected_poles = json.loads(ticket.affected_poles_json)
    current_pole_state = shared_tracker.energized

    try:
        new_status = verify_ticket(ticket.status, affected_poles, current_pole_state)
    except InvalidTransition as e:
        raise HTTPException(status_code=400, detail=str(e))
    except VerificationFailed as e:
        raise HTTPException(status_code=409, detail=str(e))

    ticket.status = new_status
    ticket.verified_at = datetime.now(timezone.utc).isoformat()
    db.commit()
    db.refresh(ticket)
    return ticket


@router.get("/{ticket_id}/summary")
def get_ticket_summary(ticket_id: int, db: Session = Depends(get_db)):
    """
    The AI feature. Returns a plain-language summary of the ticket for
    display in the operator UI. Falls back to a deterministic template
    if the LLM is unavailable -- see app/services/ai_feature.py for why
    this can never break the ticket view.
    """
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    ticket_dict = {
        "incident_type": ticket.incident_type,
        "upstream_pole": ticket.upstream_pole,
        "downstream_pole": ticket.downstream_pole,
        "dt_id": ticket.dt_id,
        "feeder_id": ticket.feeder_id,
        "affected_pole_count": ticket.affected_pole_count,
        "pincode": ticket.pincode,
        "topology_status": ticket.topology_status,
        "confidence": ticket.confidence,
    }
    return summarize_ticket(ticket_dict)