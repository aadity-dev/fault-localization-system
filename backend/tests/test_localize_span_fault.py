"""
backend/tests/test_localize_span_fault.py

A known fault in a known topology produces the expected span -- the exact
case the brief asks for as the minimum bar for testing.
"""

from app.graph.build_topology import build_full_topology
from app.graph.localize import localize_all


def test_span_fault_between_p2_and_p3(known_topology_poles, known_dt_registry):
    # P3 goes dark, everything else (P1, P2, P4) stays live.
    # Fault should be located on the span P2 -- P3.
    dark_poles = {"P3"}

    topology = build_full_topology(known_topology_poles, known_dt_registry)
    incidents = localize_all(topology, dark_poles, known_topology_poles, known_dt_registry)

    assert len(incidents) == 1
    incident = incidents[0]
    assert incident["incident_type"] == "span"
    assert incident["upstream_pole"] == "P2"
    assert incident["downstream_pole"] == "P3"
    assert incident["affected_poles"] == ["P3"]
    assert incident["topology_status"] == "VERIFIED"
    assert incident["confidence"] == 0.95


def test_span_fault_on_branch_isolates_only_that_branch(known_topology_poles, known_dt_registry):
    # P4 (the spur off P2) goes dark. P3 (the main line continuation) stays
    # live. Fault should be on P2--P4 only, NOT affect P3.
    dark_poles = {"P4"}

    topology = build_full_topology(known_topology_poles, known_dt_registry)
    incidents = localize_all(topology, dark_poles, known_topology_poles, known_dt_registry)

    assert len(incidents) == 1
    incident = incidents[0]
    assert incident["upstream_pole"] == "P2"
    assert incident["downstream_pole"] == "P4"
    assert "P3" not in incident["affected_poles"]
