"""
backend/tests/test_worker_state_tracking.py

Tests PoleStateTracker's dedup/staleness/debounce logic directly -- no
Redis needed, since apply() takes a plain dict payload. This is the part
of the ingestion pipeline responsible for handling duplicates, stale
retries, and turning raw telemetry into "this pole has been dark long
enough to act on."
"""

from datetime import datetime, timedelta, timezone

from app.ingestion.worker import PoleStateTracker


def _payload(device_id="DEV-1", pole_id="P1", event="power_lost", seq=1, ts=None):
    ts = ts or datetime.now(timezone.utc).isoformat()
    return {
        "device_id": device_id, "pole_id": pole_id, "event": event,
        "energized": event != "power_lost", "ts": ts, "seq": seq,
        "battery_mv": 3400, "rssi": -80, "fw": "1.4.2",
    }


def test_duplicate_seq_is_ignored():
    tracker = PoleStateTracker()
    assert tracker.apply(_payload(seq=5)) is True
    # same seq again -- exact duplicate, at-least-once delivery
    assert tracker.apply(_payload(seq=5)) is False


def test_out_of_order_lower_seq_is_ignored():
    tracker = PoleStateTracker()
    assert tracker.apply(_payload(seq=10)) is True
    # a message with a LOWER seq arriving late -- stale/out of order for this device
    assert tracker.apply(_payload(seq=3)) is False


def test_stale_retry_beyond_6_hours_is_ignored():
    tracker = PoleStateTracker()
    old_ts = (datetime.now(timezone.utc) - timedelta(hours=8)).isoformat()
    assert tracker.apply(_payload(seq=1, ts=old_ts)) is False


def test_power_lost_then_restored_clears_pending_dark():
    tracker = PoleStateTracker()
    tracker.apply(_payload(event="power_lost", seq=1))
    assert "P1" in tracker.pending_dark
    tracker.apply(_payload(event="power_restored", seq=2))
    assert "P1" not in tracker.pending_dark
    assert tracker.energized["P1"] is True


def test_debounce_buffer_excludes_recent_dark_poles():
    tracker = PoleStateTracker()
    tracker.apply(_payload(pole_id="P1", event="power_lost", seq=1))
    # just went dark -- should NOT be in the debounced set yet (needs 30s)
    assert "P1" not in tracker.debounced_dark_poles()

    # manually backdate to simulate 30+ seconds having passed
    tracker.pending_dark["P1"] -= 31
    assert "P1" in tracker.debounced_dark_poles()