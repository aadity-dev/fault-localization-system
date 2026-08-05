# simulator/generate_grid.py
"""
Generates synthetic pole_registry.csv, dt_registry.csv, and
ground_truth_topology.csv matching the proportions described in
02-data-and-systems.md.

Run this directly to regenerate the grid:
    python simulator/generate_grid.py

The CSVs are ALSO committed to data/, so the system works without
running this script -- it's here for reproducibility and as a graded
deliverable (G5).
"""
import csv, os, random, uuid
from pathlib import Path

random.seed(42)  # reproducible — documented in DECISIONS.md

N_SUBSTATIONS = 2
FEEDERS_PER_SUB = 3
DTS_PER_FEEDER = 3
POLES_PER_DT_RANGE = (15, 80)   # brief's real range, biased lower for test grid
PCT_DT_MISSING_TOPOLOGY = 0.60  # 60% missing topology
PCT_POLES_NO_DEVICE = 0.09      # ~9% poles without devices
PCT_PINCODE_MISSING = 0.03      # ~3% missing PIN codes

# Bengaluru wards and PIN codes for realistic data
WARDS = [f"W-{i:03d}" for i in range(1, 200)]
PINCODES = ["560001", "560002", "560008", "560010", "560011", "560017",
            "560018", "560020", "560022", "560024", "560025", "560029",
            "560030", "560032", "560034", "560036", "560038", "560040",
            "560041", "560043", "560045", "560047", "560048", "560050",
            "560051", "560052", "560053", "560054", "560055", "560056",
            "560058", "560060", "560062", "560064", "560066", "560068",
            "560070", "560071", "560073", "560076", "560078", "560079",
            "560080", "560082", "560083", "560084", "560085", "560086",
            "560092", "560094", "560095", "560096", "560097", "560098"]
POLE_TYPES = ["LT-8m-Steel", "LT-9m-Steel", "LT-8m-Concrete", "LT-9m-Concrete",
              "LT-8m-Wood", "LT-10m-Steel"]


def generate_dt_tree(dt_id, dt_lat, dt_lon, n_poles):
    """
    Builds one radial LT line off a DT, with occasional branches (spurs),
    walking outward from the DT coordinate with small lat/lon jitter.
    Returns list of pole dicts with seq_on_line + parent_pole_id.
    """
    poles = []
    lat, lon = dt_lat, dt_lon
    parent = None
    for seq in range(1, n_poles + 1):
        lat += random.uniform(-0.0004, 0.0004)
        lon += random.uniform(-0.0004, 0.0004)
        pole_id = f"P-{uuid.uuid4().hex[:6]}"

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
    """
    Short side-branch (2-5 poles) off an existing pole, simulating
    a service lane or side road off the main LT line.
    """
    spur_len = random.randint(2, 5)
    spur_poles = []
    parent = branch_root_id
    for i in range(spur_len):
        lat += random.uniform(-0.0003, 0.0003)
        lon += random.uniform(-0.0003, 0.0003)
        pole_id = f"P-{uuid.uuid4().hex[:6]}"
        spur_poles.append({
            "pole_id": pole_id, "lat": lat, "lon": lon,
            "dt_id": dt_id,
            "seq_on_line": base_seq + 100 + i,  # high seq to avoid collisions
            "parent_pole_id": parent,
        })
        parent = pole_id
    return spur_poles


def strip_topology_for_60_percent(dts, poles):
    """
    For 60% of DTs (randomly chosen), null out seq_on_line
    and parent_pole_id on every pole under that DT.
    This is the core 'missing topology' condition — must match
    exactly what 02-data-and-systems.md describes.

    Returns the list of dt_ids that were stripped.
    """
    n_strip = int(len(dts) * PCT_DT_MISSING_TOPOLOGY)
    stripped_dts = set(random.sample([d["dt_id"] for d in dts], n_strip))
    for p in poles:
        if p["dt_id"] in stripped_dts:
            p["seq_on_line"] = None
            p["parent_pole_id"] = None
    return stripped_dts


def drop_devices(poles, pct=PCT_POLES_NO_DEVICE):
    """Randomly remove device_id from pct of poles — these are the 'no sensor' gaps."""
    n_drop = int(len(poles) * pct)
    to_drop = random.sample(range(len(poles)), n_drop)
    for i in to_drop:
        poles[i]["device_id"] = None


def drop_pincodes(poles, pct=PCT_PINCODE_MISSING):
    """Randomly remove pincode from pct of poles."""
    n_drop = int(len(poles) * pct)
    to_drop = random.sample(range(len(poles)), n_drop)
    for i in to_drop:
        poles[i]["pincode"] = None


def write_csvs(poles, dts, ground_truth, output_dir):
    """Write all three CSV files to output_dir."""
    os.makedirs(output_dir, exist_ok=True)

    # pole_registry.csv
    pole_fields = ["pole_id", "lat", "lon", "feeder_id", "dt_id",
                    "seq_on_line", "parent_pole_id", "pole_type",
                    "ward", "pincode", "device_id"]
    with open(os.path.join(output_dir, "pole_registry.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=pole_fields)
        w.writeheader()
        for p in poles:
            w.writerow({k: (p.get(k, "") if p.get(k) is not None else "") for k in pole_fields})

    # dt_registry.csv
    dt_fields = ["dt_id", "feeder_id", "lat", "lon", "capacity_kva", "households_served"]
    with open(os.path.join(output_dir, "dt_registry.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=dt_fields)
        w.writeheader()
        for d in dts:
            w.writerow(d)

    # ground_truth_topology.csv — preserves real parent assignments
    gt_fields = ["pole_id", "dt_id", "real_parent_pole_id", "real_seq_on_line"]
    with open(os.path.join(output_dir, "ground_truth_topology.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=gt_fields)
        w.writeheader()
        for gt in ground_truth:
            w.writerow(gt)


if __name__ == "__main__":
    all_poles = []
    all_dts = []
    ground_truth = []

    # Base coordinates: central Bengaluru
    base_lat, base_lon = 12.9716, 77.5946

    for sub_i in range(1, N_SUBSTATIONS + 1):
        for feed_j in range(1, FEEDERS_PER_SUB + 1):
            feeder_id = f"F-{sub_i:02d}-{feed_j:02d}"
            for dt_k in range(1, DTS_PER_FEEDER + 1):
                dt_id = f"D-{sub_i:02d}{feed_j:02d}{dt_k:02d}"
                # spread DTs geographically
                dt_lat = base_lat + random.uniform(-0.01, 0.01)
                dt_lon = base_lon + random.uniform(-0.02, 0.02)
                n_poles = random.randint(*POLES_PER_DT_RANGE)
                capacity = random.choice([100, 250, 500])
                households = random.randint(50, 400)

                all_dts.append({
                    "dt_id": dt_id, "feeder_id": feeder_id,
                    "lat": round(dt_lat, 6), "lon": round(dt_lon, 6),
                    "capacity_kva": capacity, "households_served": households,
                })

                poles = generate_dt_tree(dt_id, dt_lat, dt_lon, n_poles)
                for p in poles:
                    p["feeder_id"] = feeder_id
                    p["pole_type"] = random.choice(POLE_TYPES)
                    p["ward"] = random.choice(WARDS)
                    p["pincode"] = random.choice(PINCODES)
                    p["device_id"] = f"KSPDB-{dt_id}-{p['pole_id']}"
                    p["lat"] = round(p["lat"], 6)
                    p["lon"] = round(p["lon"], 6)

                all_poles.extend(poles)

    # Save ground truth BEFORE stripping topology
    for p in all_poles:
        ground_truth.append({
            "pole_id": p["pole_id"],
            "dt_id": p["dt_id"],
            "real_parent_pole_id": p["parent_pole_id"],
            "real_seq_on_line": p["seq_on_line"],
        })

    # Strip topology for 60% of DTs
    stripped_dts = strip_topology_for_60_percent(all_dts, all_poles)

    # Drop devices from ~9% of poles
    drop_devices(all_poles)

    # Drop pincodes from ~3% of poles
    drop_pincodes(all_poles)

    output_dir = str(Path(__file__).resolve().parent.parent / "data")
    write_csvs(all_poles, all_dts, ground_truth, output_dir)

    # Summary stats
    n_stripped = sum(1 for p in all_poles if p["seq_on_line"] is None)
    n_no_device = sum(1 for p in all_poles if p["device_id"] is None)
    n_no_pin = sum(1 for p in all_poles if p["pincode"] is None)
    print(f"Generated {len(all_poles)} poles across {len(all_dts)} DTs")
    print(f"  Stripped topology: {len(stripped_dts)}/{len(all_dts)} DTs ({len(stripped_dts)/len(all_dts):.0%})")
    print(f"  No device: {n_no_device}/{len(all_poles)} poles ({n_no_device/len(all_poles):.1%})")
    print(f"  No pincode: {n_no_pin}/{len(all_poles)} poles ({n_no_pin/len(all_poles):.1%})")
    print(f"  Output: {output_dir}/")