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
        academic_cycle="even",
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
    res_factual = optimizer_factual.solve_and_validate(academic_cycle="even", time_limit_seconds=10.0)

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
    res_synth = optimizer_synth.solve_and_validate(academic_cycle="even", time_limit_seconds=10.0)
    assert res_synth.capacity_mode == "synthetic_evaluation"
    assert res_synth.validation.is_valid is True


def test_optimizer_prefers_3min_over_8min_transition(snapshot: DatasetSnapshot):
    """Hand-calculated objective unit test: distinguishes 3-min from 8-min transitions.

    Setup:
    - Session S1 is pre-reserved in room A105 on Monday Period 1 for cohort COHORT_HANDCALC.
    - Session S2 takes place on Monday Period 2 for the same cohort.
    - Candidate rooms for S2: A106 (same building prefix, T(A105, A106) = 3.0 min)
                             M201 (different building, T(A105, M201) = 8.0 min)
    - Room A105 is blocked at Period 2 (so same-room continuity is unavailable).

    Hand-calculated objective comparison:
    - If S2 -> A106: Walking time = 3.0 min. Savings vs 8.0 min max = (8.0 - 3.0) * 10 = +50 points.
    - If S2 -> M201: Walking time = 8.0 min. Savings vs 8.0 min max = (8.0 - 8.0) * 10 = 0 points.
    - Suitability and feasibility factors are identical (both are ordinary classrooms).
    - Objective strictly prefers A106 over M201 by 50 points.
    """
    r_a = snapshot.room_index["A105"]
    r_b = snapshot.room_index["A106"]
    r_c = snapshot.room_index["M201"]

    s1 = snapshot.sessions[0].model_copy(update={
        "session_id": "HANDCALC_S1",
        "cohort_id": "COHORT_HC",
        "day": "Monday",
        "start_period": 1,
        "end_period": 1,
        "academic_cycle": "odd",
        "required_room_type": "classroom",
    })
    s2 = snapshot.sessions[1].model_copy(update={
        "session_id": "HANDCALC_S2",
        "cohort_id": "COHORT_HC",
        "day": "Monday",
        "start_period": 2,
        "end_period": 2,
        "academic_cycle": "odd",
        "required_room_type": "classroom",
    })

    fixture_snapshot = DatasetSnapshot(
        rooms=[r_a, r_b, r_c],
        sessions=[s1, s2],
        facilities=[],
        availability=[],
        travel_times=snapshot.travel_times,
        events=[],
        complaints=[],
        report=snapshot.report,
    )

    optimizer = CPSATRoomOptimizer(fixture_snapshot)
    candidate = optimizer.solve(
        sessions_to_allocate=[s2],
        pre_reserved_assignments={"HANDCALC_S1": "A105"},
        blocked_room_periods={("A105", "Monday", 2)},
        time_limit_seconds=5.0,
    )

    assert candidate.metadata["solver_status"] in ["OPTIMAL", "FEASIBLE"]
    assert candidate.assignments.get("HANDCALC_S2") == "A106"
    assert candidate.assignments.get("HANDCALC_S2") != "M201"


def test_optimizer_prefers_0min_over_3min_transition(snapshot: DatasetSnapshot):
    """Hand-calculated objective unit test: distinguishes 0-min (same room) from 3-min transitions.

    Setup:
    - Session S1 is pre-reserved in room A105 on Monday Period 1 for cohort COHORT_HANDCALC.
    - Session S2 takes place on Monday Period 2 for the same cohort.
    - Candidate rooms for S2: A105 (same room, T(A105, A105) = 0.0 min)
                             A106 (same building, T(A105, A106) = 3.0 min)
                             M201 (cross building, T(A105, M201) = 8.0 min)

    Hand-calculated objective comparison:
    - If S2 -> A105: Walking time = 0.0 min. Savings vs 8.0 min max = (8.0 - 0.0) * 10 = +80 points.
    - If S2 -> A106: Walking time = 3.0 min. Savings vs 8.0 min max = (8.0 - 3.0) * 10 = +50 points.
    - If S2 -> M201: Walking time = 8.0 min. Savings vs 8.0 min max = (8.0 - 8.0) * 10 = 0 points.
    - Objective strictly prefers A105 over A106 (+30 points) and over M201 (+80 points).
    """
    r_a = snapshot.room_index["A105"]
    r_b = snapshot.room_index["A106"]
    r_c = snapshot.room_index["M201"]

    s1 = snapshot.sessions[0].model_copy(update={
        "session_id": "HANDCALC_S1",
        "cohort_id": "COHORT_HC",
        "day": "Monday",
        "start_period": 1,
        "end_period": 1,
        "academic_cycle": "odd",
        "required_room_type": "classroom",
    })
    s2 = snapshot.sessions[1].model_copy(update={
        "session_id": "HANDCALC_S2",
        "cohort_id": "COHORT_HC",
        "day": "Monday",
        "start_period": 2,
        "end_period": 2,
        "academic_cycle": "odd",
        "required_room_type": "classroom",
    })

    fixture_snapshot = DatasetSnapshot(
        rooms=[r_a, r_b, r_c],
        sessions=[s1, s2],
        facilities=[],
        availability=[],
        travel_times=snapshot.travel_times,
        events=[],
        complaints=[],
        report=snapshot.report,
    )

    optimizer = CPSATRoomOptimizer(fixture_snapshot)
    candidate = optimizer.solve(
        sessions_to_allocate=[s2],
        pre_reserved_assignments={"HANDCALC_S1": "A105"},
        time_limit_seconds=5.0,
    )

    assert candidate.metadata["solver_status"] in ["OPTIMAL", "FEASIBLE"]
    assert candidate.assignments.get("HANDCALC_S2") == "A105"


def test_travel_matrix_exact_agreement_with_cluster_formulation(snapshot: DatasetSnapshot):
    """Verifies that all 3,655 room pairs in TravelMatrixService match the compact cluster model."""
    from backend.app.services.travel_matrix import TravelMatrixService
    optimizer = CPSATRoomOptimizer(snapshot)
    clusters = optimizer._get_travel_clusters()
    travel_svc = TravelMatrixService(snapshot.travel_times)

    mismatches = []
    for r1 in snapshot.rooms:
        for r2 in snapshot.rooms:
            if r1.room_id == r2.room_id:
                assert travel_svc.get_travel_time(r1.room_id, r2.room_id) == 0.0
            else:
                actual = travel_svc.get_travel_time(r1.room_id, r2.room_id)
                expected = 3.0 if clusters[r1.room_id] == clusters[r2.room_id] else 8.0
                if actual != expected:
                    mismatches.append((r1.room_id, r2.room_id, actual, expected))

    assert len(mismatches) == 0, f"Found {len(mismatches)} cluster-matrix discrepancies."


def test_baseline_protection_retains_baseline_when_solver_worse(snapshot: DatasetSnapshot):
    """Verifies that a solver candidate worse than baseline is never reported as an optimization improvement."""
    from backend.app.core.metrics import AllocationMetrics, MetricsCalculator
    calc = MetricsCalculator(snapshot)

    # Synthetic baseline metrics: 1000 min walking time
    base_m = AllocationMetrics(
        allocator_name="BaselineGreedyAllocator",
        academic_cycle="odd",
        evaluation_mode="factual",
        total_walking_time_minutes=1000.0,
        same_room_continuity_count=200,
    )
    # Synthetic raw solver metrics that timed out into worse local state: 1200 min
    raw_opt_m = AllocationMetrics(
        allocator_name="CPSATRoomOptimizer",
        academic_cycle="odd",
        evaluation_mode="factual",
        total_walking_time_minutes=1200.0,
        same_room_continuity_count=180,
    )

    # When solver candidate is worse, baseline must be retained
    fallback = (raw_opt_m.total_walking_time_minutes > base_m.total_walking_time_minutes)
    selected_m = base_m if fallback else raw_opt_m

    comp = calc.compare_solutions(
        baseline_metrics=base_m,
        optimized_metrics=selected_m,
        raw_solver_status="FEASIBLE",
        raw_solver_walking_time=raw_opt_m.total_walking_time_minutes,
        selected_allocator_name="BaselineGreedyAllocator_Retained" if fallback else "CPSATRoomOptimizer",
        fallback_to_baseline=fallback,
    )

    assert comp.fallback_to_baseline is True
    assert comp.improvement_achieved is False
    assert comp.raw_solver_status == "FEASIBLE"
    assert comp.raw_solver_walking_time == 1200.0
    assert comp.optimized_walking_time == 1000.0  # Retains baseline!
    assert comp.walking_time_reduction_minutes == 0.0
    assert comp.walking_time_reduction_percentage == 0.0
    assert comp.selected_allocator_name == "BaselineGreedyAllocator_Retained"


def test_odd_cycle_optimizer_baseline_protection_and_validity(snapshot: DatasetSnapshot):
    """Verifies odd-cycle comparison preserves valid baseline and truthful reporting."""
    alloc_service = AllocationService(snapshot)
    comp = alloc_service.compare_baseline_and_optimizer(
        academic_cycle="odd",
        time_limit_seconds=10.0,
    )

    assert comp.baseline_walking_time == 1248.0
    # Selected walking time must be <= baseline (never worse)
    assert comp.optimized_walking_time <= comp.baseline_walking_time
    assert comp.walking_time_reduction_minutes >= 0.0
    assert comp.raw_solver_status in ["FEASIBLE", "OPTIMAL"]
    if comp.fallback_to_baseline:
        assert comp.selected_allocator_name == "BaselineGreedyAllocator_Retained"
        assert comp.raw_solver_walking_time is not None
        assert comp.improvement_achieved is False
    else:
        assert comp.selected_allocator_name == "CPSATRoomOptimizer"
        assert comp.improvement_achieved is True

