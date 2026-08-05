# Fault Localization System

🚀 **Live Demo:** [https://fault-localization-system-1.onrender.com/](https://fault-localization-system-1.onrender.com/)

A system for the (fictional) Karnataka State Power Distribution Board that
turns raw pole-level "is this pole lit?" telemetry into a located,
ticketed fault — cutting the current manual identification time from ~2
hours down to under 2 minutes.

Given only binary pole liveness signals and GPS coordinates (no sensors on
the wire itself), the system infers **where on the network a fault has
occurred** — down to the specific span of line where possible — while
filtering out the noise that would otherwise flood a control room: dead
sensors, scheduled maintenance, duplicate/out-of-order telemetry, and
partial data from a network where 60% of transformers have no recorded
wiring order.

## Quick start

```bash
git clone https://github.com/aadity-dev/fault-localization-system.git
cd fault-localization-system
docker compose up --build
```

Then open:
- **Operator console**: http://localhost:8501
- **API docs**: http://localhost:8000/docs

The system seeds itself with a synthetic ~700-pole grid on first startup — no manual data loading required. Use the **Simulator** panel in the operator console (or `POST /simulate/fault/dt/{dt_id}` via the API) to inject a fault and watch it become a ticket within ~30-40 seconds.

**Optional**: Set `GEMINI_API_KEY` before starting to enable AI-generated, plain-language ticket summaries. Without it, the system automatically falls back to a deterministic template summary, ensuring the core workflow remains unbroken.

```bash
export GEMINI_API_KEY=your-key-here
docker compose up --build
```

## What's in this repo

| File | What it covers |
|------|-----------------|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | System design, the localization algorithm, the 60%-missing-topology approach, API surface, the AI feature |
| [`DEPLOYMENT.md`](DEPLOYMENT.md) | Exact setup commands, environment variables, troubleshooting |
| [`DECISIONS.md`](DECISIONS.md) | Design decisions and documented assumptions, newest first |
| [`AI-WORKFLOW.md`](AI-WORKFLOW.md) | How AI tools were used building this, including specific cases where AI output was wrong and how it was caught |

## Core design points

- **Radial-tree localization**: faults are found as the boundary between
  a live region and a dark region on the network (`app/graph/localize.py`).
- **The 60% missing-topology problem**: where pole wiring order isn't
  recorded, topology is inferred via a geometric Minimum Spanning Tree,
  measured at **87.6% edge-level accuracy** against held-out ground
  truth — see ARCHITECTURE.md for the full methodology.
- **Noise handling**: dead-sensor detection (a dark pole with live
  children is physically impossible as a real fault), scheduled-outage
  cross-checking, and telemetry debouncing all run before a ticket is
  ever created.
- **Verification is telemetry-driven, not manual**: a ticket can only
  move to "verified" when the system independently confirms the
  affected poles are live again — a human marking it "resolved" is
  never sufficient on its own.

## Tests

```bash
cd backend
DATABASE_URL="sqlite:///test.db" python -m pytest tests/ -v
```

32 tests, organized by the specific failure mode each guards against —
span/DT/feeder faults, the missing-topology fallback, dead-sensor
suppression, scheduled-outage handling, ticket lifecycle enforcement,
and the AI feature's fallback guarantee.