"""Pydantic Domain Models for ClassroomIQ Datasets.

Preserves all source fields from the 7 CSV datasets, distinguishing verified,
unverified, unknown, synthetic, and missing attributes.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class Room(BaseModel):
    """Represents a room from rooms.csv."""
    room_id: str = Field(..., description="Unique room identifier (e.g. 'A105', 'M601')")
    room_type: str = Field(..., description="Primary type: classroom, laboratory, assembly_hall")
    additional_uses: Optional[str] = Field(None, description="Permitted secondary functions (e.g. 'project_room')")
    building_block: Optional[str] = Field(None, description="Building or block identifier (unpopulated in source)")
    floor: Optional[str] = Field(None, description="Floor level identifier (unpopulated in source)")
    capacity: Optional[int] = Field(None, description="Known physical seating capacity (unpopulated for 56 rooms)")
    capacity_source: Optional[str] = Field(None, description="Provenance of capacity figure")
    source_record: str = Field(..., description="Lineage document reference")
    verification_status: str = Field(..., description="Audit status label")
    notes: str = Field(..., description="Source-provided caveats and annotations")

    @property
    def has_known_capacity(self) -> bool:
        """Indicates whether a factual capacity exists."""
        return self.capacity is not None

    @property
    def permitted_uses(self) -> List[str]:
        """Returns the list of all approved uses (primary room_type + additional_uses)."""
        uses = [self.room_type]
        if self.additional_uses:
            for item in self.additional_uses.split(";"):
                item_clean = item.strip()
                if item_clean and item_clean not in uses:
                    uses.append(item_clean)
        return uses


class Facility(BaseModel):
    """Represents an equipment/facility record from facilities.csv."""
    room_id: str = Field(..., description="Target room identifier")
    facility_type: str = Field(..., description="Equipment type (e.g. 'projector')")
    installation_status: str = Field(..., description="'yes', 'unknown', or 'conflicting'")
    operational_status: str = Field(..., description="Current operational state ('unknown' for all source rows)")
    verification_status: str = Field(..., description="Data verification label")
    source: str = Field(..., description="Inventory source description")
    notes: str = Field(..., description="Equipment notes")


class Session(BaseModel):
    """Represents a scheduled teaching occurrence from sessions.csv."""
    session_id: str = Field(..., description="Unique session identifier (e.g. 'SSN00001')")
    academic_cycle: str = Field(..., description="'odd' or 'even'")
    semester: str = Field(..., description="Curricular semester (1-9)")
    program: str = Field(..., description="Academic degree program")
    cohort_id: str = Field(..., description="Student cohort identifier")
    course: str = Field(..., description="Course name or title")
    session_type: str = Field(..., description="e.g. 'class_or_activity', 'lab', 'project_or_semester_activity'")
    day: str = Field(..., description="Weekday ('Monday' through 'Friday')")
    start_period: int = Field(..., ge=1, le=8, description="Starting period (1-8)")
    end_period: int = Field(..., ge=1, le=8, description="Ending period (1-8)")
    student_count: Optional[int] = Field(None, description="Enrolled students (unpopulated in source)")
    required_room_type: str = Field(..., description="Required room category ('classroom', 'laboratory', 'project_room')")
    required_facilities: Optional[str] = Field(None, description="Mandatory hardware equipment (unpopulated in source)")
    assigned_room_id: str = Field(..., description="Room assigned in source timetable PDF")
    source_file: str = Field(..., description="Source timetable PDF filename")
    source_page: str = Field(..., description="Source page reference")
    validation_status: str = Field(..., description="Lineage status (e.g. 'source_assignment')")
    notes: str = Field(..., description="Session notes and caveats")

    @property
    def duration_periods(self) -> int:
        """Session duration in number of standard periods."""
        return self.end_period - self.start_period + 1

    @property
    def period_range(self) -> List[int]:
        """List of all discrete periods spanned by this session."""
        return list(range(self.start_period, self.end_period + 1))


class AvailabilityRecord(BaseModel):
    """Represents a room availability slot from availability.csv."""
    room_id: str = Field(..., description="Room identifier")
    academic_cycle: str = Field(..., description="'odd' or 'even'")
    day: str = Field(..., description="Weekday")
    period: int = Field(..., ge=1, le=8, description="Period number (1-8)")
    status: str = Field(..., description="'occupied', 'not_scheduled_in_provided_timetable', or 'unknown'")
    session_id: Optional[str] = Field(None, description="Associated session ID if occupied")
    source_status: str = Field(..., description="Lineage status of the availability entry")

    @property
    def is_occupied(self) -> bool:
        """True if the room is assigned to a session in this slot."""
        return self.status == "occupied"


class TravelTime(BaseModel):
    """Represents a pairwise walking duration from travel_times.csv."""
    from_room_id: str = Field(..., description="Origin room identifier")
    to_room_id: str = Field(..., description="Destination room identifier")
    walking_time_minutes: float = Field(..., ge=0.0, description="Estimated walking time in minutes")
    source_status: str = Field(..., description="e.g. 'synthetic_demo_estimate_unverified'")
    notes: str = Field(..., description="Provenance caveats")


class EventRecord(BaseModel):
    """Represents a demonstration disruption event from events.csv."""
    event_id: str = Field(..., description="Unique event identifier (e.g. 'EVT-DEMO-001')")
    room_id: str = Field(..., description="Target room affected by disruption")
    academic_cycle: str = Field(..., description="'odd' or 'even'")
    start_day: str = Field(..., description="Effective start day")
    start_period: int = Field(..., ge=1, le=8, description="Effective start period")
    end_day: str = Field(..., description="Effective end day")
    end_period: int = Field(..., ge=1, le=8, description="Effective end period")
    event_type: str = Field(..., description="e.g. 'room_closure', 'equipment_failure', 'maintenance'")
    description: str = Field(..., description="Human-readable scenario description")
    status: str = Field(..., description="Event lifecycle state (e.g. 'simulation_only')")
    source_status: str = Field(..., description="Lineage tag (e.g. 'synthetic_demo_scenario_not_live')")
    related_session_id: str = Field(..., description="Session directly targeted/impacted in demo")


# Alias for domain clarity in simulation contexts
DisruptionEvent = EventRecord


class ComplaintRecord(BaseModel):
    """Represents a demonstration service complaint from complaints.csv."""
    complaint_id: str = Field(..., description="Unique complaint identifier (e.g. 'CMP-DEMO-001')")
    location_type: str = Field(..., description="Location category ('classroom', 'laboratory', 'assembly_hall')")
    location_id: str = Field(..., description="Room identifier")
    reporter_role: str = Field(..., description="Reporting user role")
    issue_type: str = Field(..., description="Categorized problem")
    description: str = Field(..., description="Complaint narrative")
    assigned_department: str = Field(..., description="Maintenance unit")
    priority: str = Field(..., description="'low', 'medium', 'high'")
    status: str = Field(..., description="'Submitted', 'Assigned', 'In Progress', 'Resolved'")
    resolution: Optional[str] = Field(None, description="Resolution notes (None for open tickets)")
    created_at: str = Field(..., description="ISO 8601 creation timestamp")
    updated_at: str = Field(..., description="ISO 8601 last update timestamp")
    source_status: str = Field(..., description="Lineage tag (e.g. 'synthetic_demo_record_not_real_complaint')")


class IngestionReport(BaseModel):
    """Diagnostic report capturing the outcome of dataset ingestion."""
    files_loaded: List[str] = Field(default_factory=list)
    record_counts: Dict[str, int] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    is_success: bool = True


class DatasetSnapshot(BaseModel):
    """Immutable in-memory snapshot of all seven ingested datasets."""
    rooms: List[Room] = Field(default_factory=list)
    facilities: List[Facility] = Field(default_factory=list)
    sessions: List[Session] = Field(default_factory=list)
    availability: List[AvailabilityRecord] = Field(default_factory=list)
    travel_times: List[TravelTime] = Field(default_factory=list)
    events: List[EventRecord] = Field(default_factory=list)
    complaints: List[ComplaintRecord] = Field(default_factory=list)
    report: IngestionReport = Field(default_factory=IngestionReport)

    @property
    def room_index(self) -> Dict[str, Room]:
        """Dictionary of rooms keyed by room_id."""
        return {r.room_id: r for r in self.rooms}

    @property
    def session_index(self) -> Dict[str, Session]:
        """Dictionary of sessions keyed by session_id."""
        return {s.session_id: s for s in self.sessions}
