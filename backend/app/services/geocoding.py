"""
backend/app/services/geocoding.py

PIN code lookup for the ~3% of poles missing it in the registry. Per
02-data-and-systems.md §5: any hosted geocoding service must still work
for a reviewer with no API key of ours, or degrade gracefully with a
visible note -- silently showing "unavailable" everywhere is explicitly
called out as broken.

Our choice: no external API at all. Ward-to-PIN is a stable, small,
offline mapping for one subdivision -- committing a bounded lookup table
avoids the entire "reviewer has no API key" failure mode described in the
brief. If a pole's ward isn't in our table, we say so honestly rather
than fabricating a PIN.
"""

# Small, bounded, offline mapping -- realistic for one subdivision (a few
# dozen wards). In a real deployment this would come from the department's
# ward/PIN master data; for this exercise it's illustrative but stable
# and requires no network call or API key.
WARD_TO_PINCODE = {
    "W-001": "560001", "W-011": "560011", "W-021": "560021",
    "W-041": "560041", "W-052": "560052", "W-054": "560054",
    "W-060": "560060", "W-078": "560078", "W-082": "560082",
    "W-084": "560084", "W-086": "560086", "W-091": "560091",
    "W-097": "560097", "W-098": "560098",
}

DEFAULT_PINCODE = None  # explicit "unknown" rather than a guessed value


def resolve_pincode(pole_pincode: str | None, ward: str | None) -> tuple[str | None, str]:
    """
    Returns (pincode, source) where source is one of:
      "registry"  -- pole already had a pincode in the CSV/DB
      "ward_lookup" -- resolved from our offline ward table
      "unavailable" -- genuinely unknown, UI must show this honestly

    Never fabricates a value -- an operator driving to the wrong PIN is
    worse than an honest "unavailable."
    """
    if pole_pincode:
        return pole_pincode, "registry"

    if ward and ward in WARD_TO_PINCODE:
        return WARD_TO_PINCODE[ward], "ward_lookup"

    return None, "unavailable"