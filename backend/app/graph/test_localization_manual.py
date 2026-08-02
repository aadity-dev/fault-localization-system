"""
backend/app/graph/test_localization_manual.py

Manual integration test -- ties simulator/inject_fault.py's fault
generation together with build_topology.py + localize.py, to prove the
whole pipeline works end to end against the REAL generated grid, not a
tiny hand-built fixture.

This is exploratory/manual verification. The actual required pytest suite
(backend/tests/test_localize_*.py) uses small hand-built fixtures per the
brief's guidance -- see conftest.py, added separately.

Run:
    python -m app.graph.test_localization_manual
"""

import csv
import sys

sys.path.insert(0, "../simulator")

from app.graph.build_topology import build_full_topology
from app.graph.localize import localize_all


def load_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def test_span_fault():
    print("\n=== TEST: span fault ===")
    sys.path.insert(0, "../simulator")
    from inject_fault import pick_random_span_fault, load_poles as sim_load_poles

    poles = load_csv("../data/pole_registry.csv")
    dts = load_csv("../data/dt_registry.csv")

    result = pick_random_span_fault()
    print(f"Injected: {result['fault_location']}, {len(result['dark_poles'])} poles should go dark")

    dark_poles = set(result["dark_poles"])
    topology = build_full_topology(poles, dts)
    incidents = localize_all(topology, dark_poles, poles, dts)

    print(f"Localization found {len(incidents)} incident(s):")
    for inc in incidents:
        print(f"  {inc['incident_type']:6s} conf={inc.get('confidence', 0):.2f} "
              f"poles={inc['dark_pole_count']:3d} "
              f"location={inc.get('fault_location', inc.get('dt_id', inc.get('feeder_id')))}")

    assert len(incidents) == 1, f"Expected exactly 1 incident, got {len(incidents)}"
    assert incidents[0]["incident_type"] == "span", f"Expected span, got {incidents[0]['incident_type']}"
    print("PASS: exactly one span incident found")


def test_dt_fault():
    print("\n=== TEST: DT fault ===")
    sys.path.insert(0, "../simulator")
    from inject_fault import inject_dt_fault

    poles = load_csv("../data/pole_registry.csv")
    dts = load_csv("../data/dt_registry.csv")

    target_dt = dts[0]["dt_id"]
    result = inject_dt_fault(target_dt, poles)
    dark_poles = set(result["dark_poles"])
    print(f"Injected DT fault at {target_dt}, {len(dark_poles)} poles should go dark")

    topology = build_full_topology(poles, dts)
    incidents = localize_all(topology, dark_poles, poles, dts)

    print(f"Localization found {len(incidents)} incident(s):")
    for inc in incidents:
        print(f"  {inc['incident_type']:6s} conf={inc.get('confidence', 0):.2f} poles={inc['dark_pole_count']}")

    assert len(incidents) == 1, f"Expected exactly 1 incident, got {len(incidents)}"
    assert incidents[0]["incident_type"] == "dt", f"Expected dt, got {incidents[0]['incident_type']}"
    print("PASS: exactly one DT-level incident found")


def test_dead_sensor_suppressed():
    print("\n=== TEST: dead sensor is NOT a fault ===")
    poles = load_csv("../data/pole_registry.csv")
    dts = load_csv("../data/dt_registry.csv")

    # find a pole that has children (not a leaf) so the dead-sensor check applies
    topology = build_full_topology(poles, dts)
    target_pole = None
    target_dt = None
    for dt_id, g in topology.items():
        for node in g.nodes():
            if g.out_degree(node) > 0:
                target_pole = node
                target_dt = dt_id
                break
        if target_pole:
            break

    print(f"Marking {target_pole} (in {target_dt}) dark, with its children still live")
    dark_poles = {target_pole}  # only this one pole -- children remain "live" (not in dark set)

    incidents = localize_all(topology, dark_poles, poles, dts)
    print(f"Localization found {len(incidents)} incident(s) — expected 0")
    assert len(incidents) == 0, f"Expected 0 incidents (dead sensor), got {len(incidents)}"
    print("PASS: dead sensor correctly suppressed, no false ticket")


def test_multiple_simultaneous_faults():
    print("\n=== TEST: three simultaneous span faults ===")
    sys.path.insert(0, "../simulator")
    from inject_fault import load_poles as sim_load_poles, load_ground_truth, inject_span_fault
    import random

    poles = load_csv("../data/pole_registry.csv")
    dts = load_csv("../data/dt_registry.csv")
    ground_truth = load_ground_truth()

    candidates = []
    for p in poles:
        parent = p["parent_pole_id"] or ground_truth.get(p["pole_id"], {}).get("true_parent_pole_id")
        if parent:
            candidates.append((parent, p["pole_id"]))

    random.seed(7)
    chosen = random.sample(candidates, 3)
    all_dark = set()
    for pole_a, pole_b in chosen:
        result = inject_span_fault(pole_a, pole_b, poles, ground_truth)
        all_dark |= set(result["dark_poles"])
        print(f"  injected span fault at {pole_a} -- {pole_b}")

    topology = build_full_topology(poles, dts)
    incidents = localize_all(topology, all_dark, poles, dts)
    span_incidents = [i for i in incidents if i["incident_type"] == "span"]

    print(f"Localization found {len(incidents)} total incident(s), {len(span_incidents)} span-type")
    for inc in incidents:
        print(f"  {inc['incident_type']:6s} poles={inc['dark_pole_count']}")

    # Note: if two chosen faults happen to land in the same DT with one
    # downstream of the other, they could legitimately merge into fewer
    # incidents -- that's correct behavior, not a bug. We assert >= 1 and
    # <= 3, and print the detail so it can be eyeballed.
    assert 1 <= len(incidents) <= 3
    print(f"PASS: {len(incidents)} incident(s) for 3 injected faults (merging, if any, is expected/correct)")


if __name__ == "__main__":
    test_span_fault()
    test_dt_fault()
    test_dead_sensor_suppressed()
    test_multiple_simultaneous_faults()
    print("\n=== all manual integration tests passed ===")
