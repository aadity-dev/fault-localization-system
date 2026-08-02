"""
backend/tests/conftest.py

Small, hand-built synthetic topology fixtures -- deliberately NOT the full
random 725-pole grid. Per 03-deliverables-and-submission.md's guidance
("if you test one thing, test that a known fault in a known topology
produces the expected span"), these fixtures are simple enough to reason
about by eye:

    DT-KNOWN (known topology, 40% case):
        D-KNOWN --> P1 --> P2 --> P3
                           |
                           +--> P4   (spur off P2)

    DT-UNKNOWN (missing topology, 60% case):
        D-UNKNOWN at (12.9700, 77.5900)
        Q1, Q2, Q3 -- no parent_pole_id, positioned so Q1 is closest to
        the DT and Q3 is furthest, in a roughly straight line, so the MST
        has an obvious, checkable correct answer.
"""

import pytest


@pytest.fixture
def known_topology_poles():
    """40% case: full parent_pole_id chain, with one branch."""
    return [
        {"pole_id": "P1", "lat": 12.9700, "lon": 77.5900, "feeder_id": "F-01",
         "dt_id": "D-KNOWN", "parent_pole_id": None, "device_id": "DEV-P1"},
        {"pole_id": "P2", "lat": 12.9705, "lon": 77.5905, "feeder_id": "F-01",
         "dt_id": "D-KNOWN", "parent_pole_id": "P1", "device_id": "DEV-P2"},
        {"pole_id": "P3", "lat": 12.9710, "lon": 77.5910, "feeder_id": "F-01",
         "dt_id": "D-KNOWN", "parent_pole_id": "P2", "device_id": "DEV-P3"},
        {"pole_id": "P4", "lat": 12.9706, "lon": 77.5920, "feeder_id": "F-01",
         "dt_id": "D-KNOWN", "parent_pole_id": "P2", "device_id": "DEV-P4"},
    ]


@pytest.fixture
def known_dt_registry():
    return [
        {"dt_id": "D-KNOWN", "feeder_id": "F-01", "lat": 12.9699, "lon": 77.5899,
         "capacity_kva": "250", "households_served": "300"},
    ]


@pytest.fixture
def unknown_topology_poles():
    """60% case: no parent_pole_id, roughly in a line moving away from the DT."""
    return [
        {"pole_id": "Q1", "lat": 12.9702, "lon": 77.5902, "feeder_id": "F-02",
         "dt_id": "D-UNKNOWN", "parent_pole_id": None, "device_id": "DEV-Q1"},
        {"pole_id": "Q2", "lat": 12.9706, "lon": 77.5906, "feeder_id": "F-02",
         "dt_id": "D-UNKNOWN", "parent_pole_id": None, "device_id": "DEV-Q2"},
        {"pole_id": "Q3", "lat": 12.9710, "lon": 77.5910, "feeder_id": "F-02",
         "dt_id": "D-UNKNOWN", "parent_pole_id": None, "device_id": "DEV-Q3"},
    ]


@pytest.fixture
def unknown_dt_registry():
    return [
        {"dt_id": "D-UNKNOWN", "feeder_id": "F-02", "lat": 12.9700, "lon": 77.5900,
         "capacity_kva": "160", "households_served": "150"},
    ]
