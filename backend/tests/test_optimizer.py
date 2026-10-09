"""Tests for Mathematical Optimization Engine (Phase P6).

Verifies CP-SAT solver correctness, constraint adherence, independent validation,
measurable objective improvement over baseline, and synthetic/factual segregation.
"""

import pytest
from backend.app.config import CapacityPolicyMode
from backend.app.schemas.models import DatasetSnapshot
from backend.app.schemas.validation import AllocationStatus, AllocationCandidate
from backend.app.services.data_loader import DataLoaderService
from backend.app.core.optimizer import CPSATRoomOptimizer
from backend.app.core.validator import IndependentValidator
from backend.app.services.allocation_service import AllocationService


@pytest.fixture(scope="module")
def snapshot() -> DatasetSnapshot:
    return DataLoaderService().load_snapshot()


def test_optimizer_candidate_independent_validation(snapshot: DatasetSnapshot):
    """Verifies that an optimizer candidate is independently validated and passes all hard constraints."""
    alloc_service = AllocationService(snapshot)
    
    # Run optimizer on even cycle (570 sessions)
    result = alloc_service.run_optimized_allocation(
        academic_cycle="even",
        time_limit_seconds=10.0,
    )

    assert result.allocator_name == "CPSATRoomOptimizer"
    assert result.validation.status == AllocationStatus.VALID_COMPLETE
    assert result.validation.is_valid is True
    assert result.validation.is_complete is True
    assert result.validation.fail_count == 0
    assert result.candidate.metadata["solver_status"] in ["OPTIMAL", "FEASIBLE"]


def test_optimizer_preserves_hard_constraints(snapshot: DatasetSnapshot):
    """Verifies that optimizer strictly enforces room-time and capability exclusivity."""
    alloc_service = AllocationService(snapshot)
    result = alloc_service.run_optimized_allocation(
        academic_cycle="even",
        time_limit_seconds=10.0,
    )

    candidate = result.candidate
    even_sessions = [s for s in snapshot.sessions if s.academic_cycle == "even"]

    # 1. Verify no room-time collisions
    occupancy = {}
    for s in even_sessions:
        room_id = candidate.assignments.get(s.session_id)
        assert room_id is not None
        for p in s.period_range:
            slot = (room_id, s.day, p)
            assert slot not in occupancy, f"Double booking detected in {slot}"
            occupancy[slot] = s.session_id

    # 2. Verify room capability
    for s in even_sessions:
        room_id = candidate.assignments[s.session_id]
        room = snapshot.room_index[room_id]
        assert s.required_room_type in room.permitted_uses


def test_deliberately_invalid_candidate_rejected_by_validator(snapshot: DatasetSnapshot):
    """Verifies that the independent validator rejects a corrupted allocation proposal."""
    validator = IndependentValidator(snapshot)

    # Deliberately assign two simultaneous sessions to the same room
    s1 = next(s for s in snapshot.sessions if s.academic_cycle == "even" and s.day == "Monday" and 1 in s.period_range)
    s2 = next(s for s in snapshot.sessions if s.academic_cycle == "even" and s.day == "Monday" and 1 in s.period_range and s.session_id != s1.session_id)

    corrupted_candidate = AllocationCandidate(
        academic_cycle="even",
        assignments={
            s1.session_id: "A105",
            s2.session_id: "A105",  # Same room at the same time!
        },
    )

    val_summary = validator.validate_candidate(corrupted_candidate)
    assert val_summary.is_valid is False
    assert val_summary.fail_count > 0
    assert any("double-booking" in f.message.lower() for f in val_summary.findings)


def test_optimizer_measurable_improvement_over_baseline(snapshot: DatasetSnapshot):
    """Verifies that CP-SAT optimizer achieves a genuine, measurable reduction in walking time vs baseline."""
    alloc_service = AllocationService(snapshot)

    comparison = alloc_service.compare_baseline_and_optimizer(
        academic_cycle="odd",
        time_limit_seconds=10.0,
    )

    # Baseline walking time should be >= optimized walking time
    assert comparison.optimized_walking_time < comparison.baseline_walking_time
    assert comparison.walking_time_reduction_minutes > 0.0
    assert comparison.walking_time_reduction_percentage > 0.0

    # Same room continuity should increase
    assert comparison.optimized_same_room_count >= comparison.baseline_same_room_count


def test_factual_vs_synthetic_modes_separation(snapshot: DatasetSnapshot):
    """Verifies that optimizer respects synthetic vs factual capacity mode boundaries."""
    optimizer_factual = CPSATRoomOptimizer(
        snapshot=snapshot,
        capacity_mode=CapacityPolicyMode.FACTUAL,
    )
    res_factual = optimizer_factual.solve_and_validate(academic_cycle="even", time_limit_seconds=5.0)

    # Factual mode must report insufficient evidence for capacity
    assert res_factual.validation.insufficient_evidence_count > 0
    assert any("missing source student counts" in lim for lim in res_factual.validation.evidence_limitations)

    # Synthetic profile with small capacities forcing constraints
    synthetic_caps = {r.room_id: 100 for r in snapshot.rooms}
    synthetic_demands = {s.session_id: 50 for s in snapshot.sessions}

    optimizer_synth = CPSATRoomOptimizer(
        snapshot=snapshot,
        capacity_mode=CapacityPolicyMode.SYNTHETIC_EVALUATION,
        synthetic_room_capacities=synthetic_caps,
        synthetic_session_demands=synthetic_demands,
    )
    res_synth = optimizer_synth.solve_and_validate(academic_cycle="even", time_limit_seconds=5.0)
    assert res_synth.capacity_mode == "synthetic_evaluation"
    assert res_synth.validation.is_valid is True
