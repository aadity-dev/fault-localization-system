"""
backend/tests/test_scheduled_outage_filter.py

Tests noise_filter.py's scheduled-outage cross-check. Per
02-data-and-systems.md §4: outages start late, overrun by 20-40 minutes,
and ~10% are cancelled without the feed updating -- so we cannot blindly
trust the schedule. The rule under test: full-coverage outage inside the
window is suppressed; PARTIAL coverage (some poles dark, some still live)
is NOT suppressed, because that's evidence of a real fault happening
during/around the maintenance window.
"""

from datetime import datetime, timezone

from app.graph.noise_filter import filter_scheduled_outages


def _dt_incident(dt_id, affected_poles):
    return {
        "incident_type": "dt",
        "dt_id": dt_id,
        "dark_pole_count": len(affected_poles),
        "affected_poles": affected_poles,
        "confidence": 0.95,
    }


def test_full_dt_outage_inside_window_is_suppressed(known_topology_poles):
    now = datetime(2026, 7, 29, 14, 30, tzinfo=timezone.utc)
    scheduled_outages = [{
        "id": "SO-TEST-001",
        "scope": "dt",
        "target_id": "D-KNOWN",
        "start": "2026-07-29T14:00:00Z",
        "end": "2026-07-29T15:00:00Z",
        "reason": "Load shedding",
    }]
    # every pole with a device under D-KNOWN is dark -- matches the full outage
    all_poles_with_devices = [p["pole_id"] for p in known_topology_poles if p.get("device_id")]
    incident = _dt_incident("D-KNOWN", all_poles_with_devices)

    poles_by_dt = {"D-KNOWN": known_topology_poles}
    kept, suppressed = filter_scheduled_outages([incident], scheduled_outages, poles_by_dt, now=now)

    assert len(kept) == 0
    assert len(suppressed) == 1
    assert "SO-TEST-001" in suppressed[0]["suppressed_reason"]


def test_partial_dt_outage_inside_window_is_not_suppressed(known_topology_poles):
    """
    Real fault during a scheduled maintenance window: only SOME poles are
    dark, not the full DT. This must NOT be suppressed -- it's evidence of
    an actual span/DT fault layered on top of planned maintenance.
    """
    now = datetime(2026, 7, 29, 14, 30, tzinfo=timezone.utc)
    scheduled_outages = [{
        "id": "SO-TEST-002",
        "scope": "dt",
        "target_id": "D-KNOWN",
        "start": "2026-07-29T14:00:00Z",
        "end": "2026-07-29T15:00:00Z",
        "reason": "Load shedding",
    }]
    # only P1 is dark -- the rest of the DT is live, so this is NOT the full
    # scheduled outage pattern
    incident = _dt_incident("D-KNOWN", ["P1"])

    poles_by_dt = {"D-KNOWN": known_topology_poles}
    kept, suppressed = filter_scheduled_outages([incident], scheduled_outages, poles_by_dt, now=now)

    assert len(kept) == 1, "partial coverage during a scheduled outage must still ticket"
    assert len(suppressed) == 0


def test_outage_overrun_slack_still_suppresses(known_topology_poles):
    """
    02-data-and-systems.md: outages overrun by 20-40 minutes routinely.
    An outage that officially 'ended' 30 minutes ago should still be
    treated as active.
    """
    # outage window ended at 14:00, now is 14:30 -- 30 min overrun, within
    # our documented OUTAGE_OVERRUN_SLACK
    now = datetime(2026, 7, 29, 14, 30, tzinfo=timezone.utc)
    scheduled_outages = [{
        "id": "SO-TEST-003",
        "scope": "dt",
        "target_id": "D-KNOWN",
        "start": "2026-07-29T13:00:00Z",
        "end": "2026-07-29T14:00:00Z",
        "reason": "Load shedding",
    }]
    all_poles_with_devices = [p["pole_id"] for p in known_topology_poles if p.get("device_id")]
    incident = _dt_incident("D-KNOWN", all_poles_with_devices)

    poles_by_dt = {"D-KNOWN": known_topology_poles}
    kept, suppressed = filter_scheduled_outages([incident], scheduled_outages, poles_by_dt, now=now)

    assert len(suppressed) == 1, "overrunning outage (within documented slack) should still suppress"


def test_no_matching_outage_is_kept(known_topology_poles):
    now = datetime(2026, 7, 29, 20, 0, tzinfo=timezone.utc)  # well outside any window
    scheduled_outages = [{
        "id": "SO-TEST-004",
        "scope": "dt",
        "target_id": "D-KNOWN",
        "start": "2026-07-29T13:00:00Z",
        "end": "2026-07-29T14:00:00Z",
        "reason": "Load shedding",
    }]
    all_poles_with_devices = [p["pole_id"] for p in known_topology_poles if p.get("device_id")]
    incident = _dt_incident("D-KNOWN", all_poles_with_devices)

    poles_by_dt = {"D-KNOWN": known_topology_poles}
    kept, suppressed = filter_scheduled_outages([incident], scheduled_outages, poles_by_dt, now=now)

    assert len(kept) == 1
    assert len(suppressed) == 0