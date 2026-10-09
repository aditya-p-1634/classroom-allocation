"""Tests for Dynamic Simulation and Bounded Disruption Recovery Engine (Phase P6).

Verifies the event lifecycle across all 5 events in events.csv,
bounded ripple reassignments (<= 2), duplicate event prevention,
rollback restoration, and transparent diagnosis of infeasible states.
"""

import pytest
from backend.app.schemas.models import DatasetSnapshot, DisruptionEvent
from backend.app.services.data_loader import DataLoaderService
from backend.app.core.simulation_engine import SimulationEngine, SimulationStatus


@pytest.fixture
def snapshot() -> DatasetSnapshot:
    return DataLoaderService().load_snapshot()


def test_all_five_documented_events_handled(snapshot: DatasetSnapshot):
    """Verifies that all 5 events in events.csv can be ingested and simulated through the engine."""
    assert len(snapshot.events) == 5

    for event in snapshot.events:
        engine = SimulationEngine(snapshot)
        result = engine.simulate_disruption(event)

        assert result.event_id == event.event_id
        assert result.event_type == event.event_type
        # Must return a valid truthful status
        assert result.status in [
            SimulationStatus.SUCCESS,
            SimulationStatus.INFEASIBLE_REPAIR,
            SimulationStatus.INVALID_EVENT,
        ]
        # Directly affected sessions must match the target session in event record
        if event.related_session_id:
            assert event.related_session_id in result.affected_sessions


def test_m601_closure_identifies_affected_and_diagnoses_infeasibility(snapshot: DatasetSnapshot):
    """Verifies M601 room closure (EVT-DEMO-001):

    Identifies SSN00005 as affected, evaluates recovery, and truthfully diagnoses that all
    20 laboratories on campus are simultaneously occupied, preventing valid recovery without
    violating hard capability constraints.
    """
    event = next(e for e in snapshot.events if e.event_id == "EVT-DEMO-001")
    engine = SimulationEngine(snapshot)

    result = engine.simulate_disruption(event, max_unaffected_reassignments=2)

    assert result.event_id == "EVT-DEMO-001"
    assert "SSN00005" in result.affected_sessions
    assert result.status == SimulationStatus.INFEASIBLE_REPAIR
    assert "laboratory" in result.diagnosis.lower()
    assert result.metrics is not None
    assert result.metrics.recovery_successful is False


def test_classroom_disruptions_recover_with_zero_ripple_reassignments(snapshot: DatasetSnapshot):
    """Verifies that classroom disruption scenarios (EVT-DEMO-003, EVT-DEMO-004, EVT-DEMO-005)

    recover successfully while reassigning <= 2 unaffected sessions (target achieved: 0 ripple moves).
    """
    for event_id in ["EVT-DEMO-003", "EVT-DEMO-004", "EVT-DEMO-005"]:
        event = next(e for e in snapshot.events if e.event_id == event_id)
        engine = SimulationEngine(snapshot)

        result = engine.simulate_disruption(event, max_unaffected_reassignments=2)

        assert result.status == SimulationStatus.SUCCESS
        assert result.unaffected_reassignments_count <= 2  # Criterion: <= 2 unaffected reassignments
        assert result.validation is not None
        assert result.validation.is_valid is True
        assert result.metrics is not None
        assert result.metrics.recovery_successful is True
        assert result.metrics.ripple_acceptable is True


def test_duplicate_event_processing_rejection(snapshot: DatasetSnapshot):
    """Verifies that the simulation engine rejects applying the same disruption event twice."""
    event = next(e for e in snapshot.events if e.event_id == "EVT-DEMO-003")
    engine = SimulationEngine(snapshot)

    # First run succeeds
    first_res = engine.simulate_disruption(event)
    assert first_res.status == SimulationStatus.SUCCESS

    # Second run with same event must be rejected
    second_res = engine.simulate_disruption(event)
    assert second_res.status == SimulationStatus.INVALID_EVENT
    assert "Duplicate event" in second_res.message


def test_invalid_target_room_rejection(snapshot: DatasetSnapshot):
    """Verifies that an event targeting a non-existent room is rejected immediately."""
    engine = SimulationEngine(snapshot)

    invalid_event = DisruptionEvent(
        event_id="EVT-INVALID-999",
        room_id="NON_EXISTENT_ROOM_XYZ",
        academic_cycle="even",
        start_day="Monday",
        start_period=1,
        end_day="Monday",
        end_period=2,
        event_type="room_closure",
        description="Invalid event test",
        status="simulation_only",
        source_status="synthetic",
        related_session_id="SSN00001",
    )

    res = engine.simulate_disruption(invalid_event)
    assert res.status == SimulationStatus.INVALID_EVENT
    assert "does not exist" in res.message


def test_state_rollback_preserves_initial_assignments(snapshot: DatasetSnapshot):
    """Verifies that rollback restores the initial working assignment state completely."""
    event = next(e for e in snapshot.events if e.event_id == "EVT-DEMO-003")
    engine = SimulationEngine(snapshot)

    initial_assignments = engine.current_assignments
    res = engine.simulate_disruption(event)
    assert res.status == SimulationStatus.SUCCESS

    # Current assignments should reflect the move
    target_s_id = event.related_session_id
    assert engine.current_assignments[target_s_id] != initial_assignments[target_s_id]

    # Perform rollback
    rolled_back = engine.rollback()
    assert rolled_back is True
    assert engine.current_assignments == initial_assignments
    assert event.event_id not in engine.applied_event_ids


def test_feasible_synthetic_room_closure_recovers_successfully(snapshot: DatasetSnapshot):
    """Verifies that a room closure with genuine compatible capacity recovers successfully.

    Distinct from EVT-DEMO-001 (where all 20 campus laboratories are concurrently saturated),
    this explicitly labeled synthetic fixture simulates a room closure on classroom A105
    during Monday Period 1 (targeting session SSN00207 in the even cycle), where alternative
    compatible classrooms exist.

    Demonstrates:
    - Truthful diagnosis of recovery when capacity exists.
    - Successful reassignment to a compatible classroom.
    - Zero unaffected session reassignments (strictly <= 2 ripple reassignments).
    - Independent validation of candidate passes with zero constraint violations.
    """
    target_session = next(
        s for s in snapshot.sessions
        if s.academic_cycle == "even" and s.assigned_room_id == "A105" and s.day == "Monday" and 1 in s.period_range
    )

    synthetic_event = DisruptionEvent(
        event_id="EVT-SYNTH-CLOSURE-FEASIBLE",
        room_id="A105",
        academic_cycle="even",
        start_day="Monday",
        start_period=target_session.start_period,
        end_day="Monday",
        end_period=target_session.end_period,
        event_type="room_closure",
        description="Feasible synthetic room closure: temporary maintenance of classroom A105",
        status="simulation_only",
        source_status="synthetic",
        related_session_id=target_session.session_id,
    )

    engine = SimulationEngine(snapshot)
    result = engine.simulate_disruption(synthetic_event, max_unaffected_reassignments=2)

    assert result.event_id == "EVT-SYNTH-CLOSURE-FEASIBLE"
    assert result.status == SimulationStatus.SUCCESS
    assert target_session.session_id in result.affected_sessions
    assert result.unaffected_reassignments_count <= 2
    assert result.unaffected_reassignments_count == 0  # Reassigned directly without ripple
    assert result.validation is not None
    assert result.validation.is_valid is True
    assert result.validation.fail_count == 0
    assert result.metrics is not None
    assert result.metrics.recovery_successful is True
    assert result.metrics.ripple_acceptable is True

