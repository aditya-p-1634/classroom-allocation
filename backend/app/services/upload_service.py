"""Upload Normalization and Validation Service for ClassroomIQ.

Governed by Document 05 revision v0.2.6 and PAR-CIQ-P7-ADDENDUM-01.
Implements multi-file CSV ingestion, column mapping, ambiguous header confirmation,
period range bounds (1-8), cohort collision checks, and session model synthesis.
"""

import csv
import io
import re
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple, Any

from backend.app.schemas.models import Session
from backend.app.schemas.upload import (
    RawFilePayload,
    RowValidationError,
    AmbiguousHeaderPrompt,
    NormalizedUploadedSession,
    UploadPreflightRequest,
    UploadPreflightResponse,
    FileSummary,
)

# Standard canonical aliases
STANDARD_ALIASES: Dict[str, List[str]] = {
    "program": ["program", "degree", "academic_program", "course_stream", "branch"],
    "cohort_id": ["cohort", "cohort_id", "section", "class", "batch"],
    "course": ["course", "subject", "course_name", "paper", "course_code", "title"],
    "academic_cycle": ["cycle", "academic_cycle", "term_type"],
    "day": ["day", "weekday", "day_of_week"],
    "start_period": ["start_period", "from_period", "start_slot", "start_hour", "start"],
    "end_period": ["end_period", "to_period", "end_slot", "end_hour", "end"],
    "required_room_type": ["required_room_type", "room_type", "type_needed", "space_type"],
    "semester": ["semester", "sem"],
    "session_type": ["session_type", "type", "kind"],
    "student_count": ["students", "strength", "enrolled", "student_count", "capacity_needed"],
    "required_facilities": ["required_facilities", "facilities", "equipment"],
}

# Ambiguous headers that must NEVER be mapped silently
AMBIGUOUS_HEADERS: Dict[str, Tuple[str, str]] = {
    "department": ("program", "Header 'department' may refer to an administrative department rather than an academic degree program. Requires explicit user confirmation."),
    "dept": ("program", "Header 'dept' may refer to an administrative department rather than an academic degree program. Requires explicit user confirmation."),
    "room": ("assigned_room_id", "Header 'room' suggests an assigned room, but raw uploads are unallocated. Requires user confirmation if intended as a pre-reservation."),
}

VALID_DAYS = {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday"}

ROOM_TYPE_NORMALIZATIONS = {
    "classroom": "classroom",
    "class": "classroom",
    "lecture": "classroom",
    "lecture_hall": "classroom",
    "theory": "classroom",
    "laboratory": "laboratory",
    "lab": "laboratory",
    "computer_lab": "laboratory",
    "software_lab": "laboratory",
    "project_room": "project_room",
    "project": "project_room",
    "assembly_hall": "assembly_hall",
    "hall": "assembly_hall",
    "auditorium": "assembly_hall",
    "seminar_hall": "assembly_hall",
}


class UploadRunContext:
    """Encapsulates the state of an uploaded dataset run."""
    def __init__(
        self,
        run_id: str,
        academic_cycle: str,
        files: List[RawFilePayload],
        normalized_sessions: List[NormalizedUploadedSession],
    ):
        self.run_id = run_id
        self.academic_cycle = academic_cycle
        self.files = files
        self.normalized_sessions = normalized_sessions
        self.created_at = datetime.now()
        self.allocation_result: Optional[Any] = None
        self.allocated_assignments: Dict[str, str] = {}


class UploadService:
    """Coordinates parsing, validation, and normalization of uploaded timetables."""

    _registry: Dict[str, UploadRunContext] = {}

    @classmethod
    def get_run_context(cls, run_id: str) -> Optional[UploadRunContext]:
        """Retrieves an active upload run from memory."""
        return cls._registry.get(run_id)

    @classmethod
    def register_run_context(cls, context: UploadRunContext) -> None:
        """Stores an upload run context in memory."""
        cls._registry[context.run_id] = context

    def resolve_headers(
        self,
        raw_headers: List[str],
        filename: str,
        explicit_mappings: Dict[str, str],
        confirmed_ambiguous: Dict[str, str],
    ) -> Tuple[Dict[str, str], List[AmbiguousHeaderPrompt]]:
        """Maps raw CSV headers to canonical schema fields."""
        mapped: Dict[str, str] = {}
        ambiguous_prompts: List[AmbiguousHeaderPrompt] = []

        for raw_h in raw_headers:
            clean_h = raw_h.strip().lower()
            clean_key = re.sub(r"[^a-z0-9_]", "", clean_h.replace(" ", "_"))

            # 1. Check user-supplied explicit column mappings
            if raw_h in explicit_mappings:
                mapped[raw_h] = explicit_mappings[raw_h]
                continue
            if clean_h in explicit_mappings:
                mapped[raw_h] = explicit_mappings[clean_h]
                continue

            # 2. Check ambiguous headers requiring confirmation
            if clean_key in AMBIGUOUS_HEADERS:
                suggested, reason = AMBIGUOUS_HEADERS[clean_key]
                if raw_h in confirmed_ambiguous or clean_key in confirmed_ambiguous:
                    mapped[raw_h] = confirmed_ambiguous.get(raw_h, confirmed_ambiguous.get(clean_key))
                else:
                    ambiguous_prompts.append(
                        AmbiguousHeaderPrompt(
                            filename=filename,
                            raw_header=raw_h,
                            suggested_field=suggested,
                            reason=reason,
                            requires_confirmation=True,
                        )
                    )
                continue

            # 3. Match against standard canonical aliases
            found = False
            for canonical, aliases in STANDARD_ALIASES.items():
                if clean_key == canonical or clean_key in aliases or clean_h in aliases:
                    mapped[raw_h] = canonical
                    found = True
                    break

            if not found:
                mapped[raw_h] = raw_h

        return mapped, ambiguous_prompts

    def process_preflight(self, request: UploadPreflightRequest) -> UploadPreflightResponse:
        """Executes full multi-file preflight inspection, parsing, and normalization."""
        run_id = f"UPL-RUN-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6]}"
        errors: List[RowValidationError] = []
        warnings: List[RowValidationError] = []
        all_ambiguous: List[AmbiguousHeaderPrompt] = []
        all_normalized: List[NormalizedUploadedSession] = []
        files_summary: List[FileSummary] = []
        
        detected_programs: Set[str] = set()
        detected_cohorts: Set[str] = set()
        detected_cycles: Set[str] = set()
        
        session_counter = 1

        for raw_file in request.files:
            filename = raw_file.filename
            file_explicit_map = request.column_mappings.get(filename, {})
            file_confirmed_ambiguous = request.confirmed_ambiguous_mappings.get(filename, {})
            
            # Read CSV content
            f_stream = io.StringIO(raw_file.content)
            try:
                reader = csv.reader(f_stream)
                header_row = next(reader, None)
            except Exception as e:
                errors.append(
                    RowValidationError(
                        filename=filename,
                        row_number=1,
                        message=f"Failed to read CSV structure: {str(e)}",
                        severity="error",
                    )
                )
                continue

            if not header_row:
                errors.append(
                    RowValidationError(
                        filename=filename,
                        row_number=1,
                        message="File is empty or contains no header row.",
                        severity="error",
                    )
                )
                continue

            # Resolve column mapping
            header_map, ambiguous_prompts = self.resolve_headers(
                header_row, filename, file_explicit_map, file_confirmed_ambiguous
            )
            all_ambiguous.extend(ambiguous_prompts)

            # Check for required canonical columns
            mapped_targets = set(header_map.values())
            required_fields = ["cohort_id", "course", "day", "start_period", "end_period", "required_room_type"]
            for rf in required_fields:
                if rf not in mapped_targets:
                    errors.append(
                        RowValidationError(
                            filename=filename,
                            row_number=1,
                            field=rf,
                            message=f"Missing mandatory column '{rf}'. Please provide column mapping.",
                            severity="error",
                        )
                    )

            file_accepted = 0
            file_errors = 0
            file_warnings = 0
            file_programs: Set[str] = set()
            file_cohorts: Set[str] = set()

            # Invert header_map: canonical -> list of raw headers
            canonical_to_raw: Dict[str, str] = {v: k for k, v in header_map.items()}

            row_num = 1
            for row in reader:
                row_num += 1
                if not any(cell.strip() for cell in row):
                    continue  # skip completely blank rows

                row_dict = {header_row[i]: (row[i].strip() if i < len(row) else "") for i in range(len(header_row))}

                def get_val(canonical_key: str, default: str = "") -> str:
                    raw_col = canonical_to_raw.get(canonical_key)
                    if raw_col and raw_col in row_dict:
                        return row_dict[raw_col].strip()
                    return default

                # Extract and validate fields
                cohort = get_val("cohort_id")
                course = get_val("course")
                day_raw = get_val("day")
                start_p_str = get_val("start_period")
                end_p_str = get_val("end_period")
                room_type_raw = get_val("required_room_type")
                program_val = get_val("program")
                cycle_val = get_val("academic_cycle")
                sem_val = get_val("semester", "1")
                session_type_val = get_val("session_type", "lecture")
                student_count_str = get_val("student_count")
                facilities_val = get_val("required_facilities", None)

                row_has_error = False

                # 1. Program handling
                if not program_val:
                    # Derivation fallback: if filename contains program hint or cohort has prefix
                    if cohort:
                        derived = cohort.split("_")[-1]
                        program_val = f"Program {derived}"
                        warnings.append(
                            RowValidationError(
                                filename=filename,
                                row_number=row_num,
                                field="program",
                                message=f"Missing explicit program; inferred '{program_val}' from cohort ID.",
                                severity="warning",
                            )
                        )
                    else:
                        errors.append(
                            RowValidationError(
                                filename=filename,
                                row_number=row_num,
                                field="program",
                                message="Missing mandatory academic program.",
                                severity="error",
                            )
                        )
                        row_has_error = True

                # 2. Cohort & Course
                if not cohort:
                    errors.append(
                        RowValidationError(
                            filename=filename,
                            row_number=row_num,
                            field="cohort_id",
                            message="Missing mandatory student cohort identifier.",
                            severity="error",
                        )
                    )
                    row_has_error = True

                if not course:
                    errors.append(
                        RowValidationError(
                            filename=filename,
                            row_number=row_num,
                            field="course",
                            message="Missing mandatory course name or course code.",
                            severity="error",
                        )
                    )
                    row_has_error = True

                # 3. Day validation
                day_norm = day_raw.capitalize() if day_raw else ""
                if day_norm not in VALID_DAYS:
                    errors.append(
                        RowValidationError(
                            filename=filename,
                            row_number=row_num,
                            field="day",
                            message=f"Invalid weekday '{day_raw}'. Expected Monday through Friday.",
                            severity="error",
                        )
                    )
                    row_has_error = True

                # 4. Period bounds validation (Strictly 1–8 per Document 05 v0.2.6)
                try:
                    start_p = int(start_p_str)
                    end_p = int(end_p_str)
                except (ValueError, TypeError):
                    errors.append(
                        RowValidationError(
                            filename=filename,
                            row_number=row_num,
                            field="periods",
                            message=f"Periods must be numeric integers. Received start='{start_p_str}', end='{end_p_str}'.",
                            severity="error",
                        )
                    )
                    row_has_error = True
                    start_p, end_p = 1, 1

                if not row_has_error:
                    if start_p < 1 or end_p > 8:
                        errors.append(
                            RowValidationError(
                                filename=filename,
                                row_number=row_num,
                                field="periods",
                                message=(
                                    f"Period range [{start_p}, {end_p}] out of bounds. "
                                    f"ClassroomIQ timetable inputs are strictly constrained to periods 1–8. "
                                    f"Period-9 scheduling is not permitted in raw CSV uploads."
                                ),
                                severity="error",
                            )
                        )
                        row_has_error = True
                    elif start_p > end_p:
                        errors.append(
                            RowValidationError(
                                filename=filename,
                                row_number=row_num,
                                field="periods",
                                message=f"Start period ({start_p}) cannot be greater than end period ({end_p}).",
                                severity="error",
                            )
                        )
                        row_has_error = True

                # 5. Room type validation (Strict, no silent inference)
                if not room_type_raw:
                    errors.append(
                        RowValidationError(
                            filename=filename,
                            row_number=row_num,
                            field="required_room_type",
                            message="Missing required room type. Silent inference from course names is prohibited.",
                            severity="error",
                        )
                    )
                    row_has_error = True
                    normalized_room_type = "classroom"
                else:
                    rt_clean = room_type_raw.strip().lower().replace(" ", "_")
                    normalized_room_type = ROOM_TYPE_NORMALIZATIONS.get(rt_clean)
                    if not normalized_room_type:
                        errors.append(
                            RowValidationError(
                                filename=filename,
                                row_number=row_num,
                                field="required_room_type",
                                message=(
                                    f"Unrecognized room type '{room_type_raw}'. "
                                    f"Expected 'classroom', 'laboratory', 'project_room', or 'assembly_hall'."
                                ),
                                severity="error",
                            )
                        )
                        row_has_error = True
                        normalized_room_type = "classroom"

                # 6. Cycle handling
                if not cycle_val:
                    # Default from request if available, else derive from cohort prefix or semester
                    if request.academic_cycle:
                        cycle_val = request.academic_cycle
                    elif "odd" in cohort.lower():
                        cycle_val = "odd"
                    elif "even" in cohort.lower():
                        cycle_val = "even"
                    else:
                        # Derive from semester integer
                        try:
                            sem_int = int(sem_val)
                            cycle_val = "odd" if sem_int % 2 == 1 else "even"
                        except ValueError:
                            cycle_val = "even"
                else:
                    cycle_val = cycle_val.strip().lower()
                    if cycle_val not in ["odd", "even"]:
                        errors.append(
                            RowValidationError(
                                filename=filename,
                                row_number=row_num,
                                field="academic_cycle",
                                message=f"Invalid academic cycle '{cycle_val}'. Expected 'odd' or 'even'.",
                                severity="error",
                            )
                        )
                        row_has_error = True

                # 7. Student count (optional integer)
                student_count = None
                if student_count_str:
                    try:
                        student_count = int(student_count_str)
                        if student_count <= 0:
                            warnings.append(
                                RowValidationError(
                                    filename=filename,
                                    row_number=row_num,
                                    field="student_count",
                                    message=f"Non-positive student count '{student_count}'.",
                                    severity="warning",
                                )
                            )
                    except ValueError:
                        warnings.append(
                            RowValidationError(
                                filename=filename,
                                row_number=row_num,
                                field="student_count",
                                message=f"Non-numeric student count '{student_count_str}' ignored.",
                                severity="warning",
                            )
                        )

                if row_has_error:
                    file_errors += 1
                else:
                    file_accepted += 1
                    file_programs.add(program_val)
                    file_cohorts.add(cohort)
                    detected_programs.add(program_val)
                    detected_cohorts.add(cohort)
                    detected_cycles.add(cycle_val)

                    sess_id = f"UPL-{session_counter:04d}"
                    session_counter += 1

                    all_normalized.append(
                        NormalizedUploadedSession(
                            session_id=sess_id,
                            run_id=run_id,
                            source_file=filename,
                            source_row=row_num,
                            program=program_val,
                            cohort_id=cohort,
                            course=course,
                            academic_cycle=cycle_val,
                            semester=sem_val,
                            session_type=session_type_val,
                            day=day_norm,
                            start_period=start_p,
                            end_period=end_p,
                            required_room_type=normalized_room_type,
                            required_facilities=facilities_val,
                            student_count=student_count,
                            assigned_room_id=None,
                        )
                    )

            files_summary.append(
                FileSummary(
                    filename=filename,
                    total_rows=row_num - 1,
                    accepted_rows=file_accepted,
                    error_count=file_errors,
                    warning_count=file_warnings,
                    detected_programs=sorted(list(file_programs)),
                    detected_cohorts=sorted(list(file_cohorts)),
                )
            )

        # 8. Cross-file cycle consistency check
        resolved_cycle = request.academic_cycle or ("odd" if "odd" in detected_cycles else "even")
        if len(detected_cycles) > 1 and not request.academic_cycle:
            errors.append(
                RowValidationError(
                    filename="CROSS_FILE_VALIDATION",
                    row_number=0,
                    field="academic_cycle",
                    message=(
                        f"Inconsistent academic cycles detected across uploaded files: {sorted(list(detected_cycles))}. "
                        f"A joint allocation run must operate on a single cycle ('odd' or 'even')."
                    ),
                    severity="error",
                )
            )

        # 9. Internal Cohort-Time Collision Check (Preflight hard constraint)
        cohort_slots: Dict[Tuple[str, str, int], List[NormalizedUploadedSession]] = {}
        for s in all_normalized:
            for p in s.period_range:
                key = (s.cohort_id, s.day, p)
                cohort_slots.setdefault(key, []).append(s)

        for (c_id, day, p), sessions_at_slot in cohort_slots.items():
            if len(sessions_at_slot) > 1:
                sess_info = ", ".join(f"{s.course} ({s.source_file}:R{s.source_row})" for s in sessions_at_slot)
                errors.append(
                    RowValidationError(
                        filename=sessions_at_slot[0].source_file,
                        row_number=sessions_at_slot[0].source_row,
                        field="cohort_collision",
                        message=(
                            f"Cohort overlap detected: Cohort '{c_id}' scheduled for multiple concurrent sessions "
                            f"on {day} period {p}: {sess_info}."
                        ),
                        severity="error",
                    )
                )

        has_blocking_errors = (len(errors) > 0) or (len(all_ambiguous) > 0)
        is_valid = (not has_blocking_errors) and (len(all_normalized) > 0)

        # Store context in memory registry if clean or partially valid
        context = UploadRunContext(
            run_id=run_id,
            academic_cycle=resolved_cycle,
            files=request.files,
            normalized_sessions=all_normalized,
        )
        self.register_run_context(context)

        return UploadPreflightResponse(
            run_id=run_id,
            academic_cycle=resolved_cycle,
            is_valid=is_valid,
            total_files=len(request.files),
            total_sessions_accepted=len(all_normalized),
            files_summary=files_summary,
            programs_detected=sorted(list(detected_programs)),
            cohorts_detected=sorted(list(detected_cohorts)),
            ambiguous_headers=all_ambiguous,
            errors=errors,
            warnings=warnings,
            sample_sessions=all_normalized[:10],
        )

    @staticmethod
    def to_session_models(normalized: List[NormalizedUploadedSession]) -> List[Session]:
        """Converts normalized upload sessions into standard domain Session models."""
        sessions: List[Session] = []
        for s in normalized:
            sessions.append(
                Session(
                    session_id=s.session_id,
                    academic_cycle=s.academic_cycle,
                    semester=s.semester,
                    program=s.program,
                    cohort_id=s.cohort_id,
                    course=s.course,
                    session_type=s.session_type,
                    day=s.day,
                    start_period=s.start_period,
                    end_period=s.end_period,
                    student_count=s.student_count,
                    required_room_type=s.required_room_type,
                    required_facilities=s.required_facilities,
                    assigned_room_id=s.assigned_room_id,
                    source_file=s.source_file,
                    source_page=f"Row {s.source_row}",
                    validation_status="unallocated_upload" if not s.assigned_room_id else "allocated_candidate",
                    notes=f"Uploaded from {s.source_file} (Run {s.run_id})",
                )
            )
        return sessions
