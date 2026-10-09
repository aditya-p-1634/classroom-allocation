"""Deterministic Baseline Greedy Allocator for ClassroomIQ.

Governed by Master Project Specification §9.1, Document 03 §8, and Document 05 Phase P5 authorization.
Implements the Most-Constrained-First greedy room-allocation strategy.
Keeps session cycle, day, periods, course, and cohort fixed.
"""

from typing import Dict, List, Optional, Set, Tuple, Any
from backend.app.schemas.models import DatasetSnapshot, Room, Session
from backend.app.schemas.validation import AllocationCandidate
from backend.app.core.validator import COMPUTING_LAB_ANOMALY_SESSION_IDS


class BaselineGreedyAllocator:
    """Deterministic, most-constrained-first greedy room allocator."""

    def __init__(
        self,
        snapshot: DatasetSnapshot,
        allow_computing_lab_exception: bool = False,
    ):
        """Initializes the baseline allocator.
        
        Args:
            snapshot: Immutable dataset snapshot containing rooms and sessions.
            allow_computing_lab_exception: Whether to allow the narrow exception for the 10
                                           computing/capstone sessions in software labs.
        """
        self.snapshot = snapshot
        self.allow_computing_lab_exception = allow_computing_lab_exception
        self.rooms_by_id: Dict[str, Room] = snapshot.room_index

    def _get_eligible_rooms(self, session: Session) -> List[Room]:
        """Finds all rooms whose capabilities satisfy the session's requirements."""
        req_type = session.required_room_type
        eligible: List[Room] = []

        for room in sorted(self.snapshot.rooms, key=lambda r: r.room_id):
            if req_type in room.permitted_uses:
                eligible.append(room)
            elif (
                self.allow_computing_lab_exception
                and session.session_id in COMPUTING_LAB_ANOMALY_SESSION_IDS
                and room.room_type == "laboratory"
            ):
                eligible.append(room)

        return eligible

    def allocate(
        self,
        academic_cycle: str = "all",
        sessions_to_allocate: Optional[List[Session]] = None,
        pre_reserved_assignments: Optional[Dict[str, str]] = None,
    ) -> AllocationCandidate:
        """Executes deterministic room allocation on the specified sessions.
        
        Args:
            academic_cycle: 'odd', 'even', or 'all'.
            sessions_to_allocate: Explicit list of sessions to allocate. If None,
                                  selects all sessions matching academic_cycle.
            pre_reserved_assignments: Optional initial assignments for sessions that remain
                                       reserved (not being reallocated).
                                       
        Returns:
            AllocationCandidate containing assignment mapping and unassigned reasons.
        """
        if sessions_to_allocate is None:
            if academic_cycle in ["odd", "even"]:
                sessions_to_allocate = [
                    s for s in self.snapshot.sessions
                    if s.academic_cycle == academic_cycle
                ]
            else:
                sessions_to_allocate = self.snapshot.sessions

        # Working occupancy state: (room_id, cycle, day, period) -> session_id
        working_occupancy: Dict[Tuple[str, str, str, int], str] = {}
        working_assignments: Dict[str, str] = {}
        unassigned_reasons: Dict[str, str] = {}

        # 1. Apply pre-reserved assignments if provided (sessions outside the reallocation scope)
        if pre_reserved_assignments:
            all_sessions_map = self.snapshot.session_index
            for s_id, r_id in pre_reserved_assignments.items():
                if s_id in all_sessions_map and r_id:
                    s_res = all_sessions_map[s_id]
                    working_assignments[s_id] = r_id
                    for p in s_res.period_range:
                        working_occupancy[(r_id, s_res.academic_cycle, s_res.day, p)] = s_id

        # 2. Compute candidate domains for all target sessions
        session_domains: List[Tuple[Session, List[Room]]] = []
        for s in sessions_to_allocate:
            eligible = self._get_eligible_rooms(s)
            session_domains.append((s, eligible))

        # 3. Sort sessions deterministically using Most-Constrained-First:
        #    Primary: domain size ascending (fewest eligible rooms first)
        #    Secondary: duration periods descending (multi-period sessions first)
        #    Tertiary: session_id ascending (lexicographical stability)
        def sort_key(item: Tuple[Session, List[Room]]) -> Tuple[int, int, str]:
            sess, elig = item
            return (len(elig), -sess.duration_periods, sess.session_id)

        session_domains.sort(key=sort_key)

        # 4. Greedily assign compatible rooms
        for session, eligible_rooms in session_domains:
            if not eligible_rooms:
                unassigned_reasons[session.session_id] = (
                    f"No compatible rooms exist for required room type '{session.required_room_type}'."
                )
                continue

            assigned_room_id: Optional[str] = None

            # Sort eligible rooms deterministically by room_id ascending
            for candidate_room in sorted(eligible_rooms, key=lambda r: r.room_id):
                r_id = candidate_room.room_id
                cyc = session.academic_cycle
                day = session.day

                # Check room availability across all periods of the session
                can_fit = True
                for p in session.period_range:
                    slot_key = (r_id, cyc, day, p)
                    if slot_key in working_occupancy:
                        can_fit = False
                        break

                if can_fit:
                    assigned_room_id = r_id
                    break

            if assigned_room_id:
                working_assignments[session.session_id] = assigned_room_id
                for p in session.period_range:
                    working_occupancy[(assigned_room_id, session.academic_cycle, session.day, p)] = session.session_id
            else:
                unassigned_reasons[session.session_id] = (
                    f"All {len(eligible_rooms)} compatible rooms conflict on {session.day} "
                    f"Periods {session.start_period}-{session.end_period}."
                )

        # Build candidate output
        return AllocationCandidate(
            academic_cycle=academic_cycle,
            assignments=working_assignments,
            unassigned_sessions=unassigned_reasons,
            metadata={
                "allocator": "BaselineGreedyAllocator",
                "strategy": "most_constrained_first",
                "total_sessions_to_allocate": len(sessions_to_allocate),
                "assigned_count": len([s for s in sessions_to_allocate if s.session_id in working_assignments]),
                "unassigned_count": len(unassigned_reasons),
                "allow_computing_lab_exception": self.allow_computing_lab_exception,
            },
        )
