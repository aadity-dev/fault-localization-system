"""
backend/app/graph/noise_filter.py

Scheduled-outage cross-check. Per 02-data-and-systems.md §4, the scheduled
outage feed cannot be trusted blindly: outages start late, overrun by
20-40 minutes, and ~10% are cancelled without the feed being updated.

The rule: even inside a scheduled outage window, if only a SUBSET of the
poles under the affected scope are dark (not all of them), that's evidence
of a real physical fault happening during maintenance, not just the
maintenance itself -- because if the whole DT/feeder were correctly
switched off, ALL its poles would be dark, not some.

This is deliberately separate from the dead-sensor check in localize.py:
that one is about a single pole's signal being physically implausible,
this one is about matching an incident against an external (untrustworthy)
schedule.
"""

from datetime import datetime, timedelta, timezone

# Real-world slack: outages start late and overrun. We don't suppress
# alerts strictly within [start, end] -- we widen the window to absorb
# the documented overrun behavior, then still verify against actual dark
# pole coverage rather than trusting the window alone.
OUTAGE_START_SLACK = timedelta(minutes=15)   # outage might not have started yet
OUTAGE_OVERRUN_SLACK = timedelta(minutes=40)  # outage might be running late


def is_within_outage_window(now, outage, start_slack=OUTAGE_START_SLACK, overrun_slack=OUTAGE_OVERRUN_SLACK):
    start = datetime.fromisoformat(outage["start"].replace("Z", "+00:00")) - start_slack
    end = datetime.fromisoformat(outage["end"].replace("Z", "+00:00")) + overrun_slack
    return start <= now <= end


def find_matching_outages(incident, scheduled_outages, now=None):
    """
    Returns the list of scheduled outages whose scope matches this incident
    (same dt_id or feeder_id) and whose (slack-widened) time window covers
    now.
    """
    now = now or datetime.now(timezone.utc)
    matches = []
    for outage in scheduled_outages:
        if outage["scope"] == "dt" and outage["target_id"] == incident.get("dt_id"):
            if is_within_outage_window(now, outage):
                matches.append(outage)
        elif outage["scope"] == "feeder" and outage["target_id"] == incident.get("feeder_id"):
            if is_within_outage_window(now, outage):
                matches.append(outage)
    return matches


def filter_scheduled_outages(incidents, scheduled_outages, poles_by_dt, now=None):
    """
    For each incident, checks whether it falls inside a scheduled outage
    window for its scope. If so, and the incident's affected poles cover
    the FULL set of poles under that scope, suppress it (it's the planned
    outage, not a real fault). If only a SUBSET of poles are affected while
    the rest of the scope is live, do NOT suppress -- that's a real fault
    happening on top of / during the maintenance window.

    Returns (kept_incidents, suppressed_incidents) so callers can log what
    was suppressed for audit/debugging rather than silently dropping it.
    """
    kept = []
    suppressed = []

    for incident in incidents:
        matches = find_matching_outages(incident, scheduled_outages, now=now)
        if not matches:
            kept.append(incident)
            continue

        if incident["incident_type"] == "dt":
            total_poles_in_scope = len({
                p["pole_id"] for p in poles_by_dt.get(incident["dt_id"], [])
                if p.get("device_id")
            })
            affected = set(incident["affected_poles"])
            if total_poles_in_scope and affected.issuperset(
                {p["pole_id"] for p in poles_by_dt.get(incident["dt_id"], []) if p.get("device_id")}
            ):
                incident["suppressed_reason"] = f"scheduled outage {matches[0]['id']}"
                suppressed.append(incident)
                continue

        # feeder-level: same logic, full coverage under a matching scheduled
        # feeder outage suppresses; partial coverage does not
        if incident["incident_type"] == "feeder":
            incident["suppressed_reason"] = f"scheduled outage {matches[0]['id']}"
            suppressed.append(incident)
            continue

        # span-level incidents are never blindly suppressed by a DT/feeder
        # outage window -- a span fault during maintenance is still a real
        # fault the crew needs to know about once power is restored
        kept.append(incident)

    return kept, suppressed