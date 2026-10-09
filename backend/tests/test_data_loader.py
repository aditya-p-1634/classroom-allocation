"""Automated Tests for DataLoaderService.

Verifies:
1. Expected row counts matching the current source snapshot.
2. Accurate parsing into typed Pydantic models without silent row loss.
3. Preservation of source fields and explicit handling of missing values.
4. Foreign-key referential integrity across all datasets.
5. Detection and explicit rejection of malformed records.
"""

import pytest
from pathlib import Path
from backend.app.config import EXPECTED_ROW_COUNTS, DATA_DIR
from backend.app.services.data_loader import (
    DataLoaderService,
    _clean_str,
    _clean_int,
    _clean_float,
)
from backend.app.schemas.models import Room, Session, Facility


@pytest.fixture(scope="module")
def data_loader():
    """Provides an initialized DataLoaderService instance."""
    return DataLoaderService(data_dir=DATA_DIR)


@pytest.fixture(scope="module")
def snapshot(data_loader):
    """Provides a fully ingested DatasetSnapshot."""
    return data_loader.load_snapshot()


def test_row_counts_against_contract(snapshot):
    """Criterion 3: Expected row counts are checked against current source snapshot."""
    assert len(snapshot.rooms) == EXPECTED_ROW_COUNTS["rooms.csv"], "rooms.csv count mismatch"
    assert len(snapshot.facilities) == EXPECTED_ROW_COUNTS["facilities.csv"], "facilities.csv count mismatch"
    assert len(snapshot.sessions) == EXPECTED_ROW_COUNTS["sessions.csv"], "sessions.csv count mismatch"
    assert len(snapshot.availability) == EXPECTED_ROW_COUNTS["availability.csv"], "availability.csv count mismatch"
    assert len(snapshot.travel_times) == EXPECTED_ROW_COUNTS["travel_times.csv"], "travel_times.csv count mismatch"
    assert len(snapshot.events) == EXPECTED_ROW_COUNTS["events.csv"], "events.csv count mismatch"
    assert len(snapshot.complaints) == EXPECTED_ROW_COUNTS["complaints.csv"], "complaints.csv count mismatch"
    assert snapshot.report.is_success is True
    assert len(snapshot.report.errors) == 0
    assert len(snapshot.report.warnings) == 0


def test_source_fields_preservation_rooms(snapshot):
    """Verifies room fields, distinguishing known capacities from missing ones."""
    room_map = snapshot.room_index
    assert "A105" in room_map
    a105 = room_map["A105"]
    assert a105.room_type == "classroom"
    assert a105.additional_uses == "project_room"
    assert "project_room" in a105.permitted_uses
    assert a105.capacity is None  # Factual missing capacity preserved as None
    assert a105.building_block is None  # Preserved as None

    # Assembly hall with known inferred capacity
    assert "AA250" in room_map
    aa250 = room_map["AA250"]
    assert aa250.room_type == "assembly_hall"
    assert aa250.capacity == 250
    assert aa250.has_known_capacity is True
    assert aa250.capacity_source == "inferred_from_user_supplied_hall_ID"


def test_source_fields_preservation_sessions(snapshot):
    """Verifies session fields and period ranges."""
    sess_map = snapshot.session_index
    assert "SSN00001" in sess_map
    s1 = sess_map["SSN00001"]
    assert s1.academic_cycle == "even"
    assert s1.day == "Monday"
    assert s1.start_period == 1
    assert s1.end_period == 1
    assert s1.duration_periods == 1
    assert s1.period_range == [1]
    assert s1.student_count is None  # Preserved as None, not defaulted to 0
    assert s1.required_facilities is None


def test_foreign_key_referential_integrity(snapshot):
    """Verifies that all relational references resolve to valid entities."""
    room_ids = set(snapshot.room_index.keys())

    # Facilities -> Rooms
    for f in snapshot.facilities:
        assert f.room_id in room_ids, f"Facility room_id '{f.room_id}' not found in rooms"

    # Sessions -> Rooms
    for s in snapshot.sessions:
        assert s.assigned_room_id in room_ids, f"Session assigned_room_id '{s.assigned_room_id}' not in rooms"

    # Availability -> Rooms
    for a in snapshot.availability:
        assert a.room_id in room_ids, f"Availability room_id '{a.room_id}' not found in rooms"

    # Travel Times -> Rooms
    for t in snapshot.travel_times:
        assert t.from_room_id in room_ids, f"Travel from_room_id '{t.from_room_id}' not in rooms"
        assert t.to_room_id in room_ids, f"Travel to_room_id '{t.to_room_id}' not in rooms"

    # Events -> Rooms & Sessions
    session_ids = set(snapshot.session_index.keys())
    for e in snapshot.events:
        assert e.room_id in room_ids, f"Event room_id '{e.room_id}' not found in rooms"
        assert e.related_session_id in session_ids, f"Event session '{e.related_session_id}' not in sessions"

    # Complaints -> Rooms
    for c in snapshot.complaints:
        if c.location_type in ["classroom", "laboratory", "assembly_hall"]:
            assert c.location_id in room_ids, f"Complaint location_id '{c.location_id}' not in rooms"


def test_availability_and_session_synchronization(snapshot):
    """Verifies that occupied availability slots match session occurrences."""
    occupied_slots = [a for a in snapshot.availability if a.status == "occupied"]
    assert len(occupied_slots) == 1490

    session_slots = sum(s.duration_periods for s in snapshot.sessions)
    assert session_slots == 1490

    # Ensure every occupied slot references a valid session
    for a in occupied_slots:
        assert a.session_id is not None
        assert a.session_id in snapshot.session_index


def test_malformed_input_rejection():
    """Criterion 6: Malformed records are detected and rejected explicitly."""
    # Test integer parsing helpers
    with pytest.raises(ValueError):
        _clean_int("not_an_int")

    with pytest.raises(ValueError):
        _clean_float("not_a_float")

    assert _clean_int("") is None
    assert _clean_int(None) is None
    assert _clean_str("   ") is None
    assert _clean_str(" valid ") == "valid"

    # Test Pydantic validation on malformed period range
    with pytest.raises(Exception):
        Session(
            session_id="BAD_PERIOD",
            academic_cycle="even",
            semester="2",
            program="CS",
            cohort_id="COHORT1",
            course="Test",
            session_type="class",
            day="Monday",
            start_period=0,  # Invalid period < 1
            end_period=9,    # Invalid period > 8
            required_room_type="classroom",
            assigned_room_id="A105",
            source_file="test.pdf",
            source_page="1",
            validation_status="test",
            notes="",
        )
