"""
backend/app/schemas/ticket.py

Pydantic models for the /tickets API surface.
"""

from typing import List, Optional

from pydantic import BaseModel


class TicketOut(BaseModel):
    id: int
    incident_type: str
    status: str
    dt_id: Optional[str] = None
    feeder_id: Optional[str] = None
    upstream_pole: Optional[str] = None
    downstream_pole: Optional[str] = None
    fault_lat: Optional[float] = None
    fault_lon: Optional[float] = None
    pincode: Optional[str] = None
    affected_pole_count: int
    topology_status: Optional[str] = None
    confidence: float
    detected_at: str
    resolved_at: Optional[str] = None
    verified_at: Optional[str] = None

    class Config:
        from_attributes = True


class TicketStatusUpdate(BaseModel):
    new_status: str   # "acknowledged" | "crew_assigned" | "resolved"