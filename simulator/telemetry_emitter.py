"""
simulator/telemetry_emitter.py

Turns "these poles should go dark" (from inject_fault.py) into realistic,
MESSY telemetry sent to the backend's /telemetry endpoint -- encoding every
dirty-data rule from 01-problem-context.md and 02-data-and-systems.md:

  - firmware >= 1.3: sends power_lost via capacitor reserve, succeeds ~70%
    of the time. The other 30% is silence -- nothing is sent at all.
  - firmware 1.2.x (~8% of fleet): NEVER sends power_lost. Just stops
    heartbeating. The backend must infer power loss from missing heartbeats.
  - clock skew: device ts can be off by up to +/-90 seconds from real time.
  - out-of-order arrival: messages are shuffled before sending, so two poles
    that lost power at the same instant may arrive a minute apart, and the
    downstream one may arrive first.
  - duplicates: at-least-once delivery -- some messages are sent twice.
  - stale retries: an offline device retries buffered messages for up to
    6 hours -- occasionally emit a very old power_lost as a "late retry".
  - noise independent of any fault: a device can die with power still fine
    (dead sensor case), unrelated to any injected fault.

This module only builds the payloads and POSTs them -- it does not decide
which poles go dark (that's inject_fault.py's job) and it does not decide
what's a real fault vs noise (that's the backend's graph/noise_filter.py job,
tested against exactly this kind of input).
"""

import random
import time
import uuid
from datetime import datetime, timedelta, timezone

import requests

INGEST_URL = "http://localhost:8000/telemetry"  # adjust to your backend's actual route

FW_1_2_PROBABILITY = 0.08          # fraction of fleet on old firmware
DYING_BREATH_SUCCESS_RATE = 0.70   # power_lost successfully sent
DUPLICATE_RATE = 0.05              # chance any given message is sent twice
STALE_RETRY_RATE = 0.03            # chance a message is a "late retry" from hours ago
CLOCK_SKEW_SECONDS = 90


def device_id_for(pole):
    return pole.get("device_id") or f"UNKNOWN-{pole['pole_id']}"


def is_legacy_firmware(pole_id, seed_salt=""):
    """Deterministic per pole+context so a given pole consistently behaves
    the same way across repeated test runs, unless salt changes."""
    rnd = random.Random(pole_id + seed_salt)
    return rnd.random() < FW_1_2_PROBABILITY


def skewed_timestamp(base_time=None):
    base_time = base_time or datetime.now(timezone.utc)
    skew = random.uniform(-CLOCK_SKEW_SECONDS, CLOCK_SKEW_SECONDS)
    return (base_time + timedelta(seconds=skew)).isoformat()


def build_power_lost_payload(pole, seq, fw="1.4.2", ts=None):
    return {
        "device_id": device_id_for(pole),
        "pole_id": pole["pole_id"],
        "event": "power_lost",
        "energized": False,
        "ts": ts or skewed_timestamp(),
        "seq": seq,
        "battery_mv": random.randint(3100, 3600),
        "rssi": random.randint(-100, -60),
        "fw": fw,
    }


def build_heartbeat_payload(pole, seq, fw="1.4.2", energized=True):
    return {
        "device_id": device_id_for(pole),
        "pole_id": pole["pole_id"],
        "event": "heartbeat",
        "energized": energized,
        "ts": skewed_timestamp(),
        "seq": seq,
        "battery_mv": random.randint(3600, 4200),
        "rssi": random.randint(-95, -55),
        "fw": fw,
    }


def build_restoration_payloads(pole, seq_start):
    """boot -> power_restored, per the brief, ~20s apart."""
    boot_ts = datetime.now(timezone.utc)
    restored_ts = boot_ts + timedelta(seconds=random.uniform(5, 20))
    return [
        {
            "device_id": device_id_for(pole), "pole_id": pole["pole_id"],
            "event": "boot", "energized": True,
            "ts": boot_ts.isoformat(), "seq": 0,  # seq resets to 0 on boot
            "battery_mv": random.randint(3800, 4200), "rssi": random.randint(-90, -60),
            "fw": "1.4.2",
        },
        {
            "device_id": device_id_for(pole), "pole_id": pole["pole_id"],
            "event": "power_restored", "energized": True,
            "ts": restored_ts.isoformat(), "seq": 1,
            "battery_mv": random.randint(3800, 4200), "rssi": random.randint(-90, -60),
            "fw": "1.4.2",
        },
    ]


def emit_outage_telemetry(dark_poles_dicts, dry_run=True):
    """
    Given a list of pole dicts (with at least pole_id, device_id) that should
    go dark, produces the messy payload set: some succeed, some go silent,
    firmware-1.2 poles never send power_lost at all, duplicates and stale
    retries are sprinkled in, and the whole batch is shuffled before sending.

    dry_run=True just prints/returns the payload list instead of POSTing --
    use this to eyeball the output before your backend even exists.
    """
    payloads = []

    for pole in dark_poles_dicts:
        if not pole.get("device_id"):
            continue  # no device on this pole -- nothing to send, by definition

        seq = random.randint(1000, 99000)

        if is_legacy_firmware(pole["pole_id"]):
            # firmware 1.2.x: sends NOTHING on power loss. Just goes silent.
            # (backend must infer this from missing heartbeats)
            continue

        if random.random() < DYING_BREATH_SUCCESS_RATE:
            payload = build_power_lost_payload(pole, seq)
            payloads.append(payload)

            if random.random() < DUPLICATE_RATE:
                payloads.append(dict(payload))  # exact duplicate, at-least-once delivery

            if random.random() < STALE_RETRY_RATE:
                stale = build_power_lost_payload(
                    pole, seq - 1,
                    ts=(datetime.now(timezone.utc) - timedelta(hours=random.uniform(1, 6))).isoformat(),
                )
                payloads.append(stale)
        # else: the 30% case -- capacitor died before it could send. Silence.

    random.shuffle(payloads)  # out-of-order arrival

    if dry_run:
        return payloads

    for p in payloads:
        try:
            requests.post(INGEST_URL, json=p, timeout=2)
        except requests.RequestException as e:
            print(f"WARN: failed to send telemetry for {p['pole_id']}: {e}")
        time.sleep(random.uniform(0, 0.05))  # spread arrival slightly

    return payloads


def emit_dead_sensor_noise(pole, dry_run=True):
    """
    A device dies while power is fine -- unrelated to any real fault.
    This is the exact scenario the backend's noise_filter must NOT ticket:
    the pole itself goes silent/dark but everything downstream of it (if any)
    stays live, because the power line itself is fine.
    """
    payload = build_power_lost_payload(pole, seq=random.randint(1000, 9000))
    if dry_run:
        return [payload]
    requests.post(INGEST_URL, json=payload, timeout=2)
    return [payload]


if __name__ == "__main__":
    # quick smoke test using a couple of fabricated poles
    fake_dark_poles = [
        {"pole_id": "P-test1", "device_id": "DEV-1"},
        {"pole_id": "P-test2", "device_id": "DEV-2"},
        {"pole_id": "P-test3", "device_id": None},        # no device -- should be skipped
        {"pole_id": "P-test4", "device_id": "DEV-4"},
    ]
    payloads = emit_outage_telemetry(fake_dark_poles, dry_run=True)
    print(f"Generated {len(payloads)} telemetry messages for {len(fake_dark_poles)} dark poles:")
    for p in payloads:
        print(f"  {p['event']:15s} pole={p['pole_id']:10s} seq={p['seq']:6d} ts={p['ts']}")