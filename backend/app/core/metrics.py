"""Standardized Allocation Metrics Engine for ClassroomIQ.

Governed by Master Project Specification §9.3, Document 03 §8, and Document 05 Phase P6.
Provides verifiable, reproducible calculations for:
1. Cohort walking time across consecutive scheduled periods (T_walk proxy).
2. Room-type suitability and unnecessary specialized-room usage.
3. Disruption reassignment impact (D_repair).
4. Time-slot and seat utilization.
5. Structured comparative reporting between baseline and optimized solutions.
"""

from typing import Dict, List, Optional, Tuple, Any
from pydantic import BaseModel, Field

from backend.app.schemas.models import DatasetSnapshot, Session, Room, DisruptionEvent
from backend.app.schemas.validation import AllocationCandidate
from backend.app.services.travel_matrix import TravelMatrixService


class CohortTransitionMetric(BaseModel):
    """Details of a single consecutive-period room change for a student cohort."""
    cohort_id: str
    academic_cycle: str
    day: str
    from_period: int
    to_period: int
    from_session_id: str
    to_session_id: str
    from_room_id: str
    to_room_id: str
    walking_time_minutes: float
    is_same_room: bool


class AllocationMetrics(BaseModel):
    """Standardized metric evaluation results for an allocation candidate."""
    allocator_name: str
    academic_cycle: str
    evaluation_mode: str  # 'factual' or 'synthetic_evaluation'
    
    # 1. Travel Metrics (Proxy)
    total_walking_time_minutes: float = Field(0.0, description="Sum of cohort walking times between consecutive sessions")
    total_cohort_transitions: int = Field(0, description="Number of consecutive-session pairs for cohorts")
    same_room_continuity_count: int = Field(0, description="Number of consecutive transitions staying in the same room")
    average_walking_time_per_transition: float = Field(0.0, description="Mean walking time in minutes per transition")
    walking_time_provenance: str = Field(
        "synthetic_prefix_proxy_minutes",
        description="Explicit provenance label distinguishing proxy from measured times",
    )

    # 2. Room Suitability & Specialization
    total_assigned_sessions: int = 0
    exact_room_type_matches: int = Field(0, description="Sessions placed in exact primary room type")
    secondary_permitted_matches: int = Field(0, description="Sessions placed in approved additional use (e.g. project_room)")
    specialized_room_misuse_count: int = Field(0, description="Classroom sessions placed in specialized labs")
    room_suitability_percentage: float = Field(0.0, description="Percentage of assignments matching exact primary room type")

    # 3. Utilization Metrics
    total_occupied_slots: int = Field(0, description="Sum of (room x period) slots occupied")
    total_capacity_slots: int = Field(0, description="Total possible slots (rooms x periods x days)")
    slot_utilization_percentage: float = Field(0.0, description="Occupied slots divided by total slots")
    
    # Synthetic Capacity Slack (populated only when synthetic profile provided)
    synthetic_seat_utilization_percentage: Optional[float] = Field(None, description="Average seat fill percentage under synthetic profile")
    synthetic_total_wasted_seats: Optional[int] = Field(None, description="Sum of (room_capacity - student_demand)")

    # 4. Latency
    execution_time_ms: float = 0.0


class DisruptionRepairMetrics(BaseModel):
    """Metrics tracking disruption impact and bounded recovery."""
    event_id: str
    event_type: str
    disrupted_room_id: str
    directly_affected_sessions_count: int
    directly_affected_session_ids: List[str]
    reassigned_sessions_count: int
    unaffected_sessions_reassigned_count: int
    unassigned_after_repair_count: int
    recovery_successful: bool
    ripple_acceptable: bool = Field(..., description="True if unaffected reassignments <= 2")


class MetricComparison(BaseModel):
    """Side-by-side metric comparison between a baseline and an optimized solution."""
    academic_cycle: str
    baseline_allocator_name: str
    optimized_allocator_name: str
    
    # Baseline vs Optimized Walking Time
    baseline_walking_time: float
    optimized_walking_time: float
    walking_time_reduction_minutes: float
    walking_time_reduction_percentage: float

    # Same-room continuity
    baseline_same_room_count: int
    optimized_same_room_count: int

    # Specialized room misuse
    baseline_specialized_misuse: int
    optimized_specialized_misuse: int

    # Execution Latency
    baseline_execution_ms: float
    optimized_execution_ms: float

    # Raw Solver Status & Baseline Protection (Phase P6 Remediation)
    raw_solver_status: Optional[str] = Field(None, description="Actual termination status of CP-SAT solver (OPTIMAL, FEASIBLE, etc.)")
    raw_solver_walking_time: Optional[float] = Field(None, description="Raw walking-time metric from the raw solver candidate")
    selected_allocator_name: Optional[str] = Field(None, description="Allocator whose candidate was selected as the best valid output")
    fallback_to_baseline: bool = Field(False, description="True if raw candidate was worse than baseline and baseline was retained")
    improvement_achieved: bool = Field(True, description="True if solver achieved a genuine walking-time improvement over baseline")

    evidence_limitations: List[str] = Field(default_factory=list)


class MetricsCalculator:
    """Computes verifiable allocation metrics from domain snapshots and candidates."""

    def __init__(self, snapshot: DatasetSnapshot, travel_service: Optional[TravelMatrixService] = None):
        self.snapshot = snapshot
        self.travel_service = travel_service or TravelMatrixService()
        self.rooms_by_id: Dict[str, Room] = snapshot.room_index
        self.sessions_by_id: Dict[str, Session] = snapshot.session_index

    def calculate_metrics(
        self,
        candidate: AllocationCandidate,
        allocator_name: str = "Unknown",
        execution_time_ms: float = 0.0,
        evaluation_mode: str = "factual",
        synthetic_demands: Optional[Dict[str, int]] = None,
        synthetic_capacities: Optional[Dict[str, int]] = None,
        synthetic_room_capacities: Optional[Dict[str, int]] = None,
        synthetic_session_demands: Optional[Dict[str, int]] = None,
        sessions_to_evaluate: Optional[List[Session]] = None,
    ) -> AllocationMetrics:
        """Calculates complete standardized metrics for a candidate allocation."""
        synthetic_capacities = synthetic_capacities or synthetic_room_capacities
        synthetic_demands = synthetic_demands or synthetic_session_demands

        cycle = candidate.academic_cycle

        # Filter target sessions matching cycle or provided list
        if sessions_to_evaluate is not None:
            target_sessions = sessions_to_evaluate
        elif cycle in ["odd", "even"]:
            target_sessions = [s for s in self.snapshot.sessions if s.academic_cycle == cycle]
        else:
            target_sessions = self.snapshot.sessions

        # 1. Evaluate Cohort Walking Time (Consecutive periods on same day)
        transitions = self.get_cohort_transitions(candidate, target_sessions)
        total_walking_time = sum(t.walking_time_minutes for t in transitions)
        same_room_count = sum(1 for t in transitions if t.is_same_room)
        num_transitions = len(transitions)
        avg_walk = (total_walking_time / num_transitions) if num_transitions > 0 else 0.0

        # 2. Evaluate Room-Type Suitability
        exact_matches = 0
        secondary_matches = 0
        specialized_misuse = 0
        assigned_count = 0

        for s in target_sessions:
            room_id = candidate.assignments.get(s.session_id)
            if not room_id:
                continue

            assigned_count += 1
            room = self.rooms_by_id.get(room_id)
            if not room:
                continue

            if s.required_room_type == room.room_type:
                exact_matches += 1
            elif s.required_room_type in room.permitted_uses:
                secondary_matches += 1

            # Misuse: required classroom placed into laboratory
            if s.required_room_type == "classroom" and room.room_type == "laboratory":
                specialized_misuse += 1

        suitability_pct = (exact_matches / assigned_count * 100.0) if assigned_count > 0 else 0.0

        # 3. Time-Slot Utilization
        # Denominator: 86 rooms x 8 periods x 5 weekdays = 3,440 slots per cycle
        total_slots_per_cycle = len(self.snapshot.rooms) * 8 * 5
        denom_slots = total_slots_per_cycle if cycle in ["odd", "even"] else (total_slots_per_cycle * 2)

        occupied_period_slots = 0
        for s in target_sessions:
            if candidate.assignments.get(s.session_id):
                occupied_period_slots += s.duration_periods

        slot_util_pct = (occupied_period_slots / denom_slots * 100.0) if denom_slots > 0 else 0.0

        # 4. Synthetic Seat Utilization (if profile provided)
        seat_util_pct = None
        wasted_seats = None
        if synthetic_demands and synthetic_capacities:
            total_demand = 0
            total_seat_cap = 0
            for s in target_sessions:
                r_id = candidate.assignments.get(s.session_id)
                if r_id and s.session_id in synthetic_demands and r_id in synthetic_capacities:
                    d = synthetic_demands[s.session_id]
                    c = synthetic_capacities[r_id]
                    total_demand += d
                    total_seat_cap += c
            if total_seat_cap > 0:
                seat_util_pct = round((total_demand / total_seat_cap) * 100.0, 2)
                wasted_seats = max(0, total_seat_cap - total_demand)

        return AllocationMetrics(
            allocator_name=allocator_name,
            academic_cycle=cycle,
            evaluation_mode=evaluation_mode,
            total_walking_time_minutes=round(total_walking_time, 2),
            total_cohort_transitions=num_transitions,
            same_room_continuity_count=same_room_count,
            average_walking_time_per_transition=round(avg_walk, 2),
            total_assigned_sessions=assigned_count,
            exact_room_type_matches=exact_matches,
            secondary_permitted_matches=secondary_matches,
            specialized_room_misuse_count=specialized_misuse,
            room_suitability_percentage=round(suitability_pct, 2),
            total_occupied_slots=occupied_period_slots,
            total_capacity_slots=denom_slots,
            slot_utilization_percentage=round(slot_util_pct, 2),
            synthetic_seat_utilization_percentage=seat_util_pct,
            synthetic_total_wasted_seats=wasted_seats,
            execution_time_ms=round(execution_time_ms, 2),
        )

    def get_cohort_transitions(
        self,
        candidate: AllocationCandidate,
        sessions: Optional[List[Session]] = None,
        sessions_to_evaluate: Optional[List[Session]] = None,
    ) -> List[CohortTransitionMetric]:
        """Extracts all consecutive-period room transitions for every student cohort."""
        target_sessions = sessions if sessions is not None else (sessions_to_evaluate or self.snapshot.sessions)

        # Group assigned sessions by (cohort_id, academic_cycle, day)
        cohort_day_sessions: Dict[Tuple[str, str, str], List[Session]] = {}

        for s in target_sessions:
            room_id = candidate.assignments.get(s.session_id)
            if not room_id:
                continue
            key = (s.cohort_id, s.academic_cycle, s.day)
            cohort_day_sessions.setdefault(key, []).append(s)

        transitions: List[CohortTransitionMetric] = []

        for (cohort_id, cycle, day), sess_list in cohort_day_sessions.items():
            # Sort sessions by start_period
            sorted_sessions = sorted(sess_list, key=lambda s: s.start_period)

            for i in range(len(sorted_sessions) - 1):
                s1 = sorted_sessions[i]
                s2 = sorted_sessions[i + 1]

                # Consecutive period check: s1 ends right before s2 starts
                # or immediately adjacent scheduled periods
                if s1.end_period + 1 == s2.start_period:
                    r1 = candidate.assignments[s1.session_id]
                    r2 = candidate.assignments[s2.session_id]
                    w_time = self.travel_service.get_travel_time(r1, r2)

                    transitions.append(
                        CohortTransitionMetric(
                            cohort_id=cohort_id,
                            academic_cycle=cycle,
                            day=day,
                            from_period=s1.end_period,
                            to_period=s2.start_period,
                            from_session_id=s1.session_id,
                            to_session_id=s2.session_id,
                            from_room_id=r1,
                            to_room_id=r2,
                            walking_time_minutes=w_time,
                            is_same_room=(r1 == r2),
                        )
                    )

        return transitions

    def compare_solutions(
        self,
        baseline_metrics: AllocationMetrics,
        optimized_metrics: AllocationMetrics,
        raw_solver_status: Optional[str] = None,
        raw_solver_walking_time: Optional[float] = None,
        selected_allocator_name: Optional[str] = None,
        fallback_to_baseline: bool = False,
        improvement_achieved: Optional[bool] = None,
    ) -> MetricComparison:
        """Compares baseline vs optimized solutions and calculates genuine deltas."""
        base_t = baseline_metrics.total_walking_time_minutes
        opt_t = optimized_metrics.total_walking_time_minutes

        delta_t = round(base_t - opt_t, 2)
        pct_t = round((delta_t / base_t * 100.0), 2) if base_t > 0 else 0.0

        if improvement_achieved is None:
            improvement_achieved = (delta_t > 0.0 and not fallback_to_baseline)

        limitations = [
            "Walking times are calculated using the synthetic prefix-distance matrix (3.0/8.0 min proxy), not GPS-measured routes.",
            "Feasibility is verified independently; no soft scores compromise hard constraints.",
        ]

        return MetricComparison(
            academic_cycle=baseline_metrics.academic_cycle,
            baseline_allocator_name=baseline_metrics.allocator_name,
            optimized_allocator_name=optimized_metrics.allocator_name,
            baseline_walking_time=base_t,
            optimized_walking_time=opt_t,
            walking_time_reduction_minutes=delta_t,
            walking_time_reduction_percentage=pct_t,
            baseline_same_room_count=baseline_metrics.same_room_continuity_count,
            optimized_same_room_count=optimized_metrics.same_room_continuity_count,
            baseline_specialized_misuse=baseline_metrics.specialized_room_misuse_count,
            optimized_specialized_misuse=optimized_metrics.specialized_room_misuse_count,
            baseline_execution_ms=baseline_metrics.execution_time_ms,
            optimized_execution_ms=optimized_metrics.execution_time_ms,
            raw_solver_status=raw_solver_status,
            raw_solver_walking_time=raw_solver_walking_time,
            selected_allocator_name=selected_allocator_name or (baseline_metrics.allocator_name if fallback_to_baseline else optimized_metrics.allocator_name),
            fallback_to_baseline=fallback_to_baseline,
            improvement_achieved=improvement_achieved,
            evidence_limitations=limitations,
        )

    # Method aliases for consistent invocation across test suites
    compare_allocations = compare_solutions
    calculate_cohort_transitions = get_cohort_transitions

    def calculate_disruption_metrics(
        self,
        event: DisruptionEvent,
        affected_sessions: List[Session],
        initial_assignments: Dict[str, str],
        repaired_assignments: Dict[str, str],
        recovery_successful: bool,
    ) -> DisruptionRepairMetrics:
        """Calculates disruption impact metrics including ripple reassignments."""
        affected_ids = [s.session_id for s in affected_sessions]

        reassigned_count = sum(
            1 for s_id in initial_assignments
            if s_id in repaired_assignments and initial_assignments[s_id] != repaired_assignments[s_id]
        )

        unaffected_reassigned_count = sum(
            1 for s_id in initial_assignments
            if s_id not in affected_ids
            and s_id in repaired_assignments
            and initial_assignments[s_id] != repaired_assignments[s_id]
        )

        unassigned_after_repair = len(affected_ids) if not recovery_successful else 0

        return DisruptionRepairMetrics(
            event_id=event.event_id,
            event_type=event.event_type,
            disrupted_room_id=event.room_id,
            directly_affected_sessions_count=len(affected_ids),
            directly_affected_session_ids=affected_ids,
            reassigned_sessions_count=reassigned_count,
            unaffected_sessions_reassigned_count=unaffected_reassigned_count,
            unassigned_after_repair_count=unassigned_after_repair,
            recovery_successful=recovery_successful,
            ripple_acceptable=(unaffected_reassigned_count <= 2),
        )
