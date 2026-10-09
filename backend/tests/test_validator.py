"""Automated Tests for IndependentValidator.

Verifies:
1. Original timetable room-time and cohort-time consistency.
2. Detection of deliberately introduced room double-bookings.
3. Detection of deliberately introduced cohort collisions.
4. Room capability matching, secondary permitted uses (project_room).
5. Explicit handling of the 10 computing lab anomalies (flagged by default, configurable).
6. Honest reporting of missing capacity and unconfirmed availability in Factual Mode.
7. Evaluation under explicitly labeled Synthetic Capacity Profile test fixtures.
8. Status taxonomy (VALID_COMPLETE, VALID_PARTIAL, INVALID).
"""

import pytest
from backend.app.config import CapacityPolicyMode
from backend.app.services.data_loader import DataLoaderService
from backend.app.core.validator import (
    IndependentValidator,
    COMPUTING_LAB_ANOMALY_SESSION_IDS,
)
from backend.app.schemas.validation import (
    AllocationCandidate,
    AllocationStatus,
    ConstraintCategory,
    FindingStatus,
)


@pytest.fixture(scope="module")
def snapshot():
    """Provides a fresh DatasetSnapshot."""
    return DataLoaderService().load_snapshot()


def test_original_timetable_exclusivity(snapshot):
    """Verifies that the original timetable has zero room or cohort collisions."""
    validator = IndependentValidator(snapshot=snapshot, allow_computing_lab_exception=True)

    # Build candidate from source assignments
    candidate = AllocationCandidate(
        academic_cycle="all",
        assignments={s.session_id: s.assigned_room_id for s in snapshot.sessions},
    )

    summary = validator.validate_candidate(candidate)

    # Zero room-time exclusivity failures
    room_excl_fails = [
        f for f in summary.findings
        if f.constraint == ConstraintCategory.ROOM_TIME_EXCLUSIVITY and f.status == FindingStatus.FAIL
    ]
    assert len(room_excl_fails) == 0, f"Unexpected room double-bookings: {room_excl_fails}"

    # Zero cohort-time exclusivity failures
    cohort_excl_fails = [
        f for f in summary.findings
        if f.constraint == ConstraintCategory.COHORT_TIME_EXCLUSIVITY and f.status == FindingStatus.FAIL
    ]
    assert len(cohort_excl_fails) == 0, f"Unexpected cohort collisions: {cohort_excl_fails}"


def test_validator_catches_deliberate_room_double_booking(snapshot):
    """Criterion 7: Intentionally invalid candidate (room double-booking) is caught."""
    validator = IndependentValidator(snapshot=snapshot)

    # Create candidate with intentional collision: SSN00001 and SSN00003 forced into same room
    candidate = AllocationCandidate(
        academic_cycle="even",
        assignments={
            "SSN00001": "M201",  # Monday Period 1
            "SSN00002": "M201",  # Monday Period 2
            "SSN00003": "M201",  # Monday Period 3 (originally M502) -> let's make it Period 1 collision:
        },
    )
    # Force SSN00003 to clash with SSN00001 by pointing another Monday P1 session to M201
    # Find another session on Monday Period 1 in even cycle:
    mon_p1_sessions = [
        s for s in snapshot.sessions
        if s.academic_cycle == "even" and s.day == "Monday" and 1 in s.period_range
    ]
    assert len(mon_p1_sessions) >= 2
    s1, s2 = mon_p1_sessions[0], mon_p1_sessions[1]

    # Deliberately assign both to room M201
    collision_candidate = AllocationCandidate(
        academic_cycle="even",
        assignments={s1.session_id: "M201", s2.session_id: "M201"},
    )

    summary = validator.validate_candidate(collision_candidate, sessions_to_verify=[s1, s2])

    assert summary.is_valid is False
    assert summary.status == AllocationStatus.INVALID

    room_fails = [
        f for f in summary.findings
        if f.constraint == ConstraintCategory.ROOM_TIME_EXCLUSIVITY and f.status == FindingStatus.FAIL
    ]
    assert len(room_fails) > 0
    assert "M201" == room_fails[0].room_id
    assert s1.session_id in room_fails[0].message
    assert s2.session_id in room_fails[0].message


def test_validator_catches_deliberate_cohort_collision(snapshot):
    """Criterion 7: Intentionally invalid candidate (cohort conflict) is caught."""
    validator = IndependentValidator(snapshot=snapshot)

    # Find two sessions sharing the same cohort
    cohorts = {}
    s_pair = None
    for s in snapshot.sessions:
        if s.cohort_id in cohorts:
            s_pair = (cohorts[s.cohort_id], s)
            break
        cohorts[s.cohort_id] = s

    assert s_pair is not None
    s1, s2 = s_pair

    # Force them to overlap by mocking candidate where s2 is moved to overlap s1's periods
    # We test cohort check by evaluating sessions with identical periods
    # Create two artificial sessions for same cohort at same time
    from backend.app.schemas.models import Session
    mock_s1 = Session(
        session_id="MOCK_01",
        academic_cycle="even",
        semester="2",
        program="CS",
        cohort_id="COHORT_TEST",
        course="Course A",
        session_type="class",
        day="Monday",
        start_period=1,
        end_period=1,
        required_room_type="classroom",
        assigned_room_id="A105",
        source_file="test.pdf",
        source_page="1",
        validation_status="test",
        notes="",
    )
    mock_s2 = Session(
        session_id="MOCK_02",
        academic_cycle="even",
        semester="2",
        program="CS",
        cohort_id="COHORT_TEST",  # Same cohort
        course="Course B",
        session_type="class",
        day="Monday",
        start_period=1,
        end_period=1,  # Same period!
        required_room_type="classroom",
        assigned_room_id="A106",  # Different room!
        source_file="test.pdf",
        source_page="1",
        validation_status="test",
        notes="",
    )

    candidate = AllocationCandidate(
        assignments={"MOCK_01": "A105", "MOCK_02": "A106"}
    )

    summary = validator.validate_candidate(candidate, sessions_to_verify=[mock_s1, mock_s2])
    assert summary.is_valid is False
    assert summary.status == AllocationStatus.INVALID

    cohort_fails = [
        f for f in summary.findings
        if f.constraint == ConstraintCategory.COHORT_TIME_EXCLUSIVITY and f.status == FindingStatus.FAIL
    ]
    assert len(cohort_fails) > 0
    assert "COHORT_TEST" in cohort_fails[0].message


def test_room_capability_matching_and_additional_uses(snapshot):
    """Criterion 4: Room type matching and additional_uses parsing (project_room)."""
    validator = IndependentValidator(snapshot=snapshot)

    # 1. Project room sessions assigned to classroom with additional_uses='project_room'
    proj_sessions = [s for s in snapshot.sessions if s.required_room_type == "project_room"]
    assert len(proj_sessions) == 110

    proj_candidate = AllocationCandidate(
        assignments={s.session_id: s.assigned_room_id for s in proj_sessions}
    )
    summary = validator.validate_candidate(proj_candidate, sessions_to_verify=proj_sessions)

    # Permitted uses check must pass for all 110
    cap_passes = [
        f for f in summary.findings
        if f.constraint == ConstraintCategory.ROOM_CAPABILITY and f.status == FindingStatus.PASS
    ]
    assert len(cap_passes) == 110

    # 2. Assigning laboratory session to standard classroom without lab use fails
    lab_session = next(s for s in snapshot.sessions if s.required_room_type == "laboratory")
    bad_candidate = AllocationCandidate(
        assignments={lab_session.session_id: "A106"}  # A106 is a classroom
    )
    bad_summary = validator.validate_candidate(bad_candidate, sessions_to_verify=[lab_session])
    assert bad_summary.is_valid is False
    cap_fails = [
        f for f in bad_summary.findings
        if f.constraint == ConstraintCategory.ROOM_CAPABILITY and f.status == FindingStatus.FAIL
    ]
    assert len(cap_fails) == 1
    assert "classroom" in cap_fails[0].message


def test_ten_computing_lab_anomalies_handling(snapshot):
    """Section 4: Explicit handling of the 10 computing lab anomaly sessions."""
    anomaly_sessions = [
        s for s in snapshot.sessions
        if s.session_id in COMPUTING_LAB_ANOMALY_SESSION_IDS
    ]
    assert len(anomaly_sessions) == 10

    candidate = AllocationCandidate(
        assignments={s.session_id: s.assigned_room_id for s in anomaly_sessions}
    )

    # 1. Default (exception disabled): MUST be flagged as 10 room capability violations
    strict_validator = IndependentValidator(snapshot=snapshot, allow_computing_lab_exception=False)
    strict_summary = strict_validator.validate_candidate(candidate, sessions_to_verify=anomaly_sessions)

    assert strict_summary.is_valid is False
    assert strict_summary.fail_count == 10
    assert len(strict_summary.error_findings) == 10

    for finding in strict_summary.error_findings:
        assert finding.constraint == ConstraintCategory.ROOM_CAPABILITY
        assert finding.evidence.get("is_known_anomaly") is True

    # 2. Configurable narrow exception enabled: Passes with WARNING findings explaining exception
    permissive_validator = IndependentValidator(snapshot=snapshot, allow_computing_lab_exception=True)
    permissive_summary = permissive_validator.validate_candidate(candidate, sessions_to_verify=anomaly_sessions)

    assert permissive_summary.is_valid is True
    assert permissive_summary.fail_count == 0
    warning_passes = [
        f for f in permissive_summary.findings
        if f.constraint == ConstraintCategory.ROOM_CAPABILITY and f.status == FindingStatus.PASS
    ]
    assert len(warning_passes) == 10


def test_factual_capacity_mode_preserves_insufficient_evidence(snapshot):
    """Section 3.E: In Factual Mode, missing capacities are reported as INSUFFICIENT_EVIDENCE."""
    validator = IndependentValidator(snapshot=snapshot, capacity_mode=CapacityPolicyMode.FACTUAL)

    sample_sessions = snapshot.sessions[:10]
    candidate = AllocationCandidate(
        assignments={s.session_id: s.assigned_room_id for s in sample_sessions}
    )

    summary = validator.validate_candidate(candidate, sessions_to_verify=sample_sessions)

    # Capacity must NOT be marked as PASS when missing
    cap_unknowns = [
        f for f in summary.findings
        if f.constraint == ConstraintCategory.CAPACITY and f.status == FindingStatus.INSUFFICIENT_EVIDENCE
    ]
    assert len(cap_unknowns) == 10
    assert len(summary.evidence_limitations) > 0


def test_synthetic_capacity_evaluation_profile(snapshot):
    """Section 3.E: Synthetic Capacity Profile correctly evaluates test fixtures."""
    # Synthetic test fixture: 10 sessions with 50 students each
    sample_sessions = snapshot.sessions[:2]
    s1, s2 = sample_sessions[0], sample_sessions[1]

    synthetic_demands = {s1.session_id: 40, s2.session_id: 90}
    synthetic_caps = {"A105": 60, "A106": 60}

    validator = IndependentValidator(
        snapshot=snapshot,
        capacity_mode=CapacityPolicyMode.SYNTHETIC_EVALUATION,
        synthetic_room_capacities=synthetic_caps,
        synthetic_session_demands=synthetic_demands,
    )

    candidate = AllocationCandidate(
        assignments={s1.session_id: "A105", s2.session_id: "A106"}
    )

    summary = validator.validate_candidate(candidate, sessions_to_verify=[s1, s2])

    # s1 fits: 40 <= 60 (PASS)
    pass_cap = [
        f for f in summary.findings
        if f.constraint == ConstraintCategory.CAPACITY and f.status == FindingStatus.PASS
    ]
    assert len(pass_cap) == 1
    assert pass_cap[0].session_id == s1.session_id

    # s2 overflows: 90 > 60 (FAIL)
    fail_cap = [
        f for f in summary.findings
        if f.constraint == ConstraintCategory.CAPACITY and f.status == FindingStatus.FAIL
    ]
    assert len(fail_cap) == 1
    assert fail_cap[0].session_id == s2.session_id
    assert summary.is_valid is False
