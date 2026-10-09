"""Independent Allocation Validator for ClassroomIQ.

Governed by Master Project Specification §9.2, Document 02 §8.3, Document 03 §9,
and Document 05 Phase P5 authorization.

This is a strictly standalone, pure-verification component. It does NOT import
or reuse allocator logic to decide validity. It evaluates candidate room assignments
against immutable domain snapshots and returns truthful, structured findings.
"""

from collections import defaultdict
from typing import Dict, List, Optional, Set, Any

from backend.app.config import CapacityPolicyMode
from backend.app.schemas.models import DatasetSnapshot, Room, Session
from backend.app.schemas.validation import (
    ConstraintCategory,
    FindingStatus,
    ValidationSeverity,
    ValidationFinding,
    AllocationStatus,
    ValidationSummary,
    AllocationCandidate,
)

# The 10 known computing/capstone session IDs assigned to laboratories in the source timetable
COMPUTING_LAB_ANOMALY_SESSION_IDS: Set[str] = {
    "SSN00447", "SSN00456", "SSN00475", "SSN00484", "SSN00503",
    "SSN00512", "SSN00531", "SSN00540", "SSN00833", "SSN00853",
}


class IndependentValidator:
    """Independent validator checking candidate allocations against documented hard constraints."""

    def __init__(
        self,
        snapshot: DatasetSnapshot,
        capacity_mode: CapacityPolicyMode = CapacityPolicyMode.FACTUAL,
        allow_computing_lab_exception: bool = False,
        synthetic_room_capacities: Optional[Dict[str, int]] = None,
        synthetic_session_demands: Optional[Dict[str, int]] = None,
    ):
        """Initializes the validator with immutable reference data.
        
        Args:
            snapshot: Immutable dataset snapshot containing rooms, sessions, and availability.
            capacity_mode: FACTUAL (pure source data) or SYNTHETIC_EVALUATION.
            allow_computing_lab_exception: If True, enables the narrow exception for the 10
                                           computing/capstone sessions in software labs.
                                           If False (default), flags them as capability mismatches.
            synthetic_room_capacities: Explicit test-fixture room capacities for evaluation mode.
            synthetic_session_demands: Explicit test-fixture session student counts for evaluation mode.
        """
        self.snapshot = snapshot
        self.capacity_mode = capacity_mode
        self.allow_computing_lab_exception = allow_computing_lab_exception
        self.synthetic_room_capacities = synthetic_room_capacities or {}
        self.synthetic_session_demands = synthetic_session_demands or {}

        # Quick index lookups
        self.rooms_by_id: Dict[str, Room] = snapshot.room_index
        self.sessions_by_id: Dict[str, Session] = snapshot.session_index

    def validate_candidate(
        self,
        candidate: AllocationCandidate,
        sessions_to_verify: Optional[List[Session]] = None,
    ) -> ValidationSummary:
        """Independently evaluates an allocation candidate.
        
        Args:
            candidate: Proposed assignment mapping (session_id -> room_id).
            sessions_to_verify: Subset of sessions to evaluate. If None, uses all sessions
                                matching the candidate's academic_cycle (or all sessions).
                                
        Returns:
            ValidationSummary containing complete diagnostic findings and outcome status.
        """
        if sessions_to_verify is None:
            if candidate.academic_cycle in ["odd", "even"]:
                sessions_to_verify = [
                    s for s in self.snapshot.sessions
                    if s.academic_cycle == candidate.academic_cycle
                ]
            else:
                sessions_to_verify = self.snapshot.sessions

        findings: List[ValidationFinding] = []
        evidence_limitations: List[str] = []

        # 1. Evaluate Room-Time Exclusivity
        self._check_room_time_exclusivity(candidate, sessions_to_verify, findings)

        # 2. Evaluate Cohort-Time Exclusivity
        self._check_cohort_time_exclusivity(candidate, sessions_to_verify, findings)

        # 3. Evaluate Room Capability Compatibility
        self._check_room_capability(candidate, sessions_to_verify, findings)

        # 4. Evaluate Availability Semantics
        self._check_availability(candidate, sessions_to_verify, findings, evidence_limitations)

        # 5. Evaluate Capacity Feasibility
        self._check_capacity(candidate, sessions_to_verify, findings, evidence_limitations)

        # Compute summary metrics
        pass_count = sum(1 for f in findings if f.status == FindingStatus.PASS)
        fail_count = sum(1 for f in findings if f.status == FindingStatus.FAIL)
        insufficient_count = sum(1 for f in findings if f.status == FindingStatus.INSUFFICIENT_EVIDENCE)

        total_sessions = len(sessions_to_verify)
        assigned_count = sum(
            1 for s in sessions_to_verify
            if s.session_id in candidate.assignments and candidate.assignments[s.session_id]
        )
        unassigned_count = total_sessions - assigned_count

        is_valid = (fail_count == 0)
        is_complete = (unassigned_count == 0)

        # Determine truthful status taxonomy
        if not is_valid:
            status = AllocationStatus.INVALID
        elif not is_complete:
            status = AllocationStatus.VALID_PARTIAL
        else:
            status = AllocationStatus.VALID_COMPLETE

        return ValidationSummary(
            status=status,
            is_valid=is_valid,
            is_complete=is_complete,
            total_sessions_checked=total_sessions,
            assigned_sessions_count=assigned_count,
            unassigned_sessions_count=unassigned_count,
            pass_count=pass_count,
            fail_count=fail_count,
            insufficient_evidence_count=insufficient_count,
            findings=findings,
            evidence_limitations=evidence_limitations,
        )

    def _check_room_time_exclusivity(
        self,
        candidate: AllocationCandidate,
        sessions: List[Session],
        findings: List[ValidationFinding],
    ) -> None:
        """Constraint A: No two sessions may occupy the same room during overlapping periods."""
        # Key: (room_id, academic_cycle, day, period) -> List[session_id]
        room_occupancy: Dict[tuple, List[str]] = defaultdict(list)

        for s in sessions:
            room_id = candidate.assignments.get(s.session_id)
            if not room_id:
                continue

            for p in s.period_range:
                key = (room_id, s.academic_cycle, s.day, p)
                room_occupancy[key].append(s.session_id)

        # Identify collisions
        for (room_id, cycle, day, period), session_ids in room_occupancy.items():
            if len(session_ids) > 1:
                findings.append(
                    ValidationFinding(
                        constraint=ConstraintCategory.ROOM_TIME_EXCLUSIVITY,
                        status=FindingStatus.FAIL,
                        severity=ValidationSeverity.ERROR,
                        room_id=room_id,
                        academic_cycle=cycle,
                        day=day,
                        period=period,
                        message=(
                            f"Room double-booking collision in room '{room_id}' during cycle '{cycle}', "
                            f"{day} Period {period} between sessions: {session_ids}."
                        ),
                        evidence={"conflicting_session_ids": session_ids, "period": period},
                    )
                )

    def _check_cohort_time_exclusivity(
        self,
        candidate: AllocationCandidate,
        sessions: List[Session],
        findings: List[ValidationFinding],
    ) -> None:
        """Constraint B: A cohort must not be scheduled into overlapping sessions."""
        # Key: (cohort_id, academic_cycle, day, period) -> List[session_id]
        cohort_occupancy: Dict[tuple, List[str]] = defaultdict(list)

        for s in sessions:
            room_id = candidate.assignments.get(s.session_id)
            if not room_id:
                continue

            for p in s.period_range:
                key = (s.cohort_id, s.academic_cycle, s.day, p)
                cohort_occupancy[key].append(s.session_id)

        for (cohort_id, cycle, day, period), session_ids in cohort_occupancy.items():
            if len(session_ids) > 1:
                findings.append(
                    ValidationFinding(
                        constraint=ConstraintCategory.COHORT_TIME_EXCLUSIVITY,
                        status=FindingStatus.FAIL,
                        severity=ValidationSeverity.ERROR,
                        academic_cycle=cycle,
                        day=day,
                        period=period,
                        message=(
                            f"Cohort collision for cohort '{cohort_id}' during cycle '{cycle}', "
                            f"{day} Period {period} across sessions: {session_ids}."
                        ),
                        evidence={"cohort_id": cohort_id, "conflicting_sessions": session_ids},
                    )
                )

    def _check_room_capability(
        self,
        candidate: AllocationCandidate,
        sessions: List[Session],
        findings: List[ValidationFinding],
    ) -> None:
        """Constraint C: Room must satisfy session's required type or approved additional use."""
        for s in sessions:
            room_id = candidate.assignments.get(s.session_id)
            if not room_id:
                continue

            room = self.rooms_by_id.get(room_id)
            if not room:
                findings.append(
                    ValidationFinding(
                        constraint=ConstraintCategory.ROOM_CAPABILITY,
                        status=FindingStatus.FAIL,
                        severity=ValidationSeverity.ERROR,
                        session_id=s.session_id,
                        room_id=room_id,
                        message=f"Assigned room '{room_id}' does not exist in rooms inventory.",
                        evidence={"session_id": s.session_id, "assigned_room_id": room_id},
                    )
                )
                continue

            required = s.required_room_type
            permitted = room.permitted_uses

            # Direct or secondary permitted capability match
            if required in permitted:
                findings.append(
                    ValidationFinding(
                        constraint=ConstraintCategory.ROOM_CAPABILITY,
                        status=FindingStatus.PASS,
                        severity=ValidationSeverity.INFO,
                        session_id=s.session_id,
                        room_id=room_id,
                        message=(
                            f"Room '{room_id}' satisfies requirement '{required}' "
                            f"(permitted: {permitted})."
                        ),
                        evidence={"required": required, "permitted_uses": permitted},
                    )
                )
            elif (
                self.allow_computing_lab_exception
                and s.session_id in COMPUTING_LAB_ANOMALY_SESSION_IDS
                and room.room_type == "laboratory"
            ):
                # Narrow, explicitly configured exception for the 10 known computing sessions
                findings.append(
                    ValidationFinding(
                        constraint=ConstraintCategory.ROOM_CAPABILITY,
                        status=FindingStatus.PASS,
                        severity=ValidationSeverity.WARNING,
                        session_id=s.session_id,
                        room_id=room_id,
                        message=(
                            f"Approved narrow exception: Session '{s.session_id}' ({s.course}) "
                            f"requires '{required}', assigned to software laboratory '{room_id}'."
                        ),
                        evidence={
                            "exception": "narrow_computing_lab_exception",
                            "course": s.course,
                            "room_type": room.room_type,
                        },
                    )
                )
            else:
                # Discrepancy violation
                findings.append(
                    ValidationFinding(
                        constraint=ConstraintCategory.ROOM_CAPABILITY,
                        status=FindingStatus.FAIL,
                        severity=ValidationSeverity.ERROR,
                        session_id=s.session_id,
                        room_id=room_id,
                        message=(
                            f"Room capability mismatch: Session '{s.session_id}' ({s.course}) "
                            f"requires '{required}', but room '{room_id}' is '{room.room_type}' "
                            f"(permitted: {permitted})."
                        ),
                        evidence={
                            "required": required,
                            "room_type": room.room_type,
                            "permitted": permitted,
                            "is_known_anomaly": s.session_id in COMPUTING_LAB_ANOMALY_SESSION_IDS,
                        },
                    )
                )

    def _check_availability(
        self,
        candidate: AllocationCandidate,
        sessions: List[Session],
        findings: List[ValidationFinding],
        limitations: List[str],
    ) -> None:
        """Constraint D: Validates against source availability status semantics."""
        # Index source availability: (room_id, cycle, day, period) -> AvailabilityRecord
        avail_index = {
            (a.room_id, a.academic_cycle, a.day, a.period): a
            for a in self.snapshot.availability
        }

        unconfirmed_slots_used = 0
        unknown_hall_slots_used = 0

        for s in sessions:
            room_id = candidate.assignments.get(s.session_id)
            if not room_id:
                continue

            for p in s.period_range:
                key = (room_id, s.academic_cycle, s.day, p)
                rec = avail_index.get(key)
                if rec:
                    if rec.status == "unknown":
                        unknown_hall_slots_used += 1
                    elif rec.status == "not_scheduled_in_provided_timetable":
                        unconfirmed_slots_used += 1

        if unconfirmed_slots_used > 0:
            limitations.append(
                f"{unconfirmed_slots_used} session period-slots assigned to rooms at times marked "
                f"'not_scheduled_in_provided_timetable'; treated as unconfirmed candidate slots, "
                f"not verified free."
            )
        if unknown_hall_slots_used > 0:
            limitations.append(
                f"{unknown_hall_slots_used} session period-slots assigned to rooms with status 'unknown'."
            )

    def _check_capacity(
        self,
        candidate: AllocationCandidate,
        sessions: List[Session],
        findings: List[ValidationFinding],
        limitations: List[str],
    ) -> None:
        """Constraint E: Checks seating capacity under Factual vs Synthetic mode."""
        if self.capacity_mode == CapacityPolicyMode.FACTUAL:
            # Factual mode: missing capacities must be recorded as insufficient evidence
            unverified_capacity_count = 0
            for s in sessions:
                room_id = candidate.assignments.get(s.session_id)
                if not room_id:
                    continue

                room = self.rooms_by_id.get(room_id)
                if not room or room.capacity is None or s.student_count is None:
                    unverified_capacity_count += 1
                    findings.append(
                        ValidationFinding(
                            constraint=ConstraintCategory.CAPACITY,
                            status=FindingStatus.INSUFFICIENT_EVIDENCE,
                            severity=ValidationSeverity.WARNING,
                            session_id=s.session_id,
                            room_id=room_id,
                            message=(
                                f"Factual capacity check unverified for session '{s.session_id}' "
                                f"in room '{room_id}': student_count={s.student_count}, "
                                f"room_capacity={room.capacity if room else None}."
                            ),
                            evidence={
                                "student_count": s.student_count,
                                "room_capacity": room.capacity if room else None,
                            },
                        )
                    )
                else:
                    # Both known factually
                    if s.student_count <= room.capacity:
                        findings.append(
                            ValidationFinding(
                                constraint=ConstraintCategory.CAPACITY,
                                status=FindingStatus.PASS,
                                severity=ValidationSeverity.INFO,
                                session_id=s.session_id,
                                room_id=room_id,
                                message=f"Capacity verified: {s.student_count} <= {room.capacity}.",
                                evidence={"student_count": s.student_count, "capacity": room.capacity},
                            )
                        )
                    else:
                        findings.append(
                            ValidationFinding(
                                constraint=ConstraintCategory.CAPACITY,
                                status=FindingStatus.FAIL,
                                severity=ValidationSeverity.ERROR,
                                session_id=s.session_id,
                                room_id=room_id,
                                message=f"Capacity overflow: {s.student_count} > {room.capacity}.",
                                evidence={"student_count": s.student_count, "capacity": room.capacity},
                            )
                        )

            if unverified_capacity_count > 0:
                limitations.append(
                    f"Factual Mode: Capacity feasibility unverified for {unverified_capacity_count} "
                    f"assigned sessions due to missing source student counts or room capacities."
                )

        elif self.capacity_mode == CapacityPolicyMode.SYNTHETIC_EVALUATION:
            # Synthetic evaluation mode using explicitly labeled test-fixture profile
            for s in sessions:
                room_id = candidate.assignments.get(s.session_id)
                if not room_id:
                    continue

                demand = self.synthetic_session_demands.get(s.session_id)
                room = self.rooms_by_id.get(room_id)
                cap = self.synthetic_room_capacities.get(room_id, room.capacity if room else None)

                if demand is not None and cap is not None:
                    if demand <= cap:
                        findings.append(
                            ValidationFinding(
                                constraint=ConstraintCategory.CAPACITY,
                                status=FindingStatus.PASS,
                                severity=ValidationSeverity.INFO,
                                session_id=s.session_id,
                                room_id=room_id,
                                message=f"Synthetic capacity verified: {demand} <= {cap}.",
                                evidence={"synthetic_demand": demand, "synthetic_capacity": cap},
                            )
                        )
                    else:
                        findings.append(
                            ValidationFinding(
                                constraint=ConstraintCategory.CAPACITY,
                                status=FindingStatus.FAIL,
                                severity=ValidationSeverity.ERROR,
                                session_id=s.session_id,
                                room_id=room_id,
                                message=f"Synthetic capacity overflow: {demand} > {cap}.",
                                evidence={"synthetic_demand": demand, "synthetic_capacity": cap},
                            )
                        )
                else:
                    findings.append(
                        ValidationFinding(
                            constraint=ConstraintCategory.CAPACITY,
                            status=FindingStatus.INSUFFICIENT_EVIDENCE,
                            severity=ValidationSeverity.WARNING,
                            session_id=s.session_id,
                            room_id=room_id,
                            message="Synthetic capacity fixture values missing for evaluation.",
                            evidence={"synthetic_demand": demand, "synthetic_capacity": cap},
                        )
                    )
