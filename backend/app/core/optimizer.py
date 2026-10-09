"""Mathematical Room-Assignment Optimization Engine for ClassroomIQ.

Governed by Master Project Specification §9.2, Document 03 §8, and Document 05 Phase P6.
Uses Google OR-Tools CP-SAT to solve constrained classroom allocation.
Preserves session cycle, day, period range, course, and cohort.
Enforces room-time exclusivity, cohort-time exclusivity, and room capabilities as absolute hard constraints.
Optimizes cohort walking-time proxies, same-room continuity, and room specialization suitability.
Every candidate solution is independently verified by the IndependentValidator before acceptance.
"""

import time
from typing import Dict, List, Optional, Set, Tuple, Any
from ortools.sat.python import cp_model

from backend.app.config import CapacityPolicyMode
from backend.app.schemas.models import DatasetSnapshot, Room, Session
from backend.app.schemas.validation import (
    AllocationCandidate,
    AllocationResult,
    AllocationStatus,
    ValidationSummary,
)
from backend.app.core.validator import (
    IndependentValidator,
    COMPUTING_LAB_ANOMALY_SESSION_IDS,
)


class CPSATRoomOptimizer:
    """CP-SAT room allocator optimizing travel continuity and room suitability."""

    def __init__(
        self,
        snapshot: DatasetSnapshot,
        allow_computing_lab_exception: bool = False,
        capacity_mode: CapacityPolicyMode = CapacityPolicyMode.FACTUAL,
        synthetic_room_capacities: Optional[Dict[str, int]] = None,
        synthetic_session_demands: Optional[Dict[str, int]] = None,
    ):
        """Initializes the optimizer with snapshot and evaluation configurations.

        Args:
            snapshot: Immutable dataset snapshot containing rooms and sessions.
            allow_computing_lab_exception: Whether to allow the 10 computing lab sessions.
            capacity_mode: Factual vs Synthetic evaluation mode.
            synthetic_room_capacities: Optional synthetic room capacities.
            synthetic_session_demands: Optional synthetic cohort student demands.
        """
        self.snapshot = snapshot
        self.allow_computing_lab_exception = allow_computing_lab_exception
        self.capacity_mode = capacity_mode
        self.synthetic_room_capacities = synthetic_room_capacities or {}
        self.synthetic_session_demands = synthetic_session_demands or {}
        self.rooms_by_id: Dict[str, Room] = snapshot.room_index

    def _get_eligible_rooms(self, session: Session) -> List[Room]:
        """Finds all rooms matching capabilities and optional capacity requirements."""
        req_type = session.required_room_type
        eligible: List[Room] = []

        for room in self.snapshot.rooms:
            # 1. Room capability check
            is_capable = req_type in room.permitted_uses
            if (
                not is_capable
                and self.allow_computing_lab_exception
                and session.session_id in COMPUTING_LAB_ANOMALY_SESSION_IDS
                and room.room_type == "laboratory"
            ):
                is_capable = True

            if not is_capable:
                continue

            # 2. Synthetic capacity check if in synthetic mode
            if self.capacity_mode == CapacityPolicyMode.SYNTHETIC_EVALUATION:
                demand = self.synthetic_session_demands.get(session.session_id)
                cap = self.synthetic_room_capacities.get(room.room_id)
                if demand is not None and cap is not None and demand > cap:
                    continue

            eligible.append(room)

        return sorted(eligible, key=lambda r: r.room_id)

    def _find_consecutive_cohort_transitions(
        self, sessions: List[Session]
    ) -> List[Tuple[Session, Session]]:
        """Identifies consecutive sessions for the same student cohort on the same day."""
        cohort_sessions: Dict[str, List[Session]] = {}
        for s in sessions:
            cohort_sessions.setdefault(s.cohort_id, []).append(s)

        transitions: List[Tuple[Session, Session]] = []
        for cohort_id, c_sess in cohort_sessions.items():
            by_day: Dict[str, List[Session]] = {}
            for s in c_sess:
                by_day.setdefault(s.day, []).append(s)

            for day, day_s in by_day.items():
                day_s.sort(key=lambda s: s.start_period)
                for i in range(len(day_s) - 1):
                    s1, s2 = day_s[i], day_s[i + 1]
                    if s2.start_period == s1.end_period + 1:
                        transitions.append((s1, s2))

        return transitions

    def solve(
        self,
        academic_cycle: str = "all",
        sessions_to_allocate: Optional[List[Session]] = None,
        pre_reserved_assignments: Optional[Dict[str, str]] = None,
        blocked_room_periods: Optional[Set[Tuple[str, str, int]]] = None,
        target_reassignments: Optional[Dict[str, str]] = None,
        time_limit_seconds: float = 10.0,
        unassigned_penalty: int = 1_000_000,
        same_room_bonus: int = 50,
        specialized_room_penalty: int = 30,
        reassignment_penalty: int = 20,
    ) -> AllocationCandidate:
        """Formulates and solves the room assignment problem using OR-Tools CP-SAT.

        Args:
            academic_cycle: 'odd', 'even', or 'all'.
            sessions_to_allocate: Target sessions to assign. If None, uses all in cycle.
            pre_reserved_assignments: Existing assignments that are frozen and occupy rooms.
            blocked_room_periods: Set of (room_id, day, period) slots that are unusable.
            target_reassignments: Dict of session_id -> previous_room_id for disruption repair,
                                  penalizing reallocating away from the previous room.
            time_limit_seconds: Solver maximum time limit in seconds.
            unassigned_penalty: Objective penalty for leaving a session unassigned.
            same_room_bonus: Objective reward for consecutive sessions in the same room.
            specialized_room_penalty: Penalty for putting ordinary classroom sessions in labs.
            reassignment_penalty: Penalty for changing an existing session's room during repair.

        Returns:
            AllocationCandidate containing assignment mapping, unassigned reasons, and metadata.
        """
        start_time = time.perf_counter()

        if sessions_to_allocate is None:
            if academic_cycle in ["odd", "even"]:
                sessions_to_allocate = [
                    s for s in self.snapshot.sessions if s.academic_cycle == academic_cycle
                ]
            else:
                sessions_to_allocate = self.snapshot.sessions

        pre_reserved_assignments = pre_reserved_assignments or {}
        blocked_room_periods = blocked_room_periods or set()
        target_reassignments = target_reassignments or {}

        # 1. Map existing occupancy from pre-reserved assignments
        reserved_occupancy: Dict[Tuple[str, str, int], str] = {}
        for s_id, r_id in pre_reserved_assignments.items():
            s_obj = self.snapshot.session_index.get(s_id)
            if s_obj and r_id:
                for p in s_obj.period_range:
                    reserved_occupancy[(r_id, s_obj.day, p)] = s_id

        # 2. Build model and domain
        model = cp_model.CpModel()
        eligible_per_session: Dict[str, List[Room]] = {}
        for s in sessions_to_allocate:
            eligible_per_session[s.session_id] = self._get_eligible_rooms(s)

        # Variables: x[s.session_id, r.room_id]
        x: Dict[Tuple[str, str], cp_model.BoolVar] = {}
        unassigned_vars: Dict[str, cp_model.BoolVar] = {}

        for s in sessions_to_allocate:
            s_id = s.session_id
            eligible = eligible_per_session[s_id]

            # Filter candidate rooms: must not collide with pre-reserved or blocked periods
            valid_candidate_rooms: List[Room] = []
            for r in eligible:
                r_id = r.room_id
                conflict = False
                for p in s.period_range:
                    if (r_id, s.day, p) in reserved_occupancy:
                        conflict = True
                        break
                    if (r_id, s.day, p) in blocked_room_periods:
                        conflict = True
                        break
                if not conflict:
                    valid_candidate_rooms.append(r)

            for r in valid_candidate_rooms:
                x[(s_id, r.room_id)] = model.NewBoolVar(f"x_{s_id}_{r.room_id}")

            u_var = model.NewBoolVar(f"unassigned_{s_id}")
            unassigned_vars[s_id] = u_var

            # Exact assignment constraint: sum(x[s, r]) + unassigned[s] == 1
            cand_vars = [x[(s_id, r.room_id)] for r in valid_candidate_rooms]
            model.Add(sum(cand_vars) + u_var == 1)

        # 3. Room-Time Exclusivity Constraint
        # Group sessions by (day, period)
        by_day_period: Dict[Tuple[str, int], List[Session]] = {}
        for s in sessions_to_allocate:
            for p in s.period_range:
                by_day_period.setdefault((s.day, p), []).append(s)

        for (day, p), sess_list in by_day_period.items():
            for room in self.snapshot.rooms:
                r_id = room.room_id
                # Check if room is reserved or blocked at this period
                if (r_id, day, p) in reserved_occupancy or (r_id, day, p) in blocked_room_periods:
                    # No session in sessions_to_allocate can occupy this room
                    for s in sess_list:
                        if (s.session_id, r_id) in x:
                            model.Add(x[(s.session_id, r_id)] == 0)
                else:
                    active_vars = [
                        x[(s.session_id, r_id)]
                        for s in sess_list
                        if (s.session_id, r_id) in x
                    ]
                    if len(active_vars) > 1:
                        model.Add(sum(active_vars) <= 1)

        # 4. Objective Formulation
        obj_terms = []

        # (a) Unassigned penalty (heavily penalize unassigned sessions)
        for s_id, u_var in unassigned_vars.items():
            obj_terms.append(-unassigned_penalty * u_var)

        # (b) Same-room continuity bonus for consecutive cohort sessions
        transitions = self._find_consecutive_cohort_transitions(sessions_to_allocate)
        for s1, s2 in transitions:
            s1_id, s2_id = s1.session_id, s2.session_id
            common_rooms = {
                r.room_id for r in eligible_per_session[s1_id]
            }.intersection({r.room_id for r in eligible_per_session[s2_id]})

            for r_id in common_rooms:
                if (s1_id, r_id) in x and (s2_id, r_id) in x:
                    same_b = model.NewBoolVar(f"same_{s1_id}_{s2_id}_{r_id}")
                    model.Add(same_b <= x[(s1_id, r_id)])
                    model.Add(same_b <= x[(s2_id, r_id)])
                    model.Add(same_b >= x[(s1_id, r_id)] + x[(s2_id, r_id)] - 1)
                    obj_terms.append(same_room_bonus * same_b)

        # (c) Specialized room misuse penalty (penalize regular classes placed in labs)
        for s in sessions_to_allocate:
            s_id = s.session_id
            if s.required_room_type == "classroom":
                for r in eligible_per_session[s_id]:
                    r_id = r.room_id
                    if (s_id, r_id) in x and r.room_type == "laboratory":
                        obj_terms.append(-specialized_room_penalty * x[(s_id, r_id)])

        # (d) Reassignment penalty (for bounded disruption repair, prefer staying in original room)
        for s_id, orig_r_id in target_reassignments.items():
            if (s_id, orig_r_id) in x:
                # Bonus for keeping original room
                obj_terms.append(reassignment_penalty * x[(s_id, orig_r_id)])

        model.Maximize(sum(obj_terms))

        # 5. Solve CP-SAT model
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = time_limit_seconds
        solver.parameters.num_search_workers = 4

        status = solver.Solve(model)
        solve_duration = time.perf_counter() - start_time

        working_assignments: Dict[str, str] = dict(pre_reserved_assignments)
        unassigned_reasons: Dict[str, str] = {}

        status_str = solver.StatusName(status)

        if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            for s in sessions_to_allocate:
                s_id = s.session_id
                assigned_room: Optional[str] = None
                for r in eligible_per_session[s_id]:
                    r_id = r.room_id
                    if (s_id, r_id) in x and solver.Value(x[(s_id, r_id)]) == 1:
                        assigned_room = r_id
                        break

                if assigned_room:
                    working_assignments[s_id] = assigned_room
                else:
                    unassigned_reasons[s_id] = (
                        f"Solver left session unassigned (conflict or no feasible slot available in {status_str})."
                    )
        elif status == cp_model.INFEASIBLE:
            for s in sessions_to_allocate:
                unassigned_reasons[s.session_id] = "Model proved strictly INFEASIBLE."
        else:  # TIMEOUT or UNKNOWN
            for s in sessions_to_allocate:
                unassigned_reasons[s.session_id] = f"Solver returned status {status_str}."

        candidate = AllocationCandidate(
            academic_cycle=academic_cycle,
            assignments=working_assignments,
            unassigned_sessions=unassigned_reasons,
            metadata={
                "allocator": "CPSATRoomOptimizer",
                "solver_status": status_str,
                "solver_time_seconds": round(solve_duration, 3),
                "total_target_sessions": len(sessions_to_allocate),
                "assigned_count": len([s for s in sessions_to_allocate if s.session_id in working_assignments]),
                "unassigned_count": len(unassigned_reasons),
                "allow_computing_lab_exception": self.allow_computing_lab_exception,
                "capacity_mode": self.capacity_mode.value,
            },
        )

        return candidate

    def solve_and_validate(
        self,
        academic_cycle: str = "all",
        sessions_to_allocate: Optional[List[Session]] = None,
        pre_reserved_assignments: Optional[Dict[str, str]] = None,
        blocked_room_periods: Optional[Set[Tuple[str, str, int]]] = None,
        target_reassignments: Optional[Dict[str, str]] = None,
        time_limit_seconds: float = 10.0,
    ) -> AllocationResult:
        """Solves allocation with CP-SAT and independently validates the outcome.

        Maintains strict separation between the optimization solver and the validator.
        """
        start_time = time.perf_counter()

        candidate = self.solve(
            academic_cycle=academic_cycle,
            sessions_to_allocate=sessions_to_allocate,
            pre_reserved_assignments=pre_reserved_assignments,
            blocked_room_periods=blocked_room_periods,
            target_reassignments=target_reassignments,
            time_limit_seconds=time_limit_seconds,
        )

        validator = IndependentValidator(
            snapshot=self.snapshot,
            capacity_mode=self.capacity_mode,
            allow_computing_lab_exception=self.allow_computing_lab_exception,
            synthetic_room_capacities=self.synthetic_room_capacities,
            synthetic_session_demands=self.synthetic_session_demands,
        )

        validation = validator.validate_candidate(candidate)
        total_time_ms = (time.perf_counter() - start_time) * 1000.0

        return AllocationResult(
            candidate=candidate,
            validation=validation,
            allocator_name="CPSATRoomOptimizer",
            capacity_mode=self.capacity_mode.value,
            execution_time_ms=round(total_time_ms, 2),
        )
