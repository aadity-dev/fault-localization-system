"""
frontend/app.py

Operator console for the control room. Design reasoning (belongs in
ARCHITECTURE.md's "UI reasoning" section):

  - The person using this is NOT an engineer, and it's 2 a.m. The most
    important thing (open tickets, sorted by severity) must dominate the
    screen. No login, no settings, no clutter.
  - Confidence is communicated honestly, not hidden. A span fault on
    INFERRED topology shows a visibly different badge than VERIFIED --
    an operator should be able to tell at a glance whether to fully trust
    the pinpoint or expect it might be a DT-zone estimate.
  - The simulator panel is deliberately visible and separate from the
    "real" operator view, clearly labeled, so a reviewer can drive a
    fault and watch it become a ticket without touching a terminal --
    this satisfies G5 (drivable from the public URL).
  - Feeder-level and DT-level faults intentionally do NOT get a precise
    map pin (see backend/app/services/ticket_creation.py) -- the UI
    reflects that honestly instead of inventing a fake coordinate.
"""

import os
import time
from datetime import datetime, timezone

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="Fault Control Room", layout="wide")

# Local dev (running `streamlit run app.py` directly): defaults to
# localhost. Inside Docker Compose: set via the API_BASE env var to
# http://backend:8000 (the service name), since "localhost" inside a
# container refers to the container itself, not the backend container.
API_BASE = os.getenv("API_BASE", "http://localhost:8000")

STATUS_COLORS = {
    "detected": "🔴",
    "acknowledged": "🟠",
    "crew_assigned": "🟡",
    "resolved": "🔵",
    "verified": "🟢",
    "closed": "⚪",
}

NEXT_STATUS = {
    "detected": "acknowledged",
    "acknowledged": "crew_assigned",
    "crew_assigned": "resolved",
}


def api_get(path, params=None):
    try:
        r = requests.get(f"{API_BASE}{path}", params=params, timeout=5)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        st.error(f"API error calling GET {path}: {e}")
        return None


def api_post(path, json=None):
    try:
        r = requests.post(f"{API_BASE}{path}", json=json, timeout=10)
        if r.status_code >= 400:
            return {"_error": True, "status": r.status_code, "detail": r.json().get("detail", r.text)}
        return r.json()
    except requests.RequestException as e:
        return {"_error": True, "status": None, "detail": str(e)}


def api_patch(path, json=None):
    try:
        r = requests.patch(f"{API_BASE}{path}", json=json, timeout=10)
        if r.status_code >= 400:
            return {"_error": True, "status": r.status_code, "detail": r.json().get("detail", r.text)}
        return r.json()
    except requests.RequestException as e:
        return {"_error": True, "status": None, "detail": str(e)}


def age_minutes(iso_ts):
    try:
        ts = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        return int((datetime.now(timezone.utc) - ts).total_seconds() / 60)
    except Exception:
        return None


# ---------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------
st.title("⚡ Fault Control Room")
st.caption("Karnataka State Power Distribution Board — subdivision fault localization")

col_refresh, col_auto = st.columns([1, 3])
with col_refresh:
    if st.button("🔄 Refresh now"):
        st.rerun()
with col_auto:
    auto_refresh = st.checkbox("Auto-refresh every 10s", value=False)

# ---------------------------------------------------------------------
# Ticket list — the primary view, dominates the screen
# ---------------------------------------------------------------------
tickets = api_get("/tickets") or []
open_tickets = [t for t in tickets if t["status"] != "closed"]

st.subheader(f"Open incidents ({len(open_tickets)})")

if not open_tickets:
    st.success("No active faults. Grid is quiet.")
else:
    # sort most-affected / most-recent first -- severity dominates
    open_tickets_sorted = sorted(open_tickets, key=lambda t: -t["affected_pole_count"])

    for t in open_tickets_sorted:
        confidence_badge = "🟢 VERIFIED topology" if t.get("topology_status") == "VERIFIED" else "🟡 INFERRED topology (estimated)"
        age = age_minutes(t["detected_at"])
        age_str = f"{age} min ago" if age is not None else "just now"

        with st.container(border=True):
            top = st.columns([1, 3, 2, 2, 2])
            top[0].markdown(f"### {STATUS_COLORS.get(t['status'], '⚫')}")
            with top[1]:
                if t["incident_type"] == "span":
                    st.markdown(f"**Span fault** — `{t['upstream_pole']}` → `{t['downstream_pole']}`")
                elif t["incident_type"] == "dt":
                    st.markdown(f"**Transformer fault** — `{t['dt_id']}`")
                elif t["incident_type"] == "feeder":
                    st.markdown(f"**Feeder fault** — `{t['feeder_id']}`")
                st.caption(f"{t['affected_pole_count']} pole(s) affected · detected {age_str}")
            top[2].markdown(f"**{t['status'].replace('_', ' ').title()}**")
            top[3].markdown(confidence_badge)
            if t.get("pincode"):
                top[4].markdown(f"📍 PIN {t['pincode']}")
            elif t["incident_type"] == "feeder":
                top[4].markdown("_Zone-level — no single pin_")

            if t.get("fault_lat") and t.get("fault_lon"):
                st.caption(f"Navigate to: {t['fault_lat']:.6f}, {t['fault_lon']:.6f}")

            action_cols = st.columns(5)
            if t["status"] in NEXT_STATUS:
                next_status = NEXT_STATUS[t["status"]]
                if action_cols[0].button(f"→ {next_status.replace('_', ' ').title()}", key=f"advance-{t['id']}"):
                    result = api_patch(f"/tickets/{t['id']}/status", json={"new_status": next_status})
                    if result and result.get("_error"):
                        st.error(f"Rejected: {result['detail']}")
                    else:
                        st.rerun()

            if t["status"] == "resolved":
                if action_cols[1].button("✅ Verify (check telemetry)", key=f"verify-{t['id']}"):
                    result = api_post(f"/tickets/{t['id']}/verify")
                    if result and result.get("_error"):
                        st.warning(f"Not yet confirmed live: {result['detail']}")
                    else:
                        st.success("Verified from telemetry!")
                        st.rerun()

            if t["status"] == "verified":
                if action_cols[2].button("📁 Close", key=f"close-{t['id']}"):
                    api_patch(f"/tickets/{t['id']}/status", json={"new_status": "closed"})
                    st.rerun()

# ---------------------------------------------------------------------
# Map view
# ---------------------------------------------------------------------
st.subheader("Map")
mappable = [t for t in open_tickets if t.get("fault_lat") and t.get("fault_lon")]
if mappable:
    df = pd.DataFrame([{"lat": t["fault_lat"], "lon": t["fault_lon"]} for t in mappable])
    st.map(df, size=50)
else:
    st.caption("No mappable (span/DT-level) incidents right now.")

# ---------------------------------------------------------------------
# Simulator panel — clearly separated, for demo/review purposes
# ---------------------------------------------------------------------
st.divider()
with st.expander("🧪 Simulator — inject faults for demo (satisfies G5)", expanded=not open_tickets):
    st.caption(
        "This drives the same fault-injection/telemetry logic as the CLI simulator, "
        "over HTTP. Faults take ~30s (debounce window) to become tickets."
    )
    sim_cols = st.columns(4)

    if sim_cols[0].button("Inject span fault"):
        result = api_post("/simulate/fault/span")
        st.json(result)

    dt_id_input = sim_cols[1].text_input("DT id", value="D-010101", label_visibility="collapsed", placeholder="DT id")
    if sim_cols[1].button("Inject DT fault"):
        result = api_post(f"/simulate/fault/dt/{dt_id_input}")
        st.json(result)

    feeder_id_input = sim_cols[2].text_input("Feeder id", value="F-01-01", label_visibility="collapsed", placeholder="Feeder id")
    if sim_cols[2].button("Inject feeder fault"):
        result = api_post(f"/simulate/fault/feeder/{feeder_id_input}")
        st.json(result)

    pole_id_input = sim_cols[3].text_input("Pole id to restore", label_visibility="collapsed", placeholder="Pole id")
    if sim_cols[3].button("Restore pole"):
        result = api_post(f"/simulate/restore/{pole_id_input}")
        st.json(result)

# ---------------------------------------------------------------------
# Closed tickets (collapsed, out of the way)
# ---------------------------------------------------------------------
closed_tickets = [t for t in tickets if t["status"] == "closed"]
with st.expander(f"Closed tickets ({len(closed_tickets)})"):
    if closed_tickets:
        st.dataframe(pd.DataFrame(closed_tickets), use_container_width=True)
    else:
        st.caption("None yet.")

if auto_refresh:
    time.sleep(10)
    st.rerun()