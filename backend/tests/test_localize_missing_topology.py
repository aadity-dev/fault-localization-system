"""
backend/tests/test_localize_missing_topology.py

The 60% missing-topology fallback: with no parent_pole_id recorded, we
still need to produce a located (if lower-confidence) incident using MST
inference, and the incident must be clearly tagged INFERRED so the UI can
communicate the lower confidence honestly.
"""

from app.graph.build_topology import build_full_topology
from app.graph.localize import localize_all


def test_missing_topology_still_localizes_a_fault(unknown_topology_poles, unknown_dt_registry):
    # Q1 is closest to the DT, Q2 in the middle, Q3 furthest.
    # Q3 goes dark; Q1 and Q2 stay live. The MST should infer Q3's parent
    # is Q2 (its nearest neighbour), so the fault should localize near
    # Q2 -- Q3, not crash, and be marked INFERRED / lower confidence.
    dark_poles = {"Q3"}

    topology = build_full_topology(unknown_topology_poles, unknown_dt_registry)
    incidents = localize_all(topology, dark_poles, unknown_topology_poles, unknown_dt_registry)

    assert len(incidents) == 1
    incident = incidents[0]
    assert incident["incident_type"] == "span"
    assert incident["downstream_pole"] == "Q3"
    assert incident["topology_status"] == "INFERRED"
    assert incident["confidence"] < 0.95, "inferred edges must report lower confidence than verified ones"


def test_missing_topology_full_dt_outage_still_groups_correctly(unknown_topology_poles, unknown_dt_registry):
    # even with no known pole order, if EVERY pole under the DT is dark,
    # we should still correctly identify this as a DT-level fault (this
    # doesn't require topology at all -- just device coverage).
    dark_poles = {"Q1", "Q2", "Q3"}

    topology = build_full_topology(unknown_topology_poles, unknown_dt_registry)
    incidents = localize_all(topology, dark_poles, unknown_topology_poles, unknown_dt_registry)

    assert len(incidents) == 1
    assert incidents[0]["incident_type"] == "dt"
