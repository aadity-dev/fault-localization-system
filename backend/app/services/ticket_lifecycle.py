"""
backend/app/services/ticket_lifecycle.py

Ticket state machine logic, framework-free (no FastAPI/DB session
required to reason about transitions -- keeps this testable in isolation).

Lifecycle: detected -> acknowledged -> crew_assigned -> resolved ->
verified -> closed.

The one rule the brief is explicit and insistent about (00-candidate-brief.md,
"Ticket workflow" + 03-deliverables-and-submission.md's self-check list):

    "Restoration must be verified from telemetry, not from someone
    clicking a button... If a lineman marks it fixed and the poles are
    still dark, the system should not believe him."

So: a human can move a ticket to 'resolved' (crew claims the fix is
done). The system independently checks CURRENT pole state before
allowing 'resolved' -> 'verified'. If the poles are still dark,
verify_ticket() refuses and returns an explanatory error rather than
silently succeeding.
"""

VALID_TRANSITIONS = {
    "detected": {"acknowledged"},
    "acknowledged": {"crew_assigned"},
    "crew_assigned": {"resolved"},
    "resolved": {"verified"},   # only via verify_ticket(), never a raw status PATCH
    "verified": {"closed"},
    "closed": set(),
}


class InvalidTransition(Exception):
    pass


class VerificationFailed(Exception):
    """Raised when a resolve->verify transition is attempted but telemetry
    still shows the affected poles as dark."""
    def __init__(self, still_dark_poles):
        self.still_dark_poles = still_dark_poles
        super().__init__(
            f"Cannot verify: {len(still_dark_poles)} affected pole(s) still "
            f"report dark: {sorted(still_dark_poles)[:5]}"
            f"{'...' if len(still_dark_poles) > 5 else ''}"
        )


def can_transition(current_status, new_status):
    return new_status in VALID_TRANSITIONS.get(current_status, set())


def apply_manual_transition(ticket_status, new_status):
    """
    For any transition EXCEPT resolved->verified, which always requires
    telemetry confirmation via verify_ticket() below, never a raw status
    write. This function is what a PATCH /tickets/{id} endpoint calls for
    ordinary lifecycle moves (acknowledge, assign crew, mark resolved).
    """
    if new_status == "verified":
        raise InvalidTransition(
            "verified can only be reached via telemetry confirmation "
            "(see verify_ticket) -- not a direct status update."
        )
    if not can_transition(ticket_status, new_status):
        raise InvalidTransition(f"Cannot go from '{ticket_status}' to '{new_status}'")
    return new_status


def verify_ticket(ticket_status, affected_poles, current_pole_energized_state):
    """
    Attempts resolved -> verified. Checks CURRENT telemetry-derived
    energized state for every pole this ticket claims is affected.

    current_pole_energized_state: dict[pole_id] -> bool (True = live,
    False = dark), as maintained by the ingestion worker's PoleStateTracker.

    Raises VerificationFailed if any affected pole is still dark (or has
    no recent state at all, treated conservatively as "not yet confirmed
    live"). Returns "verified" only if every affected pole is confirmed
    live.
    """
    if ticket_status != "resolved":
        raise InvalidTransition(
            f"Cannot verify a ticket in status '{ticket_status}' -- must be 'resolved' first."
        )

    still_dark = [
        pole_id for pole_id in affected_poles
        if not current_pole_energized_state.get(pole_id, False)
    ]

    if still_dark:
        raise VerificationFailed(still_dark)

    return "verified"