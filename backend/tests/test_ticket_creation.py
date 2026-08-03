"""
backend/tests/test_ticket_creation.py

Tests that process_dark_poles_into_tickets() actually applies the
scheduled-outage noise filter before writing tickets -- not just that
noise_filter.py works in isolation (that's covered by
test_scheduled_outage_filter.py already). This test proves the wiring.
"""

from datetime import datetime, timedelta, timezone

from app.database import Base, SessionLocal, engine
from app.models import Pole, Transformer
from app.services import scheduled_outages_store
from app.services.ticket_creation import process_dark_poles_into_tickets


def setup_module(module):
    Base.metadata.create_all(bind=engine)


def _seed_known_dt(db):
    db.add(Transformer(dt_id="D-TEST", feeder_id="F-TEST", lat=12.97, lon=77.59,
                        capacity_kva=100, households_served=50))
    db.add(Pole(pole_id="P1", lat=12.9700, lon=77.5900, feeder_id="F-TEST",
                dt_id="D-TEST", parent_pole_id=None, device_id="DEV-P1"))
    db.add(Pole(pole_id="P2", lat=12.9705, lon=77.5905, feeder_id="F-TEST",
                dt_id="D-TEST", parent_pole_id="P1", device_id="DEV-P2"))
    db.commit()


def test_full_dt_fault_suppressed_during_matching_scheduled_outage():
    db = SessionLocal()
    try:
        # clean slate for this DT/feeder to avoid cross-test pollution
        db.query(Pole).filter(Pole.dt_id == "D-TEST").delete()
        db.query(Transformer).filter(Transformer.dt_id == "D-TEST").delete()
        db.commit()
        _seed_known_dt(db)

        scheduled_outages_store.clear()
        scheduled_outages_store.add({
            "id": "SO-TEST-CREATION-1", "scope": "dt", "target_id": "D-TEST",
            "start": (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(),
            "end": (datetime.now(timezone.utc) + timedelta(minutes=50)).isoformat(),
            "reason": "test",
        })

        dark_poles = {"P1", "P2"}  # full DT down, matches the scheduled outage exactly
        created = process_dark_poles_into_tickets(db, dark_poles)

        assert created == [], "full-coverage DT outage matching a scheduled outage must not create a ticket"
    finally:
        scheduled_outages_store.clear()
        db.close()


def test_partial_dt_fault_still_creates_ticket_during_scheduled_outage():
    db = SessionLocal()
    try:
        db.query(Pole).filter(Pole.dt_id == "D-TEST").delete()
        db.query(Transformer).filter(Transformer.dt_id == "D-TEST").delete()
        db.commit()
        _seed_known_dt(db)

        scheduled_outages_store.clear()
        scheduled_outages_store.add({
            "id": "SO-TEST-CREATION-2", "scope": "dt", "target_id": "D-TEST",
            "start": (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat(),
            "end": (datetime.now(timezone.utc) + timedelta(minutes=50)).isoformat(),
            "reason": "test",
        })

        dark_poles = {"P2"}  # only P2 dark -- partial coverage, real fault signal
        created = process_dark_poles_into_tickets(db, dark_poles)

        assert len(created) == 1, "partial coverage during a scheduled outage must still ticket"
    finally:
        scheduled_outages_store.clear()
        db.query(Pole).filter(Pole.dt_id == "D-TEST").delete()
        db.query(Transformer).filter(Transformer.dt_id == "D-TEST").delete()
        db.commit()
        db.close()