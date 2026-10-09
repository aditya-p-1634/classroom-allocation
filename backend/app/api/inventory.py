"""Inventory, Rooms, Cohorts, Programs, and Timetable Grid Endpoints."""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Query
from backend.app.services.data_loader import DataLoaderService
from backend.app.schemas.models import Room, Session

router = APIRouter(prefix="/inventory", tags=["Inventory"])


@router.get("/rooms", response_model=List[Dict[str, Any]])
def get_rooms(
    room_type: Optional[str] = Query(None, description="Filter by room type: classroom, laboratory, assembly_hall"),
) -> List[Dict[str, Any]]:
    """Returns the 86 physical rooms from rooms.csv with explicit capacity data gap markers."""
    snapshot = DataLoaderService().load_snapshot()
    rooms = snapshot.rooms
    if room_type:
        rooms = [r for r in rooms if r.room_type == room_type]

    result = []
    for r in rooms:
        result.append({
            "room_id": r.room_id,
            "room_type": r.room_type,
            "additional_uses": r.additional_uses,
            "permitted_uses": r.permitted_uses,
            "building_block": r.building_block or "Unknown (Data Gap)",
            "floor": r.floor or "Unknown (Data Gap)",
            "capacity": r.capacity,
            "has_known_capacity": r.has_known_capacity,
            "capacity_status": "Factual (Verified)" if r.has_known_capacity else "Unknown (Data Gap)",
            "verification_status": r.verification_status,
            "notes": r.notes,
        })
    return result


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
    """Returns the 45 unique student cohort identifiers and their session counts."""
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
            "student_count": s.student_count,
            "student_count_status": "Unknown (Data Gap)",
            "required_room_type": s.required_room_type,
            "assigned_room_id": s.assigned_room_id,
            "validation_status": s.validation_status,
        }
        for s in sessions
    ]


@router.get("/timetables", response_model=Dict[str, Any])
def get_timetable_grid(
    academic_cycle: str = Query("odd", description="'odd' or 'even'"),
    cohort_id: Optional[str] = Query(None, description="Optional cohort filter"),
    program: Optional[str] = Query(None, description="Optional program filter"),
    room_id: Optional[str] = Query(None, description="Optional room filter"),
    day: Optional[str] = Query(None, description="Optional day filter"),
) -> Dict[str, Any]:
    """Returns a structured weekly timetable grid (Day x Period) for UI rendering."""
    snapshot = DataLoaderService().load_snapshot()
    sessions = [s for s in snapshot.sessions if s.academic_cycle == academic_cycle]

    if program:
        sessions = [s for s in sessions if s.program == program]
    if cohort_id:
        sessions = [s for s in sessions if s.cohort_id == cohort_id]
    if room_id:
        sessions = [s for s in sessions if s.assigned_room_id == room_id]
    if day:
        sessions = [s for s in sessions if s.day.lower() == day.lower()]

    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    periods = [1, 2, 3, 4, 5, 6, 7, 8, 9]

    # Organize grid by day -> period -> list of sessions
    grid: Dict[str, Dict[int, List[Dict[str, Any]]]] = {d: {p: [] for p in periods} for d in days}

    for s in sessions:
        if s.day in grid:
            for p in s.period_range:
                if p in grid[s.day]:
                    grid[s.day][p].append({
                        "session_id": s.session_id,
                        "cohort_id": s.cohort_id,
                        "course": s.course,
                        "program": s.program,
                        "room_id": s.assigned_room_id,
                        "session_type": s.session_type,
                        "required_room_type": s.required_room_type,
                        "start_period": s.start_period,
                        "end_period": s.end_period,
                    })

    return {
        "academic_cycle": academic_cycle,
        "total_sessions_filtered": len(sessions),
        "days": days,
        "periods": periods,
        "grid": grid,
        "disclaimer": "Live session and room cells are populated from the selected source cycle in the application.",
    }
