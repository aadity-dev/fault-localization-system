"""
backend/tests/test_noise_filter.py

The "lying sensor" case: a pole reports dark, but its children are still
live. Physically impossible as a real line fault (power can't skip a dead
wire), so this must be suppressed, not ticketed. This is one of the
explicit disqualifiers in 04-evaluation.md if handled wrong.
"""

from app.graph.build_topology import build_full_topology
from app.graph.localize import localize_all, is_dead_sensor


def test_dead_sensor_produces_no_incident(known_topology_poles, known_dt_registry):
    # P2 reports dark, but its children P3 and P4 are still live.
    # This is impossible as a real fault -- P2's own sensor is broken.
    dark_poles = {"P2"}

    topology = build_full_topology(known_topology_poles, known_dt_registry)
    incidents = localize_all(topology, dark_poles, known_topology_poles, known_dt_registry)

    assert len(incidents) == 0, "a dark pole with live children must NOT produce a ticket"


def test_is_dead_sensor_helper_directly(known_topology_poles, known_dt_registry):
    topology = build_full_topology(known_topology_poles, known_dt_registry)
    g = topology["D-KNOWN"]

    # P2 dark, P3/P4 (its children) live -> dead sensor
    assert is_dead_sensor(g, "P2", dark_poles={"P2"}) is True

    # P2 dark AND P3 dark (a real downstream child also dark) -> not a dead
    # sensor, this looks like a real fault
    assert is_dead_sensor(g, "P2", dark_poles={"P2", "P3"}) is False

    # leaf pole (P3 has no children) -- check doesn't apply, returns False
    assert is_dead_sensor(g, "P3", dark_poles={"P3"}) is False
