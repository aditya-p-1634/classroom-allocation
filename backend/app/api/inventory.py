"""Inventory, Rooms, Cohorts, Programs, and Timetable Grid Endpoints."""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Query, HTTPException
from backend.app.services.data_loader import DataLoaderService
from backend.app.services.synthetic_profile import SyntheticProfileService
from backend.app.schemas.models import Room, Session

router = APIRouter(prefix="/inventory", tags=["Inventory"])


@router.get("/profile", response_model=Dict[str, Any])
def get_synthetic_profile_info() -> Dict[str, Any]:
    """Returns documentation and parameters of the Synthetic Demo Profile."""
    return {
        "profile_name": "SYNTHETIC DEMO PROFILE",
        "description": "Deterministic, repeatable sample assumptions in memory per Document 05 Phase P7 specification.",
        "defaults": {
            "classroom_capacity": 65,
            "laboratory_capacity": 40,
            "assembly_hall_capacity": 120,
            "lecture_student_enrollment": 55,
            "lab_student_enrollment": 30,
            "seminar_student_enrollment": 25,
            "facility_operational_status": "Operational (Demo Profile)",
        },
        "governance_rule": "Deterministic in memory • Source CSV files remain bit-for-bit unchanged • Mode labeled prominently.",
    }


@router.get("/rooms", response_model=List[Dict[str, Any]])
def get_rooms(
    room_type: Optional[str] = Query(None, description="Filter by room type: classroom, laboratory, assembly_hall"),
    capability: Optional[str] = Query(None, description="Filter by permitted capability"),
    building_block: Optional[str] = Query(None, description="Filter by building block prefix"),
    mode: str = Query("synthetic", description="'synthetic' or 'factual'"),
) -> List[Dict[str, Any]]:
    """Returns the 86 physical rooms with capacity and location appropriate to active mode."""
    snapshot = DataLoaderService().load_snapshot()
    rooms = snapshot.rooms

    if room_type:
        rooms = [r for r in rooms if r.room_type == room_type]
    if capability:
        rooms = [r for r in rooms if capability in (r.permitted_uses or [])]
    if building_block:
        rooms = [r for r in rooms if r.room_id.upper().startswith(building_block.upper())]

    result = []
    for r in rooms:
        loc = SyntheticProfileService.get_room_building_and_floor(r.room_id)
        syn_cap = SyntheticProfileService.get_synthetic_room_capacity(r)

        if mode == "synthetic":
            capacity_val = syn_cap
            is_cap_syn = not r.has_known_capacity
            cap_status = "Factual (Verified)" if r.has_known_capacity else "Demo Estimate (Synthetic Profile)"
            block_val = loc["building_block"]
            floor_val = loc["floor"]
            op_status = "Operational (Demo Profile)"
        else:
            capacity_val = r.capacity
            is_cap_syn = False
            cap_status = "Factual (Verified)" if r.has_known_capacity else "Unknown (Data Gap)"
            block_val = r.building_block or "Unspecified in rooms.csv"
            floor_val = r.floor or "Unspecified in rooms.csv"
            op_status = "Not Recorded in facilities.csv"

        result.append({
            "room_id": r.room_id,
            "room_type": r.room_type,
            "additional_uses": r.additional_uses,
            "permitted_uses": r.permitted_uses,
            "building_block": block_val,
            "floor": floor_val,
            "capacity": capacity_val,
            "has_known_capacity": r.has_known_capacity,
            "is_capacity_synthetic": is_cap_syn,
            "capacity_status": cap_status,
            "operational_status": op_status,
            "verification_status": r.verification_status,
            "notes": r.notes,
        })
    return result


@router.get("/room-detail/{room_id}", response_model=Dict[str, Any])
def get_room_detail(
    room_id: str,
    academic_cycle: str = Query("even", description="'odd' or 'even'"),
    mode: str = Query("synthetic", description="'synthetic' or 'factual'"),
) -> Dict[str, Any]:
    """Returns detailed profile for a specific room including weekly occupancy grid."""
    snapshot = DataLoaderService().load_snapshot()
    room = next((r for r in snapshot.rooms if r.room_id.upper() == room_id.upper()), None)
    if not room:
        raise HTTPException(status_code=404, detail=f"Room '{room_id}' not found in rooms.csv")

    loc = SyntheticProfileService.get_room_building_and_floor(room.room_id)
    syn_cap = SyntheticProfileService.get_synthetic_room_capacity(room)

    # Calculate weekly schedule for this room
    cycle_sessions = [
        s for s in snapshot.sessions
        if s.academic_cycle == academic_cycle and s.assigned_room_id == room.room_id
    ]

    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    periods = list(range(1, 10))
    schedule_grid = {d: {p: None for p in periods} for d in days}
    total_occupied_periods = 0

    for s in cycle_sessions:
        if s.day in schedule_grid:
            for p in s.period_range:
                if p in schedule_grid[s.day]:
                    schedule_grid[s.day][p] = {
                        "session_id": s.session_id,
                        "course": s.course,
                        "cohort_id": s.cohort_id,
                        "program": s.program,
                        "session_type": s.session_type,
                    }
                    total_occupied_periods += 1

    total_periods = len(days) * len(periods)
    utilization_pct = round((total_occupied_periods / total_periods) * 100, 1) if total_periods > 0 else 0.0

    return {
        "room_id": room.room_id,
        "room_type": room.room_type,
        "permitted_uses": room.permitted_uses,
        "building_block": loc["building_block"] if mode == "synthetic" else (room.building_block or "Unspecified in rooms.csv"),
        "floor": loc["floor"] if mode == "synthetic" else (room.floor or "Unspecified in rooms.csv"),
        "capacity": syn_cap if mode == "synthetic" else room.capacity,
        "capacity_status": ("Factual (Verified)" if room.has_known_capacity else ("Demo Estimate" if mode == "synthetic" else "Unknown (Data Gap)")),
        "has_known_capacity": room.has_known_capacity,
        "operational_status": "Operational (Demo Profile)" if mode == "synthetic" else "Not Recorded in facilities.csv",
        "academic_cycle": academic_cycle,
        "total_scheduled_sessions": len(cycle_sessions),
        "total_occupied_periods": total_occupied_periods,
        "total_weekly_periods": total_periods,
        "utilization_percentage": utilization_pct,
        "schedule": schedule_grid,
    }


@router.get("/programs", response_model=List[Dict[str, Any]])
def get_programs() -> List[Dict[str, Any]]:
    """Returns the 5 distinct academic programs and their session distributions."""
    snapshot = DataLoaderService().load_snapshot()
    programs_map: Dict[str, Dict[str, int]] = {}

    for s in snapshot.sessions:
        if s.program not in programs_map:
            programs_map[s.program] = {"odd": 0, "even": 0, "total": 0}
        programs_map[s.program][s.academic_cycle] += 1
        programs_map[s.program]["total"] += 1

    return [
        {
            "program": p_name,
            "odd_sessions": counts["odd"],
            "even_sessions": counts["even"],
            "total_sessions": counts["total"],
        }
        for p_name, counts in sorted(programs_map.items())
    ]


@router.get("/cohorts", response_model=List[Dict[str, Any]])
def get_cohorts(
    academic_cycle: Optional[str] = Query(None, description="'odd' or 'even'"),
    program: Optional[str] = Query(None, description="Filter by program"),
) -> List[Dict[str, Any]]:
    """Returns unique student cohort identifiers and their session counts."""
    snapshot = DataLoaderService().load_snapshot()
    cohort_map: Dict[str, Dict[str, Any]] = {}

    for s in snapshot.sessions:
        if academic_cycle and s.academic_cycle != academic_cycle:
            continue
        if program and s.program != program:
            continue

        cid = s.cohort_id
        if cid not in cohort_map:
            cohort_map[cid] = {
                "cohort_id": cid,
                "academic_cycle": s.academic_cycle,
                "semester": s.semester,
                "program": s.program,
                "session_count": 0,
            }
        cohort_map[cid]["session_count"] += 1

    return sorted(cohort_map.values(), key=lambda x: x["cohort_id"])


@router.get("/sessions", response_model=List[Dict[str, Any]])
def get_sessions(
    academic_cycle: Optional[str] = Query(None, description="'odd' or 'even'"),
    program: Optional[str] = Query(None, description="Filter by program"),
    cohort_id: Optional[str] = Query(None, description="Filter by cohort_id"),
    day: Optional[str] = Query(None, description="Filter by weekday"),
    room_id: Optional[str] = Query(None, description="Filter by assigned_room_id"),
    mode: str = Query("synthetic", description="'synthetic' or 'factual'"),
) -> List[Dict[str, Any]]:
    """Returns scheduled teaching occurrences with comprehensive filtering."""
    snapshot = DataLoaderService().load_snapshot()
    sessions = snapshot.sessions

    if academic_cycle and academic_cycle in ["odd", "even"]:
        sessions = [s for s in sessions if s.academic_cycle == academic_cycle]
    if program:
        sessions = [s for s in sessions if s.program == program]
    if cohort_id:
        sessions = [s for s in sessions if s.cohort_id == cohort_id]
    if day:
        sessions = [s for s in sessions if s.day.lower() == day.lower()]
    if room_id:
        sessions = [s for s in sessions if s.assigned_room_id == room_id]

    return [
        {
            "session_id": s.session_id,
            "academic_cycle": s.academic_cycle,
            "semester": s.semester,
            "program": s.program,
            "cohort_id": s.cohort_id,
            "course": s.course,
            "session_type": s.session_type,
            "day": s.day,
            "start_period": s.start_period,
            "end_period": s.end_period,
            "period_range": s.period_range,
            "student_count": (
                SyntheticProfileService.get_synthetic_session_demand(s)
                if mode == "synthetic" else s.student_count
            ),
            "student_count_status": "Demo Estimate (Synthetic Profile)" if mode == "synthetic" else "Unknown (Data Gap)",
            "required_room_type": s.required_room_type,
            "assigned_room_id": s.assigned_room_id,
            "validation_status": s.validation_status,
        }
        for s in sessions
    ]


@router.get("/timetables", response_model=Dict[str, Any])
def get_timetable_grid(
    academic_cycle: str = Query("even", description="'odd' or 'even'"),
    allocation_source: str = Query("source", description="'source', 'baseline', or 'optimized'"),
    group_by: str = Query("cohort", description="'cohort', 'room', or 'program'"),
    cohort_id: Optional[str] = Query(None, description="Optional cohort filter"),
    program: Optional[str] = Query(None, description="Optional program filter"),
    room_id: Optional[str] = Query(None, description="Optional room filter"),
    day: Optional[str] = Query(None, description="Optional day filter"),
    mode: str = Query("synthetic", description="'synthetic' or 'factual'"),
) -> Dict[str, Any]:
    """Returns a structured weekly timetable grid rendered from the requested allocation source."""
    snapshot = DataLoaderService().load_snapshot()
    cycle_sessions = [s for s in snapshot.sessions if s.academic_cycle == academic_cycle]

    # Resolve assignment mapping according to allocation_source
    is_fallback = False
    reassigned_count = 0
    if allocation_source == "baseline":
        from backend.app.services.allocation_service import AllocationService
        service = AllocationService()
        base_res = service.run_baseline_allocation(academic_cycle=academic_cycle)
        assignments = base_res.candidate.assignments
        status_label = "Selected Baseline Allocation (Greedy P5)"
    elif allocation_source == "optimized":
        from backend.app.services.allocation_service import AllocationService
        service = AllocationService()
        comparison = service.compare_baseline_and_optimizer(academic_cycle=academic_cycle)
        if comparison.fallback_to_baseline:
            # Fallback to baseline
            base_res = service.run_baseline_allocation(academic_cycle=academic_cycle)
            assignments = base_res.candidate.assignments
            status_label = "Selected Allocation: Safe Fallback — Valid Baseline Retained"
            is_fallback = True
        else:
            opt_res = service.run_optimized_allocation(academic_cycle=academic_cycle)
            assignments = opt_res.candidate.assignments
            status_label = "Selected Optimized Allocation (CP-SAT)"
    else:  # source
        assignments = {s.session_id: s.assigned_room_id for s in cycle_sessions if s.assigned_room_id}
        status_label = "Imported Source Timetable (sessions.csv)"

    # Apply filters
    filtered_sessions = []
    for s in cycle_sessions:
        active_room = assignments.get(s.session_id, s.assigned_room_id or "Unassigned")
        if s.assigned_room_id and active_room != s.assigned_room_id:
            reassigned_count += 1

        if program and s.program != program:
            continue
        if cohort_id and s.cohort_id != cohort_id:
            continue
        if room_id and active_room != room_id:
            continue
        if day and s.day.lower() != day.lower():
            continue

        filtered_sessions.append(s)

    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    periods = list(range(1, 10))

    # Determine row keys according to group_by
    if group_by == "room":
        row_keys = sorted(list(set(
            assignments.get(s.session_id, s.assigned_room_id or "Unassigned")
            for s in filtered_sessions
            if assignments.get(s.session_id, s.assigned_room_id or "Unassigned") != "Unassigned"
        )))
    elif group_by == "program":
        row_keys = sorted(list(set(s.program for s in filtered_sessions)))
    else:  # cohort
        row_keys = sorted(list(set(s.cohort_id for s in filtered_sessions)))

    # Structure grid: row_key -> period -> list of sessions
    # (for the selected day or across all sessions)
    is_all_days = (day is not None and day.lower().strip() in ("all", "all days", "all_days", "alldays"))
    target_day = "All Days" if is_all_days else (day.capitalize() if day else "Monday")
    day_sessions = filtered_sessions if is_all_days else [s for s in filtered_sessions if s.day.lower() == target_day.lower()]

    grid: Dict[str, Dict[int, List[Dict[str, Any]]]] = {
        rk: {p: [] for p in periods} for rk in row_keys
    }

    for s in day_sessions:
        assigned_room = assignments.get(s.session_id, s.assigned_room_id or "Unassigned")
        was_relocated = (assigned_room != s.assigned_room_id)

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
                        "source_room_id": s.assigned_room_id,
                        "was_reassigned": was_relocated,
                        "session_type": s.session_type,
                        "required_room_type": s.required_room_type,
                        "start_period": s.start_period,
                        "end_period": s.end_period,
                        "student_count": (
                            SyntheticProfileService.get_synthetic_session_demand(s)
                            if mode == "synthetic" else s.student_count
                        ),
                        "student_count_status": "Demo Estimate" if mode == "synthetic" else "Unknown",
                    })

    return {
        "academic_cycle": academic_cycle,
        "allocation_source": allocation_source,
        "allocation_status_label": status_label,
        "is_fallback": is_fallback,
        "group_by": group_by,
        "target_day": target_day,
        "row_keys": row_keys,
        "total_sessions_filtered": len(filtered_sessions),
        "days": days,
        "periods": periods,
        "grid": grid,
        "mode": mode,
        "disclaimer": (
            "Displaying selected room assignments returned by allocation service."
            if allocation_source != "source"
            else "Displaying raw imported timetable records from sessions.csv."
        ),
    }
