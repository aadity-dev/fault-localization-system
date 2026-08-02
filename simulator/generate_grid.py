# simulator/generate_grid.py
"""
Generates synthetic pole_registry.csv and dt_registry.csv
matching the proportions described in 02-data-and-systems.md
"""
import csv, random, uuid
from math import radians, cos, sin 
#generate gps coordinates

random.seed(42)  # reproducible — put this in DECISIONS.md

N_SUBSTATIONS = 2
FEEDERS_PER_SUB = 3
DTS_PER_FEEDER = 3
POLES_PER_DT_RANGE = (9, 240)   # brief's real range, but bias toward lower end for testing
PCT_DT_MISSING_TOPOLOGY = 0.60 #missing topology
PCT_POLES_NO_DEVICE = 0.09 #poles without devices
PCT_PINCODE_MISSING = 0.03 #missing PIN codes

def generate_dt_tree(dt_id, dt_lat, dt_lon, n_poles):
    """
    Builds one radial LT line off a DT, with 1-3 branches,
    walking outward from the DT coordinate with small lat/lon jitter.
    Returns list of pole dicts with seq_on_line + parent_pole_id.
    """
    poles = []
    # main run
    lat, lon = dt_lat, dt_lon
    parent = None
    for seq in range(1, n_poles + 1):
        lat += random.uniform(-0.0004, 0.0004)
        lon += random.uniform(-0.0004, 0.0004)
        pole_id = f"P-{uuid.uuid4().hex[:6]}" #Creates IDs likeP-a93f21 intead of p1, and p2 till 6 is good for ploes data which willnot be short or long
        poles.append({
            "pole_id": pole_id, "lat": lat, "lon": lon,
            "dt_id": dt_id, "seq_on_line": seq, "parent_pole_id": parent
        })
        parent = pole_id
        # occasionally branch off (spur)
        if random.random() < 0.15 and seq > 2:
            poles += generate_spur(parent, lat, lon, dt_id, seq)
    return poles

def generate_spur(branch_root_id, lat, lon, dt_id, base_seq):
    # short side-branch off an existing pole
    ...

def strip_topology_for_60_percent(dts, poles):
    """
    For 60% of DTs (randomly chosen), null out seq_on_line
    and parent_pole_id on every pole under that DT.
    This is the core 'missing topology' condition — must match
    exactly what 02-data-and-systems.md describes.
    """
    ...

def drop_devices(poles, pct=0.09):
    """Randomly remove device_id from pct of poles — these are the 'no sensor' gaps."""
    ...

def write_csvs(poles, dts):
    ...

if __name__ == "__main__":
    # build substations -> feeders -> DTs -> poles
    # call strip_topology_for_60_percent AFTER generating full topology
    # (you need the real topology to test your MST inference against later!)
    ...