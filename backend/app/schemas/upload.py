"""Pydantic schemas for the Upload & Allocate multi-timetable workflow.

Governed by Document 05 revision v0.2.6 and PAR-CIQ-P7-ADDENDUM-01.
Enforces the 1–8 period range constraint, explicit provenance tracking,
ambiguous header confirmation, and strict room-type requirements.
"""

from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field


class RawFilePayload(BaseModel):
    """Encapsulates an uploaded raw timetable file."""
    filename: str = Field(..., description="Original filename (e.g. 'cyber_security.csv')")
    content: str = Field(..., description="Raw file text content (CSV)")


class RowValidationError(BaseModel):
    """Diagnostic error or warning tied to exact filename and line number."""
    filename: str = Field(..., description="Source filename")
    row_number: int = Field(..., description="1-based row number in source file")
    field: Optional[str] = Field(None, description="Affected column or attribute")
    message: str = Field(..., description="Diagnostic explanation")
    severity: str = Field("error", description="'error' or 'warning'")
    raw_data: Optional[Dict[str, Any]] = Field(None, description="Raw row values for inspection")


class AmbiguousHeaderPrompt(BaseModel):
    """Identifies a column header that cannot be resolved safely without user confirmation."""
    filename: str = Field(..., description="Source filename")
    raw_header: str = Field(..., description="Observed header name in the CSV")
    suggested_field: str = Field(..., description="Candidate target field (e.g. 'program')")
    reason: str = Field(..., description="Explanation of ambiguity (e.g. 'Department vs Program distinction')")
    requires_confirmation: bool = Field(True, description="True if mapping must be confirmed by user")


class NormalizedUploadedSession(BaseModel):
    """Structured, verified session occurrence extracted from an uploaded timetable."""
    session_id: str = Field(..., description="Stable unique identifier for this occurrence (e.g. 'UPL-0001')")
    run_id: str = Field(..., description="Isolation run identifier")
    source_file: str = Field(..., description="Source filename for provenance")
    source_row: int = Field(..., description="Source row number for provenance")
    program: str = Field(..., description="Academic degree program")
    cohort_id: str = Field(..., description="Student cohort identifier")
    course: str = Field(..., description="Course name or code")
    academic_cycle: str = Field(..., description="'odd' or 'even'")
    semester: str = Field("1", description="Curricular semester (1-9)")
    session_type: str = Field("lecture", description="e.g. 'lecture', 'lab', 'seminar'")
    day: str = Field(..., description="Weekday ('Monday' through 'Friday')")
    start_period: int = Field(..., ge=1, le=8, description="Starting period (1-8)")
    end_period: int = Field(..., ge=1, le=8, description="Ending period (1-8)")
    required_room_type: str = Field(..., description="Required room category ('classroom', 'laboratory', 'project_room', 'assembly_hall')")
    required_facilities: Optional[str] = Field(None, description="Optional required equipment")
    student_count: Optional[int] = Field(None, description="Enrolled students if known")
    assigned_room_id: Optional[str] = Field(None, description="Assigned room identifier; None before allocation")

    @property
    def duration_periods(self) -> int:
        return self.end_period - self.start_period + 1

    @property
    def period_range(self) -> List[int]:
        return list(range(self.start_period, self.end_period + 1))


class UploadPreflightRequest(BaseModel):
    """Request payload for preflight parsing and validation."""
    academic_cycle: Optional[str] = Field(None, description="Enforced academic cycle ('odd' or 'even'); if None, derived from files")
    files: List[RawFilePayload] = Field(..., min_length=1, description="List of raw files to inspect")
    column_mappings: Optional[Dict[str, Dict[str, str]]] = Field(
        default_factory=dict,
        description="Explicit column mappings per filename: {filename: {raw_header: target_field}}"
    )
    confirmed_ambiguous_mappings: Optional[Dict[str, Dict[str, str]]] = Field(
        default_factory=dict,
        description="User-confirmed ambiguous mappings: {filename: {raw_header: target_field}}"
    )


class FileSummary(BaseModel):
    """Preflight summary for an individual uploaded file."""
    filename: str
    total_rows: int
    accepted_rows: int
    error_count: int
    warning_count: int
    detected_programs: List[str]
    detected_cohorts: List[str]


class UploadPreflightResponse(BaseModel):
    """Structured preflight validation result."""
    run_id: str = Field(..., description="Unique upload run identifier")
    academic_cycle: str = Field(..., description="Resolved academic cycle ('odd' or 'even')")
    is_valid: bool = Field(..., description="True if all files parsed cleanly with zero blocking errors")
    total_files: int = Field(..., description="Number of files processed")
    total_sessions_accepted: int = Field(..., description="Count of accepted sessions ready for allocation")
    files_summary: List[FileSummary] = Field(default_factory=list)
    programs_detected: List[str] = Field(default_factory=list)
    cohorts_detected: List[str] = Field(default_factory=list)
    ambiguous_headers: List[AmbiguousHeaderPrompt] = Field(default_factory=list)
    errors: List[RowValidationError] = Field(default_factory=list)
    warnings: List[RowValidationError] = Field(default_factory=list)
    sample_sessions: List[NormalizedUploadedSession] = Field(default_factory=list)


class UploadAllocationRequest(BaseModel):
    """Request payload to trigger joint allocation on a validated run."""
    run_id: str = Field(..., description="Unique upload run identifier from preflight")
    evaluation_mode: str = Field("synthetic", description="'synthetic' or 'factual'")
    time_limit_seconds: float = Field(10.0, ge=1.0, le=10.0, description="Solver time limit (1.0 - 10.0s)")
    allow_computing_lab_exception: bool = Field(False, description="Allow narrow computing lab exception if applicable")


class UploadAllocationResponse(BaseModel):
    """Result of joint multi-program room allocation and independent validation."""
    run_id: str = Field(..., description="Upload run identifier")
    academic_cycle: str = Field(..., description="'odd' or 'even'")
    status: str = Field(..., description="'completed', 'infeasible', or 'fallback'")
    selected_allocator: str = Field(..., description="Name of selected allocator candidate")
    fallback_to_baseline: bool = Field(False, description="True if baseline was retained to protect against candidate regression")
    total_sessions: int = Field(..., description="Total input sessions in the joint run")
    assigned_count: int = Field(..., description="Number of sessions successfully placed in physical rooms")
    unassigned_count: int = Field(..., description="Number of sessions left unassigned due to resource contention")
    baseline_walking_time: float = Field(0.0, description="Greedy baseline walking time (minutes)")
    optimized_walking_time: float = Field(0.0, description="Selected walking time (minutes)")
    walking_time_reduction_minutes: float = Field(0.0, description="Minutes saved vs baseline")
    walking_time_reduction_percentage: float = Field(0.0, description="Percentage saved vs baseline")
    validation: Dict[str, Any] = Field(..., description="Independent validation summary dictionary")
    infeasibility_diagnosis: Optional[str] = Field(None, description="Truthful diagnosis if allocation is incomplete or infeasible")
    unassigned_session_ids: List[str] = Field(default_factory=list, description="IDs of sessions that could not be placed")
    evaluation_mode: str = Field("synthetic", description="'synthetic' or 'factual'")
    evaluation_mode_label: str = Field("SYNTHETIC DEMO PROFILE", description="Display label for evaluation mode")
    assignments_count: int = Field(..., description="Count of mappings in active assignment dictionary")


class UploadTimetableResponse(BaseModel):
    """Timetable grid response rendered for a completed upload run."""
    run_id: str
    academic_cycle: str
    allocation_source: str
    allocation_status_label: str
    is_fallback: bool
    group_by: str
    target_day: str
    row_keys: List[str]
    total_sessions_filtered: int
    days: List[str]
    periods: List[int]
    grid: Dict[str, Dict[int, List[Dict[str, Any]]]]
    evaluation_mode: str
    evaluation_mode_label: str
    programs: List[str]
    cohorts: List[str]
    files: List[str]
