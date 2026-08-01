"""
simulator/run_scenario.py

The single entry point that ties generate_grid.py + inject_fault.py +
telemetry_emitter.py together into one command. This is what Phase 4's
"drivable from the UI or one documented command" requirement (G5) points at
-- the Streamlit UI's "inject fault" button will call the same functions
this script calls.

Run directly for manual testing:
    python simulator/run_scenario.py span
    python simulator/run_scenario.py dt --dt-id D-010101
    python simulator/run_scenario.py feeder --feeder-id F-01-01
    python simulator/run_scenario.py noise            # dead sensor, no real fault
    python simulator/run_scenario.py --live            # actually POST, not dry-run
"""

import argparse
import random

from inject_fault import (
    load_poles, load_ground_truth,
    inject_span_fault, inject_dt_fault, inject_feeder_fault,
    pick_random_span_fault,
)
from telemetry_emitter import emit_outage_telemetry, emit_dead_sensor_noise


def poles_by_id(poles):
    return {p["pole_id"]: p for p in poles}


def run_span(poles, live):
    result = pick_random_span_fault(poles)
    print(f"[SPAN FAULT] at {result['fault_location']}, {len(result['dark_poles'])} poles affected")
    by_id = poles_by_id(poles)
    dark_pole_dicts = [by_id[pid] for pid in result["dark_poles"] if pid in by_id]
    payloads = emit_outage_telemetry(dark_pole_dicts, dry_run=not live)
    print(f"Emitted {len(payloads)} telemetry messages (device-less/legacy-firmware poles silently excluded)")
    return result


def run_dt(poles, dt_id, live):
    result = inject_dt_fault(dt_id, poles)
    print(f"[DT FAULT] at {result['fault_location']}, {len(result['dark_poles'])} poles affected")
    by_id = poles_by_id(poles)
    dark_pole_dicts = [by_id[pid] for pid in result["dark_poles"] if pid in by_id]
    payloads = emit_outage_telemetry(dark_pole_dicts, dry_run=not live)
    print(f"Emitted {len(payloads)} telemetry messages")
    return result


def run_feeder(poles, feeder_id, live):
    result = inject_feeder_fault(feeder_id, poles)
    print(f"[FEEDER FAULT] at {result['fault_location']}, {len(result['dark_poles'])} poles affected")
    by_id = poles_by_id(poles)
    dark_pole_dicts = [by_id[pid] for pid in result["dark_poles"] if pid in by_id]
    payloads = emit_outage_telemetry(dark_pole_dicts, dry_run=not live)
    print(f"Emitted {len(payloads)} telemetry messages")
    return result


def run_noise(poles, live):
    """Dead sensor case: one pole goes silent, power stays fine, no real fault.
    Correct system behaviour: NO ticket should be raised for this."""
    candidates = [p for p in poles if p.get("device_id")]
    pole = random.choice(candidates)
    print(f"[NOISE] dead sensor at {pole['pole_id']} -- power is fine, this should NOT produce a ticket")
    payloads = emit_dead_sensor_noise(pole, dry_run=not live)
    print(f"Emitted {len(payloads)} telemetry message(s)")
    return pole


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", choices=["span", "dt", "feeder", "noise"])
    parser.add_argument("--dt-id", help="required for 'dt' scenario")
    parser.add_argument("--feeder-id", help="required for 'feeder' scenario")
    parser.add_argument("--pole-file", default="data/pole_registry.csv")
    parser.add_argument("--live", action="store_true", help="actually POST to backend instead of dry-run")
    args = parser.parse_args()

    poles = load_poles(args.pole_file)

    if args.scenario == "span":
        run_span(poles, args.live)
    elif args.scenario == "dt":
        if not args.dt_id:
            parser.error("--dt-id is required for the 'dt' scenario")
        run_dt(poles, args.dt_id, args.live)
    elif args.scenario == "feeder":
        if not args.feeder_id:
            parser.error("--feeder-id is required for the 'feeder' scenario")
        run_feeder(poles, args.feeder_id, args.live)
    elif args.scenario == "noise":
        run_noise(poles, args.live)