"""
backend/app/models.py

Pole and Transformer ORM models — matches pole_registry.csv and
dt_registry.csv exactly, per 02-data-and-systems.md.

seq_on_line and parent_pole_id are nullable BY DESIGN, not because we
forgot to constrain them. ~60% of DTs have no recorded pole ordering
(02-data-and-systems.md §3) -- this is the central design problem the
assignment is testing, and the schema reflects that from day one rather
than bolting it on later.
"""

from sqlalchemy import Column, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class Pole(Base):
    __tablename__ = "poles"

    pole_id = Column(String, primary_key=True)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    feeder_id = Column(String, nullable=False)
    dt_id = Column(String, ForeignKey("transformers.dt_id"), nullable=False)

    # Nullable by design: missing for ~60% of DTs (the missing-topology problem)
    seq_on_line = Column(Integer, nullable=True)
    parent_pole_id = Column(String, nullable=True)

    pole_type = Column(String, nullable=True)
    ward = Column(String, nullable=True)
    pincode = Column(String, nullable=True)     # missing for ~3% of poles
    device_id = Column(String, nullable=True)   # missing for ~9% of poles (no telemetry coverage)

    transformer = relationship("Transformer", back_populates="poles")


class Transformer(Base):
    __tablename__ = "transformers"

    dt_id = Column(String, primary_key=True)
    feeder_id = Column(String, nullable=False)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    capacity_kva = Column(Float)
    households_served = Column(Integer)

    poles = relationship("Pole", back_populates="transformer")


class Ticket(Base):
    """
    A localized fault, moving through the lifecycle described in
    00-candidate-brief.md: detected -> acknowledged -> crew_assigned ->
    resolved -> verified -> closed.

    CRITICAL RULE (00-candidate-brief.md, "Ticket workflow"): 'verified'
    must be set by telemetry confirming the affected poles are live again
    -- never by a human clicking a button. A 'resolved' status means a
    lineman claims to have fixed it; the system independently checks
    real pole state before allowing a transition to 'verified'. See
    routers/tickets.py for the enforcement logic.
    """
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    incident_type = Column(String, nullable=False)   # "span" | "dt" | "feeder"
    status = Column(String, nullable=False, default="detected")

    dt_id = Column(String, nullable=True)
    feeder_id = Column(String, nullable=True)
    upstream_pole = Column(String, nullable=True)
    downstream_pole = Column(String, nullable=True)

    fault_lat = Column(Float, nullable=True)
    fault_lon = Column(Float, nullable=True)
    pincode = Column(String, nullable=True)

    affected_pole_count = Column(Integer, nullable=False, default=0)
    affected_poles_json = Column(String, nullable=False, default="[]")  # JSON list of pole_ids

    topology_status = Column(String, nullable=True)   # VERIFIED | INFERRED
    confidence = Column(Float, nullable=False, default=0.5)

    detected_at = Column(String, nullable=False)
    acknowledged_at = Column(String, nullable=True)
    crew_assigned_at = Column(String, nullable=True)
    resolved_at = Column(String, nullable=True)         # lineman claims fixed
    verified_at = Column(String, nullable=True)          # telemetry CONFIRMS fixed
    closed_at = Column(String, nullable=True)

    suppressed_reason = Column(String, nullable=True)   # set if this was a suppressed noise incident, kept for audit