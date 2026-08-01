"""
simulator/inject_fault.py

Fault injection against the GENERATED grid. Uses the real (private) topology
-- including the fields that get stripped from pole_registry.csv for the 60%
case -- to correctly determine which poles should actually go dark. Your
backend never sees this ground truth; it only sees the (possibly stripped)
pole_registry.csv, exactly like the real system would.

Three fault types, matching 01-problem-context.md §2:
  - span fault:    live/dark boundary mid-line. Fault is on the edge between
                    two adjacent poles; everything downstream goes dark.
  - dt fault:      every pole under one DT goes dark.
  - feeder fault:  every pole under every DT on that feeder goes dark.

This module does NOT talk to the backend directly -- it just computes
*which poles should go dark*. telemetry_emitter.py turns that into actual
messy HTTP telemetry.
"""

import csv
from collections import defaultdict


def load_poles(path="data/pole_registry.csv"):
    with open(path) as f:
        return list(csv.DictReader(f))


def load_ground_truth(path="data/ground_truth_topology.csv"):
    """
    For DTs with stripped topology, pole_registry.csv has no parent_pole_id.
    The simulator (not the backend under test) still needs to know the real
    wiring to decide who goes dark, so it reads the private ground truth file.
    """
    with open(path) as f:
        rows = list(csv.DictReader(f))
    return {r["pole_id"]: r for r in rows}


def build_children_map(poles, ground_truth):
    """
    parent_pole_id -> [child pole_ids], using real parent info regardless of
    whether it's present in pole_registry.csv or only in ground truth.
    """
    children = defaultdict(list)
    for p in poles:
        parent = p["parent_pole_id"] or ground_truth.get(p["pole_id"], {}).get("true_parent_pole_id")
        if parent:
            children[parent].append(p["pole_id"])
    return children


def downstream_of(pole_id, children_map):
    """BFS: every pole electrically downstream of pole_id, pole_id included."""
    result = []
    stack = [pole_id]
    while stack:
        current = stack.pop()
        result.append(current)
        stack.extend(children_map.get(current, []))
    return result


def inject_span_fault(pole_a_id, pole_b_id, poles=None, ground_truth=None):
    """
    Fault on the span between pole_a (upstream, stays live) and pole_b
    (downstream, goes dark along with everything below it).
    Caller must ensure pole_b is actually the child of pole_a.
    """
    poles = poles or load_poles()
    ground_truth = ground_truth or load_ground_truth()
    children = build_children_map(poles, ground_truth)
    dark_poles = downstream_of(pole_b_id, children)
    return {
        "fault_type": "span",
        "fault_location": f"{pole_a_id} -- {pole_b_id}",
        "dark_poles": dark_poles,
    }


def inject_dt_fault(dt_id, poles=None):
    poles = poles or load_poles()
    dark_poles = [p["pole_id"] for p in poles if p["dt_id"] == dt_id]
    return {
        "fault_type": "dt",
        "fault_location": dt_id,
        "dark_poles": dark_poles,
    }


def inject_feeder_fault(feeder_id, poles=None):
    poles = poles or load_poles()
    dark_poles = [p["pole_id"] for p in poles if p["feeder_id"] == feeder_id]
    return {
        "fault_type": "feeder",
        "fault_location": feeder_id,
        "dark_poles": dark_poles,
    }


def pick_random_span_fault(poles=None, ground_truth=None):
    """Convenience: picks a real parent/child pair at random to fault, for demos/tests."""
    import random
    poles = poles or load_poles()
    ground_truth = ground_truth or load_ground_truth()

    candidates = []
    for p in poles:
        parent = p["parent_pole_id"] or ground_truth.get(p["pole_id"], {}).get("true_parent_pole_id")
        if parent:
            candidates.append((parent, p["pole_id"]))

    pole_a, pole_b = random.choice(candidates)
    return inject_span_fault(pole_a, pole_b, poles, ground_truth)


if __name__ == "__main__":
    result = pick_random_span_fault()
    print(f"Injected {result['fault_type']} fault at {result['fault_location']}")
    print(f"{len(result['dark_poles'])} poles should go dark: {result['dark_poles'][:10]}"
          f"{'...' if len(result['dark_poles']) > 10 else ''}")