"""Export Engine for ClassroomIQ Upload & Allocate Workflow.

Governed by Document 05 revision v0.2.6 and PAR-CIQ-P7-ADDENDUM-01.
Generates combined allocation CSVs, per-program CSV timetables,
per-source-file CSV timetables, truthful audit certificates, and
self-contained ZIP archives using the Python standard library.
"""

import csv
import io
import os
import re
import zipfile
from datetime import datetime
from typing import Dict, List, Optional, Any, Set, Tuple

from backend.app.schemas.upload import NormalizedUploadedSession
from backend.app.services.upload_service import UploadRunContext


# Canonical exported CSV columns per Document 05 v0.2.6 specification
CSV_COLUMNS: List[str] = [
    "session_id",
    "source_file",
    "source_row",
    "program",
    "cohort_id",
    "course",
    "academic_cycle",
    "semester",
    "session_type",
    "day",
    "start_period",
    "end_period",
    "required_room_type",
    "required_facilities",
    "student_count",
    "assigned_room_id",
    "allocation_status",
]

DAY_ORDER: Dict[str, int] = {
    "Monday": 1,
    "Tuesday": 2,
    "Wednesday": 3,
    "Thursday": 4,
    "Friday": 5,
}


def sanitize_filename(name: str, default: str = "item") -> str:
    """Sanitizes names derived from uploaded data to prevent path traversal and invalid characters."""
    # Strip any directory path components
    base = os.path.basename(name.replace("\\", "/"))
    # Remove leading dots to prevent hidden files
    base = base.lstrip(".")
    # Replace non-alphanumeric characters (except underscore, hyphen, and dot) with underscore
    cleaned = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", base)
    # Collapse multiple consecutive underscores
    cleaned = re.sub(r"_+", "_", cleaned)
    cleaned = cleaned.strip("._")
    return cleaned if cleaned else default


def make_unique_zip_entry(used_entries: Set[str], folder: str, filename: str) -> str:
    """Ensures each entry path in the ZIP archive is unique, preventing silent collisions."""
    base, ext = os.path.splitext(filename)
    path = f"{folder}/{filename}" if folder else filename
    counter = 1
    while path in used_entries:
        disambiguated = f"{base}_{counter}{ext}"
        path = f"{folder}/{disambiguated}" if folder else disambiguated
        counter += 1
    used_entries.add(path)
    return path


def _session_sort_key(s: NormalizedUploadedSession) -> Tuple[int, int, str, str, str]:
    """Chronological and cohort-based sort key for exported timetable rows."""
    return (
        DAY_ORDER.get(s.day, 99),
        s.start_period,
        s.program,
        s.cohort_id,
        s.session_id,
    )


class ExportService:
    """Produces downloadable allocation datasets and audit certificates for completed upload runs."""

    @staticmethod
    def _render_csv(sessions: List[NormalizedUploadedSession], assignments: Dict[str, str]) -> str:
        """Renders a list of normalized sessions into a standardized CSV string."""
        sorted_sessions = sorted(sessions, key=_session_sort_key)
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, lineterminator="\n")
        writer.writeheader()

        for s in sorted_sessions:
            assigned_room = assignments.get(s.session_id)
            if assigned_room:
                alloc_status = "allocated"
                room_val = assigned_room
            else:
                alloc_status = "unallocated"
                room_val = ""

            writer.writerow({
                "session_id": s.session_id,
                "source_file": s.source_file,
                "source_row": s.source_row,
                "program": s.program,
                "cohort_id": s.cohort_id,
                "course": s.course,
                "academic_cycle": s.academic_cycle,
                "semester": s.semester or "",
                "session_type": s.session_type or "",
                "day": s.day,
                "start_period": s.start_period,
                "end_period": s.end_period,
                "required_room_type": s.required_room_type,
                "required_facilities": s.required_facilities or "",
                "student_count": s.student_count if s.student_count is not None else "",
                "assigned_room_id": room_val,
                "allocation_status": alloc_status,
            })

        return output.getvalue()

    @classmethod
    def generate_combined_csv(cls, context: UploadRunContext) -> str:
        """Generates the combined allocation CSV across all programs and uploaded files."""
        if context.allocation_result is None:
            raise ValueError(f"Run '{context.run_id}' has not been allocated yet.")
        return cls._render_csv(context.normalized_sessions, context.allocated_assignments)

    @classmethod
    def generate_program_csv(cls, context: UploadRunContext, program: str) -> str:
        """Generates a dedicated timetable CSV for a specific degree program."""
        if context.allocation_result is None:
            raise ValueError(f"Run '{context.run_id}' has not been allocated yet.")
        program_sessions = [s for s in context.normalized_sessions if s.program == program]
        return cls._render_csv(program_sessions, context.allocated_assignments)

    @classmethod
    def generate_source_file_csv(cls, context: UploadRunContext, filename: str) -> str:
        """Generates an allocated timetable CSV preserving source-file boundaries."""
        if context.allocation_result is None:
            raise ValueError(f"Run '{context.run_id}' has not been allocated yet.")
        file_sessions = [s for s in context.normalized_sessions if s.source_file == filename]
        return cls._render_csv(file_sessions, context.allocated_assignments)

    @classmethod
    def generate_audit_certificate(cls, context: UploadRunContext) -> str:
        """Generates an authoritative, truthful plain-text audit certificate for the allocation run."""
        alloc_res = context.allocation_result
        if alloc_res is None:
            raise ValueError(f"Run '{context.run_id}' has not been allocated yet.")

        # Extract allocation metadata
        selected_allocator = alloc_res.get("selected_allocator", "Unknown")
        fallback_to_baseline = bool(alloc_res.get("fallback_to_baseline", False))
        evaluation_mode = alloc_res.get("evaluation_mode", "synthetic")
        is_synthetic = (evaluation_mode == "synthetic")
        mode_label = "SYNTHETIC DEMO PROFILE" if is_synthetic else "FACTUAL MODE"
        infeasibility_diagnosis = alloc_res.get("infeasibility_diagnosis")
        unassigned_ids: List[str] = alloc_res.get("unassigned_session_ids", [])

        # Metrics
        sel_metrics = alloc_res.get("metrics")
        base_metrics = alloc_res.get("baseline_metrics")
        sel_wt = getattr(sel_metrics, "total_walking_time_minutes", 0.0) if sel_metrics else 0.0
        base_wt = getattr(base_metrics, "total_walking_time_minutes", sel_wt) if base_metrics else sel_wt

        savings_min = max(0.0, base_wt - sel_wt) if not fallback_to_baseline else 0.0
        savings_pct = (savings_min / base_wt * 100.0) if base_wt > 0 and not fallback_to_baseline else 0.0

        # Totals
        total_sessions = len(context.normalized_sessions)
        assigned_count = total_sessions - len(unassigned_ids)
        completion_pct = round((assigned_count / total_sessions * 100.0), 1) if total_sessions > 0 else 0.0

        distinct_programs = sorted(list(set(s.program for s in context.normalized_sessions if s.program)))
        distinct_cohorts = sorted(list(set(s.cohort_id for s in context.normalized_sessions if s.cohort_id)))

        # Validation analysis
        val_summary = alloc_res.get("validation", {})
        is_valid = bool(val_summary.get("is_valid", False))
        is_complete = bool(val_summary.get("is_complete", False))
        findings = val_summary.get("findings", [])
        evidence_limitations = val_summary.get("evidence_limitations", [])

        room_collisions = sum(1 for f in findings if f.get("constraint") == "room_time_exclusivity" and f.get("status") == "fail")
        cohort_collisions = sum(1 for f in findings if f.get("constraint") == "cohort_time_exclusivity" and f.get("status") == "fail")
        capability_mismatches = sum(1 for f in findings if f.get("constraint") == "room_capability" and f.get("status") == "fail")
        capacity_failures = sum(1 for f in findings if f.get("constraint") == "capacity" and f.get("status") == "fail")

        # Outcome classification
        if unassigned_ids:
            overall_status = "PARTIAL / INFEASIBLE (CONSTRAINED)"
        elif fallback_to_baseline:
            overall_status = "COMPLETED WITH BASELINE-PROTECTION FALLBACK"
        else:
            overall_status = "COMPLETED WITH OPTIMIZER IMPROVEMENT"

        lines: List[str] = [
            "=" * 80,
            "                    CLASSROOMIQ JOINT ALLOCATION AUDIT CERTIFICATE",
            "=" * 80,
            f"Run Identifier:          {context.run_id}",
            f"Generated Timestamp:     {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"Academic Cycle:          {context.academic_cycle.upper()}",
            f"Evaluation Mode:         {mode_label} ({evaluation_mode})",
            f"Allocation Status:       {overall_status}",
            f"Selected Allocator:      {selected_allocator}",
            f"Baseline-Protection:     {'ACTIVE (Protected baseline retained)' if fallback_to_baseline else 'INACTIVE (Optimizer candidate adopted)'}",
            "",
            "-" * 80,
            "1. SESSION ASSIGNMENT TOTALS",
            "-" * 80,
            f"Total Uploaded Sessions: {total_sessions}",
            f"Successfully Allocated:  {assigned_count} ({completion_pct}%)",
            f"Unassigned Sessions:     {len(unassigned_ids)}",
            f"Degree Programs:         {len(distinct_programs)} ({', '.join(distinct_programs)})",
            f"Student Cohorts:         {len(distinct_cohorts)}",
            f"Source Files Processed:  {len(context.files)} ({', '.join(f.filename for f in context.files)})",
            "",
            "-" * 80,
            "2. WALKING TIME METRICS & EFFICIENCY COMPARISON",
            "-" * 80,
            f"Greedy Baseline Walking Time: {round(base_wt, 2)} minutes",
            f"Selected Allocation Walking:  {round(sel_wt, 2)} minutes",
            f"Walking Time Reduction:       {round(savings_min, 2)} minutes ({round(savings_pct, 2)}%)",
            f"Efficiency Provenance:        synthetic_prefix_proxy_minutes (symmetric campus graph)",
            "",
            "-" * 80,
            "3. INDEPENDENT VALIDATION AUDIT",
            "-" * 80,
            f"Hard Constraint Integrity:    {'PASS (0 hard violations)' if is_valid else 'FAIL (violations detected)'}",
            f"Completeness Guarantee:       {'COMPLETE (100% placed)' if is_complete else 'PARTIAL (unassigned sessions present)'}",
            f"Room-Time Collisions:         {room_collisions}",
            f"Cohort-Time Collisions:       {cohort_collisions}",
            f"Room Capability Mismatches:   {capability_mismatches}",
            f"Capacity Evaluation Status:   {capacity_failures} failures",
            "",
        ]

        if evidence_limitations:
            lines.append("Evidence Limitations & Governance Disclosures:")
            for lim in evidence_limitations:
                lines.append(f"  * {lim}")
            lines.append("")

        lines.extend([
            "-" * 80,
            "4. DIAGNOSIS & AFFECTED OCCURRENCES",
            "-" * 80,
        ])

        if unassigned_ids:
            lines.append("CAUTION: This allocation is NOT fully successful.")
            lines.append(f"Reason: {len(unassigned_ids)} session occurrences could not be accommodated.")
            if infeasibility_diagnosis:
                lines.append(f"Diagnosis: {infeasibility_diagnosis}")
            lines.append("")
            lines.append("Affected Unassigned Sessions:")
            unassigned_set = set(unassigned_ids)
            for s in context.normalized_sessions:
                if s.session_id in unassigned_set:
                    lines.append(
                        f"  - [{s.session_id}] {s.program} | {s.cohort_id} | {s.course} "
                        f"({s.day} P{s.start_period}-{s.end_period}, required '{s.required_room_type}', source: {s.source_file}:{s.source_row})"
                    )
            lines.append("")
        else:
            lines.append("STATUS: FULLY FEASIBLE ALLOCATION")
            lines.append(f"All {total_sessions} uploaded sessions were successfully placed without contention.")
            lines.append("")

        lines.extend([
            "=" * 80,
            "End of Audit Certificate — ClassroomIQ Allocation Engine (Document 05 v0.2.6)",
            "=" * 80,
        ])

        return "\n".join(lines)

    @classmethod
    def generate_zip_archive(cls, context: UploadRunContext) -> bytes:
        """Generates a complete ZIP archive containing all CSV files and the audit certificate."""
        if context.allocation_result is None:
            raise ValueError(f"Run '{context.run_id}' has not been allocated yet.")

        zip_buffer = io.BytesIO()
        used_entries: Set[str] = set()

        with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            # 1. Combined allocation CSV
            combined_csv = cls.generate_combined_csv(context)
            combined_filename = f"ClassroomIQ_Combined_Allocation_{sanitize_filename(context.run_id)}.csv"
            entry_path = make_unique_zip_entry(used_entries, "", combined_filename)
            zf.writestr(entry_path, combined_csv)

            # 2. Per-program CSV files
            distinct_programs = sorted(list(set(s.program for s in context.normalized_sessions if s.program)))
            for prog in distinct_programs:
                prog_csv = cls.generate_program_csv(context, prog)
                safe_prog = sanitize_filename(prog, default="program")
                prog_filename = f"{safe_prog}_timetable.csv"
                entry_path = make_unique_zip_entry(used_entries, "programs", prog_filename)
                zf.writestr(entry_path, prog_csv)

            # 3. Per-source-file CSV files
            distinct_files = sorted(list(set(s.source_file for s in context.normalized_sessions if s.source_file)))
            for src_file in distinct_files:
                file_csv = cls.generate_source_file_csv(context, src_file)
                base_name = os.path.splitext(sanitize_filename(src_file, default="file"))[0]
                file_filename = f"{base_name}_allocated.csv"
                entry_path = make_unique_zip_entry(used_entries, "source_files", file_filename)
                zf.writestr(entry_path, file_csv)

            # 4. Audit Certificate
            audit_cert = cls.generate_audit_certificate(context)
            cert_filename = f"ClassroomIQ_Audit_Certificate_{sanitize_filename(context.run_id)}.txt"
            entry_path = make_unique_zip_entry(used_entries, "", cert_filename)
            zf.writestr(entry_path, audit_cert)

        return zip_buffer.getvalue()
