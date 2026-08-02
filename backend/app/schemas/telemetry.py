"""
backend/app/schemas/telemetry.py

Pydantic model for the device telemetry payload, matching the JSON
contract in 02-data-and-systems.md §2 exactly. Used to validate incoming
POST /telemetry requests before they're pushed onto the queue.
"""

from typing import Literal, Optional

from pydantic import BaseModel


class TelemetryPayload(BaseModel):
    device_id: str
    pole_id: str
    event: Literal["heartbeat", "power_lost", "power_restored", "boot"]
    energized: bool
    ts: str            # device clock, ISO8601 -- do not trust for cross-device ordering (±90s skew)
    seq: int            # monotonic per device, resets to 0 on boot -- the reliable ordering tool
    battery_mv: Optional[int] = None
    rssi: Optional[int] = None
    fw: Optional[str] = None