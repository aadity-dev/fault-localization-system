## Tools used
Claude (Sonnet) for architecture discussion, code generation, and reviewing
design tradeoffs against the brief's grading weights.

## What was delegated vs. written by hand
Delegated: simulator scaffolding (generate_grid.py, inject_fault.py,
telemetry_emitter.py, run_scenario.py, load_test.py) — boilerplate-heavy,
mechanical translation of documented rules (firmware percentages, clock
skew ranges, etc.) into code. Reviewed and ran every file myself before
accepting it; verified output against expected proportions
(9.0% no-device, 60% stripped-topology, ~28 poles downstream on a sample
span fault) rather than trusting it blindly.

## Cases where AI output needed correction
[Fill in as you hit these — you haven't yet, since Phase 1 ran clean on
first pass. Genuine ones will show up in Phase 2 — MST edge cases, or
places where a suggested approach didn't match your judgment. Don't
fabricate one; wait for a real case.]

## Estimate of AI-generated code
Roughly [X]% of simulator code is AI-generated and reviewed/run by me;
backend graph logic (Phase 2 onward) — update as you write it yourself vs.
delegate it.