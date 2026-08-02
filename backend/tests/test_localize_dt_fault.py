"""
backend/tests/test_localize_dt_fault.py

Every pole under a DT going dark should be ONE dt-level incident, not one
alert per pole. This is the "alert fatigue" failure mode the brief
explicitly calls out as a disqualifier.
"""

from app.graph.build_topology import build_full_topology
from app.graph.localize import localize_all


def test_full_dt_outage_is_one_incident(known_topology_poles, known_dt_registry):
    # every pole with a device under D-KNOWN goes dark
    dark_poles = {"P1", "P2", "P3", "P4"}

    topology = build_full_topology(known_topology_poles, known_dt_registry)
    incidents = localize_all(topology, dark_poles, known_topology_poles, known_dt_registry)

    assert len(incidents) == 1, f"expected 1 incident (grouped), got {len(incidents)}"
    incident = incidents[0]
    assert incident["incident_type"] == "dt"
    assert incident["dt_id"] == "D-KNOWN"
    assert incident["dark_pole_count"] == 4
    assert set(incident["affected_poles"]) == {"P1", "P2", "P3", "P4"}
