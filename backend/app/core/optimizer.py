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
from backend.app.services.travel_matrix import TravelMatrixService


class CPSATRoomOptimizer:
    """CP-SAT room allocator optimizing travel continuity and room suitability."""

    def __init__(
        self,
        snapshot: DatasetSnapshot,
        travel_service: Optional[TravelMatrixService] = None,
        allow_computing_lab_exception: bool = False,
        capacity_mode: CapacityPolicyMode = CapacityPolicyMode.FACTUAL,
        synthetic_room_capacities: Optional[Dict[str, int]] = None,
        synthetic_session_demands: Optional[Dict[str, int]] = None,
    ):
        """Initializes the optimizer with snapshot and evaluation configurations.

        Args:
            snapshot: Immutable dataset snapshot containing rooms and sessions.
            travel_service: TravelMatrixService instance for symmetric walking-time queries.
            allow_computing_lab_exception: Whether to allow the 10 computing lab sessions.
            capacity_mode: Factual vs Synthetic evaluation mode.
            synthetic_room_capacities: Optional synthetic room capacities.
            synthetic_session_demands: Optional synthetic cohort student demands.
        """
        self.snapshot = snapshot
        self.travel_service = travel_service or TravelMatrixService(
            snapshot.travel_times if snapshot.travel_times else None
        )
        self.allow_computing_lab_exception = allow_computing_lab_exception
        self.capacity_mode = capacity_mode
        self.synthetic_room_capacities = synthetic_room_capacities or {}
        self.synthetic_session_demands = synthetic_session_demands or {}
        self.rooms_by_id: Dict[str, Room] = snapshot.room_index
        self._travel_clusters: Optional[Dict[str, Tuple[str, ...]]] = None

    def _get_travel_clusters(self) -> Dict[str, Tuple[str, ...]]:
        """Groups snapshot rooms into clusters with travel time <= 3.0 min (same building)."""
        if self._travel_clusters is not None:
            return self._travel_clusters

        clusters: Dict[str, Tuple[str, ...]] = {}
        visited: Set[str] = set()
        for r in self.snapshot.rooms:
            rid = r.room_id
            if rid in visited:
                continue
            group = {rid}
            for r2 in self.snapshot.rooms:
                r2id = r2.room_id
                if r2id != rid:
                    try:
                        t = self.travel_service.get_travel_time(rid, r2id)
                        if t <= 3.0:
                            group.add(r2id)
                    except (KeyError, ValueError):
                        pass
            visited.update(group)
            gt = tuple(sorted(group))
            for m in group:
                clusters[m] = gt

        self._travel_clusters = clusters
        return self._travel_clusters

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
        walking_time_weight: int = 10,
        same_room_bonus: Optional[int] = None,
        specialized_room_penalty: int = 30,
        reassignment_penalty: int = 20,
        allow_slack: bool = False,
        warm_start_hints: Optional[Dict[str, str]] = None,
    ) -> AllocationCandidate:
        """Formulates and solves the room assignment problem using OR-Tools CP-SAT.

        Directly minimizes cohort walking time using TravelMatrixService:
        - 0.0 min (same room): 8.0 min savings vs 8.0 min max -> +80 points
        - 3.0 min (same building): 5.0 min savings vs 8.0 min max -> +50 points
        - 8.0 min (cross building): 0.0 min savings vs 8.0 min max -> +0 points
        Preserves hard feasibility as absolute priority. When allow_slack is False,
        exact assignment sum(x[s, r]) == 1 is enforced directly, eliminating 10^6
        penalty coefficients and slack variables for fast (<10s) solver convergence.

        Args:
            academic_cycle: 'odd', 'even', or 'all'.
            sessions_to_allocate: Target sessions to assign. If None, uses all in cycle.
            pre_reserved_assignments: Existing assignments that are frozen and occupy rooms.
            blocked_room_periods: Set of (room_id, day, period) slots that are unusable.
            target_reassignments: Dict of session_id -> previous_room_id for disruption repair,
                                  penalizing reallocating away from the previous room.
            time_limit_seconds: Solver maximum time limit in seconds (default: 10.0).
            unassigned_penalty: Objective penalty for leaving a session unassigned when allow_slack=True.
            walking_time_weight: Objective reward scaling per minute of walking-time reduction.
            same_room_bonus: Optional backward-compatibility parameter.
            specialized_room_penalty: Penalty for putting ordinary classroom sessions in labs.
            reassignment_penalty: Penalty for changing an existing session's room during repair.
            allow_slack: If False, enforces exact assignment as a hard constraint (fast).

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
        # Primal warm-start hint generation from baseline greedy allocator when not explicitly provided
        if not warm_start_hints and not pre_reserved_assignments and not blocked_room_periods:
            try:
                from backend.app.core.baseline_allocator import BaselineGreedyAllocator
                hint_alloc = BaselineGreedyAllocator(
                    snapshot=self.snapshot,
                    allow_computing_lab_exception=self.allow_computing_lab_exception,
                )
                hint_cand = hint_alloc.allocate(academic_cycle=academic_cycle)
                warm_start_hints = hint_cand.assignments
            except Exception:
                warm_start_hints = {}
        warm_start_hints = warm_start_hints or {}

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
                    if (r_id, s.day, p) in reserved_occupancy or (r_id, s.day, p) in blocked_room_periods:
                        conflict = True
                        break
                if not conflict:
                    valid_candidate_rooms.append(r)

            for r in valid_candidate_rooms:
                x[(s_id, r.room_id)] = model.NewBoolVar(f"x_{s_id}_{r.room_id}")

            cand_vars = [x[(s_id, r.room_id)] for r in valid_candidate_rooms]
            if allow_slack:
                u_var = model.NewBoolVar(f"unassigned_{s_id}")
                unassigned_vars[s_id] = u_var
                model.Add(sum(cand_vars) + u_var == 1)
            else:
                if cand_vars:
                    model.Add(sum(cand_vars) == 1)
                else:
                    # Genuinely no candidate room available: force infeasibility
                    dummy_infeasible = model.NewBoolVar(f"infeasible_{s_id}")
                    model.Add(dummy_infeasible == 1)
                    model.Add(dummy_infeasible == 0)

        # Apply primal warm-start hints
        for s_id, target_r_id in warm_start_hints.items():
            if (s_id, target_r_id) in x:
                model.AddHint(x[(s_id, target_r_id)], 1)

        # 3. Room-Time Exclusivity Constraint
        # Group sessions by (day, period)
        by_day_period: Dict[Tuple[str, int], List[Session]] = {}
        for s in sessions_to_allocate:
            for p in s.period_range:
                by_day_period.setdefault((s.day, p), []).append(s)

        for (day, p), sess_list in by_day_period.items():
            for room in self.snapshot.rooms:
                r_id = room.room_id
                if (r_id, day, p) not in reserved_occupancy and (r_id, day, p) not in blocked_room_periods:
                    active_vars = [
                        x[(s.session_id, r_id)]
                        for s in sess_list
                        if (s.session_id, r_id) in x
                    ]
                    if len(active_vars) > 1:
                        model.Add(sum(active_vars) <= 1)

        # 4. Objective Formulation
        obj_terms = []

        # (a) Unassigned penalty (only when allow_slack is enabled)
        if allow_slack:
            for s_id, u_var in unassigned_vars.items():
                obj_terms.append(-unassigned_penalty * u_var)

        # (b) Cohort walking-time objective based directly on TravelMatrixService
        all_eval_sessions = list(sessions_to_allocate)
        for r_sid in pre_reserved_assignments:
            s_obj = self.snapshot.session_index.get(r_sid)
            if s_obj and s_obj not in all_eval_sessions:
                all_eval_sessions.append(s_obj)

        transitions = self._find_consecutive_cohort_transitions(all_eval_sessions)
        travel_clusters = self._get_travel_clusters()
        multi_room_clusters = {c for c in travel_clusters.values() if len(c) > 1}

        for s1, s2 in transitions:
            s1_id, s2_id = s1.session_id, s2.session_id
            s1_fixed = pre_reserved_assignments.get(s1_id)
            s2_fixed = pre_reserved_assignments.get(s2_id)

            cand_s1 = [r.room_id for r in eligible_per_session.get(s1_id, []) if (s1_id, r.room_id) in x]
            cand_s2 = [r.room_id for r in eligible_per_session.get(s2_id, []) if (s2_id, r.room_id) in x]

            # Case A: s1 is pre-reserved, s2 is to allocate
            if s1_fixed and cand_s2:
                for r2_id in cand_s2:
                    try:
                        t = self.travel_service.get_travel_time(s1_fixed, r2_id)
                    except (KeyError, ValueError):
                        t = 8.0
                    savings = int(round((8.0 - t) * walking_time_weight))
                    if savings > 0:
                        obj_terms.append(savings * x[(s2_id, r2_id)])

            # Case B: s2 is pre-reserved, s1 is to allocate
            elif s2_fixed and cand_s1:
                for r1_id in cand_s1:
                    try:
                        t = self.travel_service.get_travel_time(r1_id, s2_fixed)
                    except (KeyError, ValueError):
                        t = 8.0
                    savings = int(round((8.0 - t) * walking_time_weight))
                    if savings > 0:
                        obj_terms.append(savings * x[(s1_id, r1_id)])

            # Case C: both s1 and s2 are to allocate
            elif cand_s1 and cand_s2:
                common_rooms = set(cand_s1).intersection(set(cand_s2))
                # For small candidate sets (e.g. unit tests, targeted disruption repair),
                # evaluate exact pairwise savings directly via self.travel_service
                if len(cand_s1) * len(cand_s2) <= 50:
                    for r1_id in cand_s1:
                        for r2_id in cand_s2:
                            try:
                                t = self.travel_service.get_travel_time(r1_id, r2_id)
                            except (KeyError, ValueError):
                                t = 8.0
                            savings = int(round((8.0 - t) * walking_time_weight))
                            if savings > 0:
                                p_var = model.NewBoolVar(f"travel_{s1_id}_{r1_id}_{s2_id}_{r2_id}")
                                model.Add(p_var <= x[(s1_id, r1_id)])
                                model.Add(p_var <= x[(s2_id, r2_id)])
                                obj_terms.append(savings * p_var)
                elif common_rooms:
                    # Same-room continuity bonus (+80 points: 8.0 min savings * 10)
                    for r_id in common_rooms:
                        same_b = model.NewBoolVar(f"same_r_{s1_id}_{s2_id}_{r_id}")
                        model.Add(same_b <= x[(s1_id, r_id)])
                        model.Add(same_b <= x[(s2_id, r_id)])
                        obj_terms.append(80 * same_b)
                else:
                    # Different room types (e.g. classroom to lab): same-cluster bonus (+50 points: 5.0 min savings * 10)
                    for cluster in multi_room_clusters:
                        c_rooms = set(cluster)
                        c1 = [r_id for r_id in cand_s1 if r_id in c_rooms]
                        c2 = [r_id for r_id in cand_s2 if r_id in c_rooms]
                        if c1 and c2:
                            u1 = sum(x[(s1_id, r_id)] for r_id in c1)
                            u2 = sum(x[(s2_id, r_id)] for r_id in c2)
                            same_c = model.NewBoolVar(f"same_c_{s1_id}_{s2_id}_{cluster[0]}")
                            model.Add(same_c <= u1)
                            model.Add(same_c <= u2)
                            obj_terms.append(50 * same_c)

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
                obj_terms.append(reassignment_penalty * x[(s_id, orig_r_id)])

        if obj_terms:
            model.Maximize(sum(obj_terms))

        # 5. Solve CP-SAT model
        model_build_time = time.perf_counter() - start_time

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = time_limit_seconds
        solver.parameters.num_search_workers = 4

        status = solver.Solve(model)
        solver_wall_time = solver.WallTime()
        total_duration = time.perf_counter() - start_time

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
                "solver_wall_time_seconds": round(solver_wall_time, 3),
                "model_construction_time_seconds": round(model_build_time, 3),
                "solver_time_seconds": round(total_duration, 3),
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
        allow_slack: bool = False,
        warm_start_hints: Optional[Dict[str, str]] = None,
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
            allow_slack=allow_slack,
            warm_start_hints=warm_start_hints,
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
