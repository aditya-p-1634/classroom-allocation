"""Joint Multi-Program Room Allocation Service for ClassroomIQ.

Governed by Document 05 revision v0.2.6 and PAR-CIQ-P7-ADDENDUM-01.
Orchestrates joint allocation of uploaded multi-timetable sessions across a shared
room inventory, reusing P5 BaselineGreedyAllocator, P6 CPSATRoomOptimizer,
IndependentValidator, and MetricsCalculator with baseline-protection fallback.
"""

from typing import Dict, List, Optional, Any, Set, Tuple
from collections import defaultdict

from backend.app.config import CapacityPolicyMode
from backend.app.schemas.models import DatasetSnapshot, Room, Session
from backend.app.schemas.validation import (
    AllocationCandidate,
    ValidationSummary,
    ConstraintCategory,
    FindingStatus,
)
from backend.app.schemas.upload import (
    UploadAllocationRequest,
    UploadAllocationResponse,
    UploadTimetableResponse,
)
from backend.app.services.data_loader import DataLoaderService
from backend.app.services.upload_service import UploadService, UploadRunContext
from backend.app.services.synthetic_profile import SyntheticProfileService
from backend.app.services.travel_matrix import TravelMatrixService
from backend.app.core.baseline_allocator import BaselineGreedyAllocator
from backend.app.core.optimizer import CPSATRoomOptimizer
from backend.app.core.validator import IndependentValidator
from backend.app.core.metrics import MetricsCalculator


class JointAllocationService:
    """Coordinates joint multi-program room allocation on validated upload runs."""

    def __init__(self, snapshot: Optional[DatasetSnapshot] = None):
        """Initializes with domain reference data."""
        self.snapshot = snapshot or DataLoaderService().load_snapshot()

    def run_joint_allocation(self, req: UploadAllocationRequest) -> UploadAllocationResponse:
        """Executes joint baseline allocation and CP-SAT optimization on all uploaded files."""
        context = UploadService.get_run_context(req.run_id)
        if not context:
            raise KeyError(f"Upload run ID '{req.run_id}' not found or session expired.")

        domain_sessions = UploadService.to_session_models(context.normalized_sessions)
        if not domain_sessions:
            raise ValueError(f"Upload run '{req.run_id}' contains no valid sessions to allocate.")

        # Resolve evaluation mode
        is_synthetic = (req.evaluation_mode == "synthetic")
        capacity_mode = CapacityPolicyMode.SYNTHETIC_EVALUATION if is_synthetic else CapacityPolicyMode.FACTUAL

        syn_caps: Optional[Dict[str, int]] = None
        syn_demands: Optional[Dict[str, int]] = None
        if is_synthetic:
            syn_caps = SyntheticProfileService.build_synthetic_room_capacities_map(self.snapshot)
            syn_demands = {}
            for s in domain_sessions:
                if s.student_count is not None and s.student_count > 0:
                    syn_demands[s.session_id] = s.student_count
                else:
                    syn_demands[s.session_id] = SyntheticProfileService.get_synthetic_session_demand(s)

        # Build clean isolated snapshot for the joint upload run
        # NOTE: availability is empty so historical seed timetable occupancy does not block fresh uploads
        upload_snapshot = DatasetSnapshot(
            rooms=self.snapshot.rooms,
            sessions=domain_sessions,
            facilities=self.snapshot.facilities,
            availability=[],
            travel_times=self.snapshot.travel_times,
            events=self.snapshot.events,
            complaints=self.snapshot.complaints,
            report=self.snapshot.report,
        )

        # 1. Run Joint Greedy Baseline Allocation
        baseline_allocator = BaselineGreedyAllocator(
            snapshot=upload_snapshot,
            allow_computing_lab_exception=req.allow_computing_lab_exception,
        )
        baseline_candidate = baseline_allocator.allocate(
            academic_cycle=context.academic_cycle,
            sessions_to_allocate=domain_sessions,
        )

        base_validator = IndependentValidator(
            snapshot=upload_snapshot,
            capacity_mode=capacity_mode,
            allow_computing_lab_exception=req.allow_computing_lab_exception,
            synthetic_room_capacities=syn_caps,
            synthetic_session_demands=syn_demands,
        )
        base_validation = base_validator.validate_candidate(baseline_candidate, sessions_to_verify=domain_sessions)

        calc = MetricsCalculator(upload_snapshot)
        base_metrics = calc.calculate_metrics(
            candidate=baseline_candidate,
            allocator_name="BaselineGreedyAllocator_JointUpload",
            evaluation_mode=req.evaluation_mode,
            synthetic_room_capacities=syn_caps,
            synthetic_session_demands=syn_demands,
            execution_time_ms=0.0,
        )

        # 2. Run Joint CP-SAT Mathematical Optimization
        optimizer = CPSATRoomOptimizer(
            snapshot=upload_snapshot,
            travel_service=TravelMatrixService(self.snapshot.travel_times),
            allow_computing_lab_exception=req.allow_computing_lab_exception,
            capacity_mode=capacity_mode,
            synthetic_room_capacities=syn_caps,
            synthetic_session_demands=syn_demands,
        )
        opt_candidate = optimizer.solve(
            academic_cycle=context.academic_cycle,
            sessions_to_allocate=domain_sessions,
            time_limit_seconds=req.time_limit_seconds,
            warm_start_hints=baseline_candidate.assignments if base_validation.is_valid else None,
        )

        opt_validator = IndependentValidator(
            snapshot=upload_snapshot,
            capacity_mode=capacity_mode,
            allow_computing_lab_exception=req.allow_computing_lab_exception,
            synthetic_room_capacities=syn_caps,
            synthetic_session_demands=syn_demands,
        )
        opt_validation = opt_validator.validate_candidate(opt_candidate, sessions_to_verify=domain_sessions)

        opt_metrics = calc.calculate_metrics(
            candidate=opt_candidate,
            allocator_name="CPSATRoomOptimizer_JointUpload",
            evaluation_mode=req.evaluation_mode,
            synthetic_room_capacities=syn_caps,
            synthetic_session_demands=syn_demands,
            execution_time_ms=0.0,
        )

        # 3. Preserve Baseline-Protection Fallback
        is_base_valid = base_validation.is_valid and base_validation.is_complete
        is_opt_valid = opt_validation.is_valid and opt_validation.is_complete

        fallback_to_baseline = False
        selected_candidate = opt_candidate
        selected_validation = opt_validation
        selected_metrics = opt_metrics
        selected_allocator = "CPSATRoomOptimizer"

        if is_base_valid:
            # If optimizer candidate is invalid or regresses on walking time, safely fall back to baseline
            if not is_opt_valid or opt_metrics.total_walking_time_minutes > base_metrics.total_walking_time_minutes:
                fallback_to_baseline = True
                selected_candidate = baseline_candidate
                selected_validation = base_validation
                selected_metrics = base_metrics
                selected_allocator = "BaselineGreedyAllocator_Retained"
        else:
            # Baseline itself was incomplete or invalid
            if not is_opt_valid:
                selected_allocator = "InfeasibleCandidate"

        # 4. Check for Infeasibility Diagnostics
        infeasibility_diagnosis: Optional[str] = None
        unassigned_ids: List[str] = [
            s.session_id for s in domain_sessions
            if s.session_id not in selected_candidate.assignments or not selected_candidate.assignments[s.session_id]
        ]

        if unassigned_ids:
            # Analyze why sessions could not be placed
            slot_demand: Dict[Tuple[str, int, str], int] = defaultdict(int)
            for s in domain_sessions:
                for p in s.period_range:
                    slot_demand[(s.day, p, s.required_room_type)] += 1

            # Count physical rooms by capability
            room_cap_counts: Dict[str, int] = defaultdict(int)
            for r in self.snapshot.rooms:
                for u in r.permitted_uses:
                    room_cap_counts[u] += 1

            conflict_details = []
            for (day, p, r_type), count in slot_demand.items():
                available_rooms = room_cap_counts.get(r_type, 0)
                if count > available_rooms:
                    conflict_details.append(
                        f"on {day} period {p}: {count} concurrent '{r_type}' demands vs {available_rooms} physical rooms"
                    )

            if conflict_details:
                diag_summary = "; ".join(conflict_details[:3])
                infeasibility_diagnosis = (
                    f"Infeasible scenario: Physical room capacity exceeded ({diag_summary}). "
                    f"{len(unassigned_ids)} session occurrences could not be allocated."
                )
            else:
                infeasibility_diagnosis = (
                    f"Infeasible scenario under active constraints. {len(unassigned_ids)} session occurrences could not be allocated."
                )

        # Factual Mode evidence disclosure
        validation_dict = selected_validation.model_dump()
        if not is_synthetic:
            validation_dict["evidence_limitations"].append(
                "Factual Mode: Physical room operational availability records are unverified for fresh upload occurrences."
            )
            validation_dict["evidence_limitations"].append(
                "Factual Mode: Seating capacities and student enrollments evaluated strictly from source records without synthetic defaults."
            )

        # 5. Persist Selected Assignments in Context
        context.allocated_assignments = selected_candidate.assignments
        context.allocation_result = {
            "selected_allocator": selected_allocator,
            "fallback_to_baseline": fallback_to_baseline,
            "candidate": selected_candidate,
            "baseline_candidate": baseline_candidate,
            "validation": validation_dict,
            "metrics": selected_metrics,
            "baseline_metrics": base_metrics,
            "evaluation_mode": req.evaluation_mode,
            "infeasibility_diagnosis": infeasibility_diagnosis,
            "unassigned_session_ids": unassigned_ids,
        }

        # Calculate walking time metrics
        base_wt = base_metrics.total_walking_time_minutes
        opt_wt = selected_metrics.total_walking_time_minutes
        savings_min = max(0.0, base_wt - opt_wt) if not fallback_to_baseline else 0.0
        savings_pct = (savings_min / base_wt * 100.0) if base_wt > 0 and not fallback_to_baseline else 0.0

        status_val = "infeasible" if unassigned_ids else ("fallback" if fallback_to_baseline else "completed")

        return UploadAllocationResponse(
            run_id=req.run_id,
            academic_cycle=context.academic_cycle,
            status=status_val,
            selected_allocator=selected_allocator,
            fallback_to_baseline=fallback_to_baseline,
            total_sessions=len(domain_sessions),
            assigned_count=len(domain_sessions) - len(unassigned_ids),
            unassigned_count=len(unassigned_ids),
            baseline_walking_time=round(base_wt, 2),
            optimized_walking_time=round(opt_wt, 2),
            walking_time_reduction_minutes=round(savings_min, 2),
            walking_time_reduction_percentage=round(savings_pct, 2),
            validation=validation_dict,
            infeasibility_diagnosis=infeasibility_diagnosis,
            unassigned_session_ids=unassigned_ids,
            evaluation_mode=req.evaluation_mode,
            evaluation_mode_label="SYNTHETIC DEMO PROFILE" if is_synthetic else "FACTUAL MODE",
            assignments_count=len(selected_candidate.assignments),
        )

    def get_upload_timetable_grid(
        self,
        run_id: str,
        day: Optional[str] = "Monday",
        group_by: str = "cohort",
        program: Optional[str] = None,
        cohort_id: Optional[str] = None,
        room_id: Optional[str] = None,
    ) -> UploadTimetableResponse:
        """Constructs an interactive weekly timetable grid for a specific upload run."""
        context = UploadService.get_run_context(run_id)
        if not context:
            raise KeyError(f"Upload run ID '{run_id}' not found or session expired.")

        assignments = context.allocated_assignments
        domain_sessions = UploadService.to_session_models(context.normalized_sessions)

        alloc_result = context.allocation_result or {}
        is_fallback = alloc_result.get("fallback_to_baseline", False)
        eval_mode = alloc_result.get("evaluation_mode", "synthetic")

        if is_fallback:
            status_label = "Selected Allocation: Safe Fallback — Valid Baseline Retained"
            alloc_source = "baseline"
        elif alloc_result.get("selected_allocator") == "CPSATRoomOptimizer":
            status_label = "Selected Optimized Allocation (CP-SAT)"
            alloc_source = "optimized"
        else:
            status_label = "Joint Allocated Timetable"
            alloc_source = "joint"

        is_all_days = (day is not None and day.lower() == "all")

        filtered_sessions: List[Session] = []
        for s in domain_sessions:
            active_room = assignments.get(s.session_id, "Unassigned")
            if program:
                prog_clean = program.replace("M.Sc. ", "").replace("MSc ", "").strip().lower()
                s_prog_clean = s.program.replace("M.Sc. ", "").replace("MSc ", "").strip().lower()
                if prog_clean != s_prog_clean and prog_clean not in s_prog_clean and s_prog_clean not in prog_clean:
                    continue
            if cohort_id and s.cohort_id != cohort_id:
                continue
            if room_id and active_room != room_id:
                continue
            if not is_all_days and day and s.day.lower() != day.lower():
                continue
            filtered_sessions.append(s)

        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        periods = list(range(1, 9))  # Constrained to 1-8 per Document 05 v0.2.6

        target_day = "All Days" if is_all_days else (day.capitalize() if day else "Monday")

        if is_all_days:
            day_sessions = filtered_sessions
            if group_by == "room":
                entities = sorted(list(set(
                    assignments.get(s.session_id, "Unassigned")
                    for s in filtered_sessions
                    if assignments.get(s.session_id)
                )))
            elif group_by == "program":
                entities = sorted(list(set(s.program for s in filtered_sessions)))
            else:  # cohort
                entities = sorted(list(set(s.cohort_id for s in filtered_sessions)))

            # Chronological weekdays order: Mon -> Tue -> Wed -> Thu -> Fri
            row_keys = []
            for entity in entities:
                for day_name in days:
                    day_abbr = day_name[:3]
                    rk = f"{entity} ({day_abbr})"
                    has_session = any(
                        (
                            assignments.get(s.session_id, "Unassigned") == entity if group_by == "room"
                            else (s.program == entity if group_by == "program" else s.cohort_id == entity)
                        )
                        and s.day.lower() == day_name.lower()
                        for s in filtered_sessions
                    )
                    if has_session or len(entities) == 1:
                        row_keys.append(rk)
        else:
            day_sessions = [s for s in filtered_sessions if s.day.lower() == target_day.lower()]
            if group_by == "room":
                row_keys = sorted(list(set(
                    assignments.get(s.session_id, "Unassigned")
                    for s in day_sessions
                    if assignments.get(s.session_id)
                )))
            elif group_by == "program":
                row_keys = sorted(list(set(s.program for s in day_sessions)))
            else:  # cohort
                row_keys = sorted(list(set(s.cohort_id for s in day_sessions)))

        grid: Dict[str, Dict[int, List[Dict[str, Any]]]] = {
            rk: {p: [] for p in periods} for rk in row_keys
        }

        for s in day_sessions:
            assigned_room = assignments.get(s.session_id, "Unassigned")
            if is_all_days:
                day_abbr = s.day[:3].capitalize()
                if group_by == "room":
                    rk = f"{assigned_room} ({day_abbr})"
                elif group_by == "program":
                    rk = f"{s.program} ({day_abbr})"
                else:
                    rk = f"{s.cohort_id} ({day_abbr})"
            else:
                if group_by == "room":
                    rk = assigned_room
                elif group_by == "program":
                    rk = s.program
                else:
                    rk = s.cohort_id

            if rk in grid:
                for p in s.period_range:
                    if p in grid[rk]:
                        grid[rk][p].append({
                            "session_id": s.session_id,
                            "cohort_id": s.cohort_id,
                            "course": s.course,
                            "program": s.program,
                            "assigned_room_id": assigned_room,
                            "source_file": s.source_file,
                            "source_page": s.source_page,
                            "source_row": int(s.source_page.replace("Row ", "").strip()) if "Row " in s.source_page else None,
                            "session_type": s.session_type,
                            "required_room_type": s.required_room_type,
                            "start_period": s.start_period,
                            "end_period": s.end_period,
                            "duration_periods": s.end_period - s.start_period + 1,
                            "is_multi_period": (s.end_period > s.start_period),
                            "day": s.day,
                            "academic_cycle": s.academic_cycle,
                            "student_count": s.student_count,
                            "evaluation_mode": eval_mode,
                        })

        programs = sorted(list(set(s.program for s in domain_sessions)))
        cohorts = sorted(list(set(s.cohort_id for s in domain_sessions)))
        files = sorted(list(set(s.source_file for s in domain_sessions)))
        rooms = sorted(list(set(
            assignments.get(s.session_id)
            for s in domain_sessions
            if assignments.get(s.session_id)
        )))

        return UploadTimetableResponse(
            run_id=run_id,
            academic_cycle=context.academic_cycle,
            allocation_source=alloc_source,
            allocation_status_label=status_label,
            is_fallback=is_fallback,
            group_by=group_by,
            target_day=target_day,
            row_keys=row_keys,
            total_sessions_filtered=len(filtered_sessions),
            days=days,
            periods=periods,
            grid=grid,
            evaluation_mode=eval_mode,
            evaluation_mode_label="SYNTHETIC DEMO PROFILE" if eval_mode == "synthetic" else "FACTUAL MODE",
            programs=programs,
            cohorts=cohorts,
            files=files,
            rooms=rooms,
        )

