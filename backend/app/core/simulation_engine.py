"""Controlled Dynamic Simulation and Bounded Disruption Recovery Engine for ClassroomIQ.

Governed by Master Project Specification §9.4, Document 03 §8, and Document 05 Phase P6.
Handles the complete event lifecycle for dynamic classroom disruptions:
1. Event validation (rejecting duplicates, malformed records, or invalid room targets).
2. Direct affected-session identification across schedule time slices.
3. Atomic working-state mutation with rollback checkpoints.
4. Bounded recovery optimization using CP-SAT (minimizing ripple reassignments to <= 2).
5. Independent validation of repaired schedules.
"""

from enum import Enum
from typing import Dict, List, Optional, Set, Tuple, Any
from pydantic import BaseModel, Field

from backend.app.config import CapacityPolicyMode
from backend.app.schemas.models import DatasetSnapshot, DisruptionEvent, Session, Room
from backend.app.schemas.validation import (
    AllocationCandidate,
    AllocationResult,
    ValidationSummary,
    AllocationStatus,
)
from backend.app.core.optimizer import CPSATRoomOptimizer
from backend.app.core.validator import IndependentValidator
from backend.app.core.metrics import DisruptionRepairMetrics, MetricsCalculator


class SimulationStatus(str, Enum):
    """Truthful outcome status classification for disruption events."""
    SUCCESS = "successful_recovery"
    INFEASIBLE_REPAIR = "infeasible_repair"
    INVALID_EVENT = "event_application_failure"
    VALIDATION_FAILURE = "invalid_candidate"
    TIMEOUT = "timeout"


class DisruptionSimulationResult(BaseModel):
    """Comprehensive result of a disruption event simulation and recovery attempt."""
    event_id: str
    event_type: str
    status: SimulationStatus
    message: str
    affected_sessions: List[str]
    reassigned_sessions: Dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of session_id to newly assigned room_id",
    )
    unaffected_reassignments_count: int = 0
    candidate: Optional[AllocationCandidate] = None
    validation: Optional[ValidationSummary] = None
    metrics: Optional[DisruptionRepairMetrics] = None
    diagnosis: Optional[str] = None


class SimulationEngine:
    """Manages event lifecycles, atomic state updates, and bounded schedule recovery."""

    VALID_EVENT_TYPES = {
        "room_closure",
        "equipment_failure",
        "projector_failure",
        "maintenance",
        "power_disruption",
    }

    VALID_DAYS = {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday"}

    def __init__(
        self,
        snapshot: DatasetSnapshot,
        initial_assignments: Optional[Dict[str, str]] = None,
        capacity_mode: CapacityPolicyMode = CapacityPolicyMode.FACTUAL,
        allow_computing_lab_exception: bool = True,
    ):
        """Initializes the simulation engine.

        Args:
            snapshot: Immutable dataset snapshot.
            initial_assignments: Initial session room assignments. Defaults to source timetable.
            capacity_mode: Factual vs Synthetic mode.
            allow_computing_lab_exception: Allow computing lab anomaly sessions.
        """
        self.snapshot = snapshot
        self.capacity_mode = capacity_mode
        self.allow_computing_lab_exception = allow_computing_lab_exception
        self.metrics_calculator = MetricsCalculator(snapshot)

        # Working state mapping: session_id -> room_id
        if initial_assignments is not None:
            self._working_assignments = dict(initial_assignments)
        else:
            self._working_assignments = {
                s.session_id: s.assigned_room_id for s in snapshot.sessions
            }

        # Event tracking and rollback checkpoints
        self._applied_events: Dict[str, DisruptionEvent] = {}
        self._history: List[Tuple[str, Dict[str, str]]] = []  # List of (event_id, snapshot_copy)

    @property
    def current_assignments(self) -> Dict[str, str]:
        """Returns the current active working assignments."""
        return dict(self._working_assignments)

    @property
    def applied_event_ids(self) -> List[str]:
        """Returns the list of applied event IDs."""
        return list(self._applied_events.keys())

    def validate_event(self, event: DisruptionEvent) -> Tuple[bool, str]:
        """Validates an event before applying it.

        Checks:
        1. Duplicate event prevention (idempotency).
        2. Valid room target existence.
        3. Valid event type.
        4. Valid academic cycle, days, and period ranges.
        """
        # 1. Duplicate event check
        if event.event_id in self._applied_events:
            return False, f"Duplicate event: '{event.event_id}' has already been processed."

        # 2. Room existence check
        if event.room_id not in self.snapshot.room_index:
            return False, f"Target room '{event.room_id}' does not exist in rooms catalog."

        # 3. Event type check
        if event.event_type not in self.VALID_EVENT_TYPES:
            return False, f"Unrecognized event type '{event.event_type}'."

        # 4. Day & Period checks
        if event.start_day not in self.VALID_DAYS:
            return False, f"Invalid start day '{event.start_day}'."
        if event.end_day not in self.VALID_DAYS:
            return False, f"Invalid end day '{event.end_day}'."
        if event.start_period < 1 or event.end_period > 8 or event.start_period > event.end_period:
            return False, f"Invalid period range {event.start_period}-{event.end_period}."

        if event.academic_cycle not in ["odd", "even"]:
            return False, f"Invalid academic cycle '{event.academic_cycle}'."

        return True, "Event is valid."

    def identify_affected_sessions(self, event: DisruptionEvent) -> List[Session]:
        """Identifies sessions in the active schedule directly impacted by the disruption."""
        affected: List[Session] = []

        for s in self.snapshot.sessions:
            if s.academic_cycle != event.academic_cycle:
                continue

            # Must be currently scheduled in the disrupted room
            current_room = self._working_assignments.get(s.session_id)
            if current_room != event.room_id:
                continue

            # Check day alignment
            if s.day != event.start_day:
                continue

            # Check period overlap
            event_periods = set(range(event.start_period, event.end_period + 1))
            session_periods = set(s.period_range)

            if event_periods.intersection(session_periods):
                affected.append(s)

        return affected

    def simulate_disruption(
        self,
        event: DisruptionEvent,
        max_unaffected_reassignments: int = 2,
        time_limit_seconds: float = 5.0,
    ) -> DisruptionSimulationResult:
        """Applies a disruption event and executes bounded repair to restore feasibility.

        Maintains strict boundaries:
        - Atomic state changes with checkpointing.
        - Freezes unaffected sessions to limit ripple reassignments <= max_unaffected_reassignments.
        - Employs CP-SAT room optimizer for candidate search.
        - Validates resulting candidate with IndependentValidator.
        - Truthfully reports infeasibility when no alternative room exists.
        """
        # 1. Validate the event
        is_valid, validation_msg = self.validate_event(event)
        if not is_valid:
            return DisruptionSimulationResult(
                event_id=event.event_id,
                event_type=event.event_type,
                status=SimulationStatus.INVALID_EVENT,
                message=validation_msg,
                affected_sessions=[],
                diagnosis=validation_msg,
            )

        # 2. Checkpoint state for rollback
        self._history.append((event.event_id, dict(self._working_assignments)))

        # 3. Identify directly affected sessions
        affected_sessions = self.identify_affected_sessions(event)
        affected_ids = [s.session_id for s in affected_sessions]

        if not affected_sessions:
            # No sessions affected by this event (room was already vacant during that window)
            self._applied_events[event.event_id] = event
            return DisruptionSimulationResult(
                event_id=event.event_id,
                event_type=event.event_type,
                status=SimulationStatus.SUCCESS,
                message="Disrupted room was already unoccupied during event window. Zero sessions impacted.",
                affected_sessions=[],
                unaffected_reassignments_count=0,
            )

        # 4. Construct blocked slots: (room_id, day, period) for the event
        blocked_slots: Set[Tuple[str, str, int]] = set()
        for p in range(event.start_period, event.end_period + 1):
            blocked_slots.add((event.room_id, event.start_day, p))

        # 5. Bounded Repair Search
        # Filter sessions for the relevant academic cycle
        cycle_sessions = [
            s for s in self.snapshot.sessions if s.academic_cycle == event.academic_cycle
        ]
        unaffected_sessions = [s for s in cycle_sessions if s.session_id not in affected_ids]

        # Stage A: Pure Direct Placement (Freeze ALL unaffected sessions; 0 ripple moves)
        pre_reserved = {
            s.session_id: self._working_assignments[s.session_id]
            for s in unaffected_sessions
            if s.session_id in self._working_assignments
        }

        optimizer = CPSATRoomOptimizer(
            snapshot=self.snapshot,
            allow_computing_lab_exception=self.allow_computing_lab_exception,
            capacity_mode=self.capacity_mode,
        )

        candidate = optimizer.solve(
            academic_cycle=event.academic_cycle,
            sessions_to_allocate=affected_sessions,
            pre_reserved_assignments=pre_reserved,
            blocked_room_periods=blocked_slots,
            time_limit_seconds=time_limit_seconds,
        )

        repair_successful = (
            len(candidate.unassigned_sessions) == 0
            and all(s_id in candidate.assignments for s_id in affected_ids)
        )

        unaffected_reassigned_count = 0
        reassigned_dict: Dict[str, str] = {}

        if repair_successful:
            # Independent validation
            validator = IndependentValidator(
                snapshot=self.snapshot,
                capacity_mode=self.capacity_mode,
                allow_computing_lab_exception=self.allow_computing_lab_exception,
            )
            val_summary = validator.validate_candidate(candidate, sessions_to_verify=cycle_sessions)

            if val_summary.is_valid:
                for s_id in affected_ids:
                    reassigned_dict[s_id] = candidate.assignments[s_id]
                    self._working_assignments[s_id] = candidate.assignments[s_id]

                self._applied_events[event.event_id] = event

                metrics = self.metrics_calculator.calculate_disruption_metrics(
                    event=event,
                    affected_sessions=affected_sessions,
                    initial_assignments=self._history[-1][1],
                    repaired_assignments=self._working_assignments,
                    recovery_successful=True,
                )

                return DisruptionSimulationResult(
                    event_id=event.event_id,
                    event_type=event.event_type,
                    status=SimulationStatus.SUCCESS,
                    message=f"Successfully repaired disruption. Reassigned {len(reassigned_dict)} affected session(s) with 0 ripple moves.",
                    affected_sessions=affected_ids,
                    reassigned_sessions=reassigned_dict,
                    unaffected_reassignments_count=0,
                    candidate=candidate,
                    validation=val_summary,
                    metrics=metrics,
                )
            else:
                self.rollback()
                return DisruptionSimulationResult(
                    event_id=event.event_id,
                    event_type=event.event_type,
                    status=SimulationStatus.VALIDATION_FAILURE,
                    message="Proposed repair candidate failed independent constraint validation.",
                    affected_sessions=affected_ids,
                    candidate=candidate,
                    validation=val_summary,
                    diagnosis=f"Validation errors: {[f.message for f in val_summary.error_findings]}",
                )

        # Stage B: Bounded Ripple Exploration (if direct placement failed, allow <= max_unaffected_reassignments)
        if max_unaffected_reassignments > 0:
            # Find candidate unaffected sessions in the same period window that could potentially swap
            event_periods = set(range(event.start_period, event.end_period + 1))
            same_window_unaffected = [
                s for s in unaffected_sessions
                if s.day == event.start_day and event_periods.intersection(set(s.period_range))
            ]

            # If lab is required, see if any lab room is occupied by a non-lab or if a swap is possible
            # We select at most max_unaffected_reassignments candidates to include in the reallocation pool
            for k in range(1, min(max_unaffected_reassignments + 1, len(same_window_unaffected) + 1)):
                subset_unaffected = same_window_unaffected[:k]
                realloc_pool = affected_sessions + subset_unaffected
                realloc_ids = {s.session_id for s in realloc_pool}

                pre_reserved_k = {
                    s.session_id: self._working_assignments[s.session_id]
                    for s in unaffected_sessions
                    if s.session_id not in realloc_ids
                }

                target_reassign = {
                    s.session_id: self._working_assignments[s.session_id]
                    for s in subset_unaffected
                }

                cand_k = optimizer.solve(
                    academic_cycle=event.academic_cycle,
                    sessions_to_allocate=realloc_pool,
                    pre_reserved_assignments=pre_reserved_k,
                    blocked_room_periods=blocked_slots,
                    target_reassignments=target_reassign,
                    time_limit_seconds=time_limit_seconds,
                )

                if len(cand_k.unassigned_sessions) == 0:
                    # Count how many unaffected actually moved
                    unaffected_moved = [
                        s.session_id for s in subset_unaffected
                        if cand_k.assignments.get(s.session_id) != self._working_assignments.get(s.session_id)
                    ]

                    if len(unaffected_moved) <= max_unaffected_reassignments:
                        val_summary = validator.validate_candidate(cand_k, sessions_to_verify=cycle_sessions)
                        if val_summary.is_valid:
                            for s in realloc_pool:
                                self._working_assignments[s.session_id] = cand_k.assignments[s.session_id]
                                if s.session_id in affected_ids or s.session_id in unaffected_moved:
                                    reassigned_dict[s.session_id] = cand_k.assignments[s.session_id]

                            self._applied_events[event.event_id] = event
                            metrics = self.metrics_calculator.calculate_disruption_metrics(
                                event=event,
                                affected_sessions=affected_sessions,
                                initial_assignments=self._history[-1][1],
                                repaired_assignments=self._working_assignments,
                                recovery_successful=True,
                            )

                            return DisruptionSimulationResult(
                                event_id=event.event_id,
                                event_type=event.event_type,
                                status=SimulationStatus.SUCCESS,
                                message=f"Repaired disruption with {len(unaffected_moved)} ripple reassignments (bounded <= {max_unaffected_reassignments}).",
                                affected_sessions=affected_ids,
                                reassigned_sessions=reassigned_dict,
                                unaffected_reassignments_count=len(unaffected_moved),
                                candidate=cand_k,
                                validation=val_summary,
                                metrics=metrics,
                            )

        # If we reach here, repair is strictly infeasible under current hard constraints and boundaries
        self.rollback()

        # Diagnose the exact bottleneck
        bottleneck_reasons = []
        for s in affected_sessions:
            req = s.required_room_type
            capable_rooms = [r for r in self.snapshot.rooms if req in r.permitted_uses and r.room_id != event.room_id]
            # Check how many capable rooms are occupied
            occupied_count = 0
            for r in capable_rooms:
                for p in s.period_range:
                    # check if any session is in r at this period
                    occupied_by = [
                        sid for sid, rid in self._working_assignments.items()
                        if rid == r.room_id
                        and self.snapshot.session_index[sid].academic_cycle == event.academic_cycle
                        and self.snapshot.session_index[sid].day == event.start_day
                        and p in self.snapshot.session_index[sid].period_range
                    ]
                    if occupied_by:
                        occupied_count += 1
                        break
            free_capable = len(capable_rooms) - occupied_count
            bottleneck_reasons.append(
                f"Session '{s.session_id}' ({s.course}) requires '{req}': "
                f"campus has {len(capable_rooms)} capable alternative rooms, but {occupied_count} are occupied "
                f"({free_capable} free during {event.start_day} P{s.start_period}-P{s.end_period})."
            )

        diagnosis_text = (
            f"Bounded recovery failed: No feasible alternative room exists without violating hard constraints. "
            f"Details: {'; '.join(bottleneck_reasons)}"
        )

        metrics = self.metrics_calculator.calculate_disruption_metrics(
            event=event,
            affected_sessions=affected_sessions,
            initial_assignments=self._history[-1][1] if self._history else self._working_assignments,
            repaired_assignments=self._working_assignments,
            recovery_successful=False,
        )

        return DisruptionSimulationResult(
            event_id=event.event_id,
            event_type=event.event_type,
            status=SimulationStatus.INFEASIBLE_REPAIR,
            message="Repair proved infeasible under approved hard constraints: campus capacity exhausted for required room capability.",
            affected_sessions=affected_ids,
            unaffected_reassignments_count=0,
            diagnosis=diagnosis_text,
            metrics=metrics,
        )

    def rollback(self) -> bool:
        """Rolls back the most recently simulated event to restore previous valid state."""
        if not self._history:
            return False

        last_event_id, previous_state = self._history.pop()
        self._working_assignments = previous_state
        self._applied_events.pop(last_event_id, None)
        return True
