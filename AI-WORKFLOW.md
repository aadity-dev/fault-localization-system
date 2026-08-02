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

## Case: AI-generated database.py and models.py got cross-contaminated during manual copy-paste
While wiring up the backend schema, the SQLAlchemy `Base` definition
(belongs in database.py) and the Pole/Transformer ORM classes (belongs in
models.py) ended up merged into a single file during manual editing,
causing a NameError (Column undefined) and a self-referential import
error. Caught by actually running the import checks
(`python -c "from app.database import Base"`) rather than assuming the
paste was correct, and by inspecting file contents directly with `cat`
before re-testing. This is a case where the AI-authored code was correct
in isolation but broke during manual reassembly — the fix was verifying
file contents against intent, not just re-running and hoping.



### Case: feeder-rollup logic wrongly fired on single-DT feeders
First version of localize_feeder() rolled up to a feeder incident whenever
"every DT on the feeder" matched a full-DT-outage set — but for a
single-DT feeder, that's trivially always true. Caught by the required
pytest suite (test_full_dt_outage_is_one_incident failed, asserting
'feeder' != 'dt'), not by manual inspection. Fixed by requiring >= 2 DTs
before feeder-level rollup applies. Reproduced independently by running
the same test suite myself before accepting the fix.

### Case: repeated directory-context errors during manual file assembly
Multiple ModuleNotFoundError / ImportError failures during Phases 0-3
traced back to running commands from the wrong working directory
(backend/ vs backend/app/ vs repo root), plus two typo'd filenames
(__intit__.py, ingests.py) introduced during manual copy-paste of
AI-generated code. None were logic errors in the AI-generated code itself
-- all were caught by actually running the commands and reading tracebacks
carefully rather than assuming a paste or rename had succeeded. This
pattern is the clearest evidence in this project of verifying AI output
rather than trusting it blindly: every fix came from inspecting real
file contents (cat, ls) and real error messages, not from re-generating
code and hoping.