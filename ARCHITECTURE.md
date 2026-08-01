## Simulator

Since the department does not provide real data, the simulator is treated
as first-class work, not a test fixture bolted on at the end.

**Grid generation** (`simulator/generate_grid.py`): builds a synthetic
radial tree — substations → feeders → DTs → poles, with branches/spurs —
matching the proportions in 02-data-and-systems.md rather than its absolute
scale (see DECISIONS.md). Critically, we generate the FULL real topology
first, then null seq_on_line/parent_pole_id for a random 60% of DTs
afterward, preserving the real values separately in
ground_truth_topology.csv. This lets us later measure our MST inference's
accuracy against reality, not just eyeball plausibility.

**Fault injection** (`simulator/inject_fault.py`): computes which poles
should go dark for a span/DT/feeder fault, using the private ground-truth
topology (not the stripped CSV) — exactly mirroring how a real fault would
propagate regardless of whether we've digitized that DT's wiring order.

**Telemetry emission** (`simulator/telemetry_emitter.py`): converts a dark-
pole set into realistic, messy HTTP payloads: ~70% dying-breath success
rate, ~8% of devices silently on legacy firmware (no power_lost event at
all), ±90s clock skew, shuffled arrival order, ~5% duplicate delivery,
~3% stale retries up to 6 hours old. Poles with no device are silently
excluded, matching the ~9% coverage gap.

**Load testing** (`simulator/load_test.py`): separate from fault scenarios
— fires synthetic message volume at the ingest endpoint to validate
sustained (≥500 msg/s) and burst (5,000 msgs/10s) throughput targets,
independent of how many unique poles exist in the grid.

**Driving it**: `simulator/run_scenario.py span|dt|feeder|noise` is the
single command (and will back the UI's simulator controls) — satisfies
G5.