"""
backend/app/graph/localize.py

Turns a set of "pole is dark" signals into a small number of located
incidents, using the topology graphs from build_topology.py.

Core idea (01-problem-context.md §2): the fault is on the EDGE between the
last live pole and the first dark pole. So for each DT's graph, we look
for the frontier between the live region and the dark region -- that
frontier IS the fault.

Handles:
  - span fault: some poles under a DT are dark, others live -> boundary
    edges within the DT's graph.
  - DT fault: every pole under the DT is dark -> report at the DT level,
    not as N separate span faults.
  - feeder fault: every DT (and therefore every pole) on a feeder is dark
    -> report at the feeder level, not as M separate DT faults.
  - multiple simultaneous faults: independent boundaries in the same or
    different DTs are reported as separate incidents.
  - grouping: everything downstream of one boundary is ONE incident, no
    matter how many poles are affected.

Framework-free: takes a topology dict (from build_topology) and a dark-pole
set, returns plain dicts describing incidents. No DB, no FastAPI here --
keeps this independently testable, which is what the 3-5 required tests
target.
"""

import networkx as nx


def find_span_boundaries(g, dark_poles):
    """
    Within one DT's graph, finds every edge (parent, child) where parent
    is live and child is dark. Each such edge is a candidate span-fault
    boundary. Returns list of (parent_id, child_id) tuples.
    """
    boundaries = []
    for parent, child in g.edges():
        parent_dark = parent in dark_poles
        child_dark = child in dark_poles
        if not parent_dark and child_dark:
            boundaries.append((parent, child))
    return boundaries


def downstream_of(g, node_id):
    """All poles electrically downstream of node_id (node included), via BFS."""
    if node_id not in g:
        return [node_id]
    return list(nx.descendants(g, node_id)) + [node_id]


def is_dead_sensor(g, pole_id, dark_poles):
    """
    The 'lying sensor' check: a pole is dark but everything directly
    downstream of it is still live. Physically impossible as a real line
    fault (power can't skip a dead wire) -- so this is a broken sensor,
    not an outage. See 01-problem-context.md §2.
    """
    if pole_id not in g:
        return False
    children = list(g.successors(pole_id))
    if not children:
        return False  # leaf pole with no children -- can't apply this check
    return all(child not in dark_poles for child in children)


def localize_dt(dt_id, g, dark_poles_in_dt, all_poles_in_dt):
    """
    Localizes faults within a single DT's topology.

    Returns a list of incident dicts. Each incident is one of:
      - "dt"   : every pole under the DT is dark, no live pole beneath it
      - "span" : a live/dark boundary edge within the DT's line

    Poles that are dark but are actually just lying sensors (live children
    beneath them) are filtered out before boundary-finding, so they never
    generate a ticket.
    """
    incidents = []

    # filter out lying sensors -- if the "dark" signal is physically
    # impossible as a real fault, treat that pole as if it hadn't reported
    real_dark = set()
    for pole_id in dark_poles_in_dt:
        if is_dead_sensor(g, pole_id, dark_poles_in_dt):
            continue  # suppressed -- not added to real_dark
        real_dark.add(pole_id)

    if not real_dark:
        return incidents

    # DT-level fault: every pole with a device in this DT is dark, and none
    # of them have any live children -- whole transformer down
    poles_with_devices = {p["pole_id"] for p in all_poles_in_dt if p.get("device_id")}
    if poles_with_devices and poles_with_devices.issubset(real_dark):
        incidents.append({
            "incident_type": "dt",
            "dt_id": dt_id,
            "dark_pole_count": len(real_dark),
            "affected_poles": sorted(real_dark),
            "confidence": _dt_confidence(g),
        })
        return incidents

    # span-level faults: find each live->dark boundary edge
    boundaries = find_span_boundaries(g, real_dark)

    # merge boundaries whose downstream sets overlap (same incident, found
    # via two entry points) -- keep only the highest (most upstream) boundary
    # per connected dark region
    seen_downstream = set()
    for parent, child in boundaries:
        downstream = set(downstream_of(g, child))
        if downstream & seen_downstream:
            continue  # already covered by a more upstream boundary
        seen_downstream |= downstream

        edge_data = g.get_edge_data(parent, child) or {}
        incidents.append({
            "incident_type": "span",
            "dt_id": dt_id,
            "fault_location": f"{parent} -- {child}",
            "upstream_pole": parent,
            "downstream_pole": child,
            "dark_pole_count": len(downstream & real_dark),
            "affected_poles": sorted(downstream & real_dark),
            "topology_status": edge_data.get("status", "UNKNOWN"),
            "confidence": edge_data.get("confidence", 0.5),
        })

    return incidents


def _dt_confidence(g):
    """DT-level faults are confident regardless of topology quality --
    we don't need to know pole order to know the whole DT is dark."""
    return 0.95


def localize_feeder(feeder_id, dt_incidents_by_dt, all_dt_ids_on_feeder):
    """
    Rolls DT-level incidents up to a feeder-level incident if EVERY DT on
    the feeder reported a full DT-level fault -- that's a feeder/HT-side
    failure, not N independent DT failures, and should be one ticket.
    """
    dt_fault_ids = {
        dt_id for dt_id, incidents in dt_incidents_by_dt.items()
        if any(i["incident_type"] == "dt" for i in incidents)
    }

    # A feeder with only one DT: a full DT outage is indistinguishable from
    # a feeder outage by pole data alone. We deliberately report the more
    # specific answer (DT-level) rather than guess feeder-level -- see
    # DECISIONS.md. Feeder-level rollup only applies when there's more than
    # one DT confirming the same feeder-wide pattern.
    if len(all_dt_ids_on_feeder) < 2:
        return None

    if dt_fault_ids and dt_fault_ids == set(all_dt_ids_on_feeder):
        total_poles = sum(
            i["dark_pole_count"]
            for incidents in dt_incidents_by_dt.values()
            for i in incidents
            if i["incident_type"] == "dt"
        )
        return [{
            "incident_type": "feeder",
            "feeder_id": feeder_id,
            "affected_dts": sorted(dt_fault_ids),
            "dark_pole_count": total_poles,
            "confidence": 0.95,
        }]
    return None


def localize_all(topology_by_dt, dark_poles, poles, dt_registry):
    """
    Main entry point. topology_by_dt: dict[dt_id] -> networkx.DiGraph
    (from build_topology.build_full_topology). dark_poles: set of pole_ids
    currently reporting dark. poles: full pole list (for device/DT lookup).
    dt_registry: list of dt dicts (for feeder grouping).

    Returns a flat list of incident dicts -- this is what gets turned into
    tickets by the caller.
    """
    poles_by_dt = {}
    for p in poles:
        poles_by_dt.setdefault(p["dt_id"], []).append(p)

    dt_incidents_by_dt = {}
    for dt_id, g in topology_by_dt.items():
        dt_poles = poles_by_dt.get(dt_id, [])
        dark_in_dt = {p["pole_id"] for p in dt_poles if p["pole_id"] in dark_poles}
        if not dark_in_dt:
            continue
        dt_incidents_by_dt[dt_id] = localize_dt(dt_id, g, dark_in_dt, dt_poles)

    # feeder-level rollup: check each feeder, merge its DTs' incidents into
    # one if the whole feeder is down
    feeder_to_dts = {}
    for dt in dt_registry:
        feeder_to_dts.setdefault(dt["feeder_id"], []).append(dt["dt_id"])

    all_incidents = []
    absorbed_dts = set()

    for feeder_id, dt_ids in feeder_to_dts.items():
        relevant = {dt_id: dt_incidents_by_dt[dt_id] for dt_id in dt_ids if dt_id in dt_incidents_by_dt}
        feeder_incident = localize_feeder(feeder_id, relevant, dt_ids)
        if feeder_incident:
            all_incidents.extend(feeder_incident)
            absorbed_dts.update(relevant.keys())

    for dt_id, incidents in dt_incidents_by_dt.items():
        if dt_id in absorbed_dts:
            continue  # already reported as part of a feeder incident
        all_incidents.extend(incidents)

    return all_incidents
