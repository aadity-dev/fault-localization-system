"""
backend/tests/test_ticket_lifecycle.py

Tests the ticket state machine, especially the rule directly named in
03-deliverables-and-submission.md's self-check list: "Marked a ticket
resolved while the poles were still dark. The system pushed back."
"""

import pytest

from app.services.ticket_lifecycle import (
    InvalidTransition,
    VerificationFailed,
    apply_manual_transition,
    verify_ticket,
)


def test_normal_lifecycle_progression():
    status = "detected"
    status = apply_manual_transition(status, "acknowledged")
    assert status == "acknowledged"
    status = apply_manual_transition(status, "crew_assigned")
    assert status == "crew_assigned"
    status = apply_manual_transition(status, "resolved")
    assert status == "resolved"


def test_cannot_skip_states():
    with pytest.raises(InvalidTransition):
        apply_manual_transition("detected", "crew_assigned")


def test_cannot_manually_set_verified():
    """verified must come from telemetry confirmation, never a raw PATCH."""
    with pytest.raises(InvalidTransition):
        apply_manual_transition("resolved", "verified")


def test_verify_fails_if_poles_still_dark():
    """
    The exact scenario from the brief's self-check list: a lineman marks
    a ticket resolved, but telemetry shows the affected poles are still
    dark. The system must refuse to verify.
    """
    affected_poles = ["P1", "P2", "P3"]
    pole_state = {"P1": True, "P2": False, "P3": True}  # P2 still dark

    with pytest.raises(VerificationFailed) as exc_info:
        verify_ticket("resolved", affected_poles, pole_state)

    assert "P2" in exc_info.value.still_dark_poles


def test_verify_succeeds_when_all_poles_confirmed_live():
    affected_poles = ["P1", "P2", "P3"]
    pole_state = {"P1": True, "P2": True, "P3": True}

    result = verify_ticket("resolved", affected_poles, pole_state)
    assert result == "verified"


def test_verify_fails_for_pole_with_no_recent_state():
    """
    A pole with no entry in current_pole_energized_state (never reported
    since the fault) is treated conservatively as NOT confirmed live --
    we don't verify based on absence of bad news.
    """
    affected_poles = ["P1", "P2"]
    pole_state = {"P1": True}  # P2 has no data at all

    with pytest.raises(VerificationFailed) as exc_info:
        verify_ticket("resolved", affected_poles, pole_state)

    assert "P2" in exc_info.value.still_dark_poles


def test_cannot_verify_a_ticket_that_isnt_resolved_yet():
    with pytest.raises(InvalidTransition):
        verify_ticket("crew_assigned", ["P1"], {"P1": True})


def test_closed_has_no_further_transitions():
    with pytest.raises(InvalidTransition):
        apply_manual_transition("closed", "detected")