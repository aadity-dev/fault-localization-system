"""
backend/app/graph/score_inference.py

Standalone evaluation script (NOT part of the running app -- this reads
simulator/ground_truth_topology.csv, which the backend itself never
touches). Run this to get a real, measured accuracy number for how often
the MST inference reconstructs the correct parent-child edge, instead of
guessing at one for ARCHITECTURE.md.

Run:
    python -m app.graph.score_inference
"""

import csv

from app.graph.build_topology import build_full_topology


def load_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def main():
    poles = load_csv("../data/pole_registry.csv")
    dts = load_csv("../data/dt_registry.csv")
    ground_truth_rows = load_csv("../data/ground_truth_topology.csv")

    ground_truth = {r["pole_id"]: r["true_parent_pole_id"] for r in ground_truth_rows}

    topology = build_full_topology(poles, dts)

    n_inferred_dts = 0
    n_verified_dts = 0
    correct_edges = 0
    total_inferred_edges = 0

    for dt_id, g in topology.items():
        edge_statuses = {(u, v): d["status"] for u, v, d in g.edges(data=True)}
        if not edge_statuses:
            continue
        sample_status = next(iter(edge_statuses.values()))

        if sample_status == "VERIFIED":
            n_verified_dts += 1
            continue

        n_inferred_dts += 1
        # for each pole in this DT that has a ground-truth parent, check
        # whether our inferred graph gave it the SAME parent
        inferred_parent = {}
        for u, v in g.edges():
            inferred_parent[v] = u

        for pole_id, true_parent in ground_truth.items():
            if pole_id not in inferred_parent:
                continue
            total_inferred_edges += 1
            if inferred_parent[pole_id] == true_parent:
                correct_edges += 1

    print(f"Total DTs: {len(topology)}")
    print(f"  Known topology (VERIFIED): {n_verified_dts}")
    print(f"  Missing topology (INFERRED via MST): {n_inferred_dts}")
    print()
    if total_inferred_edges > 0:
        accuracy = correct_edges / total_inferred_edges
        print(f"MST inference accuracy: {correct_edges}/{total_inferred_edges} "
              f"edges match ground truth ({accuracy:.1%})")
    else:
        print("No inferred edges found to score.")


if __name__ == "__main__":
    main()
