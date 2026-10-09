"""Automated Tests for BaselineGreedyAllocator and AllocationService.

Verifies:
1. Determinism: identical input data and parameters produce identical room assignments.
2. Independent validation: baseline allocator output passes independent validator checks.
3. Odd and even cycle isolation: cycles are allocated independently without cross-cycle interference.
4. Working snapshot management: released sessions are reallocated without stale occupancy blocking.
5. Explicit unallocated reasons when rooms conflict or are scarce.
6. End-to-end orchestration via AllocationService.
"""

import pytest
from backend.app.config import CapacityPolicyMode
from backend.app.services.data_loader import DataLoaderService
from backend.app.core.baseline_allocator import BaselineGreedyAllocator
from backend.app.core.validator import IndependentValidator
from backend.app.services.allocation_service import AllocationService
from backend.app.schemas.validation import AllocationStatus


@pytest.fixture(scope="module")
def snapshot():
    """Provides a fresh DatasetSnapshot."""
    return DataLoaderService().load_snapshot()


@pytest.fixture(scope="module")
def allocation_service(snapshot):
    """Provides an initialized AllocationService."""
    return AllocationService(snapshot=snapshot)


def test_baseline_allocator_determinism(snapshot):
    """Section 5: Baseline allocator produces 100% deterministic output for identical input."""
    allocator_1 = BaselineGreedyAllocator(snapshot=snapshot, allow_computing_lab_exception=True)
    allocator_2 = BaselineGreedyAllocator(snapshot=snapshot, allow_computing_lab_exception=True)

    # Run twice on even cycle
    cand_1 = allocator_1.allocate(academic_cycle="even")
    cand_2 = allocator_2.allocate(academic_cycle="even")

    assert cand_1.assignments == cand_2.assignments
    assert cand_1.unassigned_sessions == cand_2.unassigned_sessions
    assert len(cand_1.assignments) > 0


def test_baseline_allocator_independent_validation_even_cycle(snapshot):
    """Section 6: Output of baseline allocator passes independent validation."""
    allocator = BaselineGreedyAllocator(snapshot=snapshot, allow_computing_lab_exception=True)
    candidate = allocator.allocate(academic_cycle="even")

    validator = IndependentValidator(snapshot=snapshot, allow_computing_lab_exception=True)
    summary = validator.validate_candidate(candidate)

    # Zero double-bookings and zero cohort collisions
    assert summary.is_valid is True
    assert summary.fail_count == 0


def test_baseline_allocator_independent_validation_odd_cycle(snapshot):
    """Section 6: Odd cycle allocated independently and passes independent validation."""
    allocator = BaselineGreedyAllocator(snapshot=snapshot, allow_computing_lab_exception=True)
    candidate = allocator.allocate(academic_cycle="odd")

    validator = IndependentValidator(snapshot=snapshot, allow_computing_lab_exception=True)
    summary = validator.validate_candidate(candidate)

    assert summary.is_valid is True
    assert summary.fail_count == 0


def test_reallocation_without_stale_source_occupancy_blocking(allocation_service):
    """Section 5: Reallocating a session allows it to use its room or any non-conflicting room."""
    # Select 5 sessions on Monday in even cycle
    monday_even_sessions = [
        s.session_id for s in allocation_service.snapshot.sessions
        if s.academic_cycle == "even" and s.day == "Monday"
    ][:5]

    result = allocation_service.reallocate_sessions(
        session_ids_to_reallocate=monday_even_sessions,
        academic_cycle="even",
        allow_computing_lab_exception=True,
    )

    # All 5 reallocated sessions must receive valid room assignments
    for s_id in monday_even_sessions:
        assert s_id in result.candidate.assignments
        assert result.candidate.assignments[s_id] is not None

    # Entire schedule must remain valid
    assert result.validation.is_valid is True
    assert result.validation.fail_count == 0


def test_unallocated_reason_returned_when_incompatible(snapshot):
    """Section 5: Explicit unallocated reason returned when session requirements cannot be met."""
    from backend.app.schemas.models import Session
    unallocatable_session = Session(
        session_id="SSN_IMPOSSIBLE",
        academic_cycle="even",
        semester="2",
        program="CS",
        cohort_id="COHORT_IMP",
        course="Impossible Course",
        session_type="class",
        day="Monday",
        start_period=1,
        end_period=2,
        required_room_type="NON_EXISTENT_ROOM_TYPE_XYZ",  # No rooms of this type
        assigned_room_id="A105",
        source_file="test.pdf",
        source_page="1",
        validation_status="test",
        notes="",
    )

    allocator = BaselineGreedyAllocator(snapshot=snapshot)
    candidate = allocator.allocate(
        academic_cycle="even",
        sessions_to_allocate=[unallocatable_session],
    )

    assert "SSN_IMPOSSIBLE" in candidate.unassigned_sessions
    reason = candidate.unassigned_sessions["SSN_IMPOSSIBLE"]
    assert "No compatible rooms exist" in reason


def test_allocation_service_source_timetable_evaluation(allocation_service):
    """Section 6 & 7: End-to-end evaluation of source timetable via AllocationService."""
    # Strict mode (exception disabled)
    strict_res = allocation_service.validate_source_timetable(
        academic_cycle="even",
        allow_computing_lab_exception=False,
    )
    # 8 of the 10 anomalies are in even cycle (capstone projects in M901, M902, A901, J901)
    assert strict_res.validation.is_valid is False
    assert strict_res.validation.fail_count == 8

    # Permissive mode (narrow computing lab exception enabled)
    permissive_res = allocation_service.validate_source_timetable(
        academic_cycle="even",
        allow_computing_lab_exception=True,
    )
    assert permissive_res.validation.is_valid is True
    assert permissive_res.validation.fail_count == 0
    assert permissive_res.validation.status == AllocationStatus.VALID_COMPLETE
    assert permissive_res.allocator_name == "SourceTimetableBenchmark"


def test_allocation_service_baseline_run(allocation_service):
    """Section 6: Full baseline allocation run via AllocationService."""
    res = allocation_service.run_baseline_allocation(
        academic_cycle="even",
        allow_computing_lab_exception=True,
    )

    assert res.allocator_name == "BaselineGreedyAllocator"
    assert res.execution_time_ms > 0
    assert res.validation.is_valid is True
    assert res.candidate.metadata["assigned_count"] > 0
