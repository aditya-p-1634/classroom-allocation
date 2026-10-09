"""Tests for Standardized Allocation Metrics Engine.

Verifies hand-calculated walking times, room suitability, utilization, and comparative reporting.
"""

import pytest
from backend.app.schemas.models import DatasetSnapshot, Session, Room, DisruptionEvent
from backend.app.schemas.validation import AllocationCandidate
from backend.app.services.data_loader import DataLoaderService
from backend.app.core.metrics import MetricsCalculator


@pytest.fixture(scope="module")
def snapshot() -> DatasetSnapshot:
    return DataLoaderService().load_snapshot()


def test_walking_time_calculation_against_hand_calculation(snapshot: DatasetSnapshot):
    """Verifies that cohort walking time matches an exact manual calculation."""
    calc = MetricsCalculator(snapshot)

    # Let's inspect travel time between known rooms:
    # M601 to M602: 3.0 min
    # M601 to M601: 0.0 min
    # Construct a minimal synthetic scenario with 3 consecutive sessions for a single cohort
    s1 = Session(
        session_id="S_TEST_1",
        academic_cycle="odd",
        semester="1",
        program="CS",
        cohort_id="cohort_test_1",
        course="Algorithms",
        session_type="theory",
        day="Monday",
        start_period=1,
        end_period=2,
        assigned_room_id="M601",
        required_room_type="classroom",
        source_file="test.pdf",
        source_page="1",
        validation_status="test",
        notes="test",
    )
    s2 = Session(
        session_id="S_TEST_2",
        academic_cycle="odd",
        semester="1",
        program="CS",
        cohort_id="cohort_test_1",
        course="Databases",
        session_type="theory",
        day="Monday",
        start_period=3,
        end_period=3,
        assigned_room_id="M601",  # Same room -> 0.0 min
        required_room_type="classroom",
        source_file="test.pdf",
        source_page="1",
        validation_status="test",
        notes="test",
    )
    s3 = Session(
        session_id="S_TEST_3",
        academic_cycle="odd",
        semester="1",
        program="CS",
        cohort_id="cohort_test_1",
        course="Networks",
        session_type="theory",
        day="Monday",
        start_period=4,
        end_period=5,
        assigned_room_id="M602",  # Different room -> 3.0 min
        required_room_type="classroom",
        source_file="test.pdf",
        source_page="1",
        validation_status="test",
        notes="test",
    )

    candidate = AllocationCandidate(
        academic_cycle="odd",
        assignments={
            "S_TEST_1": "M601",
            "S_TEST_2": "M601",
            "S_TEST_3": "M602",
        },
    )

    transitions = calc.calculate_cohort_transitions(
        candidate=candidate,
        sessions_to_evaluate=[s1, s2, s3],
    )

    assert len(transitions) == 2
    # Transition 1: S1 -> S2 (M601 -> M601)
    assert transitions[0].from_session_id == "S_TEST_1"
    assert transitions[0].to_session_id == "S_TEST_2"
    assert transitions[0].walking_time_minutes == 0.0
    assert transitions[0].is_same_room is True

    # Transition 2: S2 -> S3 (M601 -> M602)
    assert transitions[1].from_session_id == "S_TEST_2"
    assert transitions[1].to_session_id == "S_TEST_3"
    assert transitions[1].walking_time_minutes == 3.0
    assert transitions[1].is_same_room is False

    # Total walking time = 0.0 + 3.0 = 3.0 min
    total_walk = sum(t.walking_time_minutes for t in transitions)
    assert total_walk == 3.0


def test_specialized_room_misuse_calculation(snapshot: DatasetSnapshot):
    """Verifies counting of classroom sessions placed into specialized laboratory rooms."""
    calc = MetricsCalculator(snapshot)

    # Room A105 is a classroom (permitted_uses: ['classroom', 'lecture'])
    # Room M601 is a laboratory (permitted_uses: ['laboratory'])
    s_regular = Session(
        session_id="S_REG_1",
        academic_cycle="even",
        semester="2",
        program="CS",
        cohort_id="cohort_1",
        course="History",
        session_type="theory",
        day="Tuesday",
        start_period=1,
        end_period=1,
        assigned_room_id="M601",  # Laboratory -> misuse!
        required_room_type="classroom",
        source_file="test.pdf",
        source_page="1",
        validation_status="test",
        notes="test",
    )

    candidate = AllocationCandidate(
        academic_cycle="even",
        assignments={"S_REG_1": "M601"},
    )

    metrics = calc.calculate_metrics(
        candidate=candidate,
        allocator_name="TestAllocator",
        sessions_to_evaluate=[s_regular],
    )

    assert metrics.total_assigned_sessions == 1
    assert metrics.specialized_room_misuse_count == 1
    assert metrics.room_suitability_percentage == 0.0


def test_metric_comparison_generation(snapshot: DatasetSnapshot):
    """Verifies side-by-side comparison between baseline and optimizer metric models."""
    calc = MetricsCalculator(snapshot)

    cand_base = AllocationCandidate(academic_cycle="odd", assignments={})
    cand_opt = AllocationCandidate(academic_cycle="odd", assignments={})

    base_metrics = calc.calculate_metrics(candidate=cand_base, allocator_name="Base")
    opt_metrics = calc.calculate_metrics(candidate=cand_opt, allocator_name="Opt")

    # Manually tweak fields to test delta math
    base_metrics.total_walking_time_minutes = 1000.0
    opt_metrics.total_walking_time_minutes = 800.0
    base_metrics.same_room_continuity_count = 300
    opt_metrics.same_room_continuity_count = 350

    comparison = calc.compare_allocations(base_metrics, opt_metrics)

    assert comparison.baseline_walking_time == 1000.0
    assert comparison.optimized_walking_time == 800.0
    assert comparison.walking_time_reduction_minutes == 200.0
    assert comparison.walking_time_reduction_percentage == 20.0
    assert comparison.baseline_same_room_count == 300
    assert comparison.optimized_same_room_count == 350
