"""Deterministic Dataset Ingestion Service for ClassroomIQ.

Reads the seven seed CSV datasets from data/ into typed Pydantic models.
Preserves raw values, tracks missing/unknown fields, and reports ingestion metrics.
Never modifies original files or silently discards records.
"""

import csv
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any

from backend.app.config import (
    DATA_DIR,
    ROOMS_FILENAME,
    FACILITIES_FILENAME,
    SESSIONS_FILENAME,
    AVAILABILITY_FILENAME,
    TRAVEL_TIMES_FILENAME,
    EVENTS_FILENAME,
    COMPLAINTS_FILENAME,
    EXPECTED_ROW_COUNTS,
)
from backend.app.schemas.models import (
    Room,
    Facility,
    Session,
    AvailabilityRecord,
    TravelTime,
    EventRecord,
    ComplaintRecord,
    DatasetSnapshot,
    IngestionReport,
)

logger = logging.getLogger(__name__)


def _clean_str(val: Optional[str]) -> Optional[str]:
    """Converts empty or whitespace-only strings to None, otherwise strips whitespace."""
    if val is None:
        return None
    cleaned = val.strip()
    return cleaned if cleaned else None


def _clean_int(val: Optional[str]) -> Optional[int]:
    """Converts a string representation to an integer, returning None if empty."""
    cleaned = _clean_str(val)
    if cleaned is None:
        return None
    try:
        return int(cleaned)
    except ValueError as exc:
        raise ValueError(f"Cannot cast '{val}' to integer: {exc}") from exc


def _clean_float(val: Optional[str]) -> float:
    """Converts a string representation to a float."""
    cleaned = _clean_str(val)
    if cleaned is None:
        raise ValueError("Cannot cast empty string to float.")
    return float(cleaned)


class DataLoaderService:
    """Service responsible for deterministic ingestion and validation of seed CSV files."""

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or DATA_DIR

    def _read_csv_rows(self, filename: str) -> List[Dict[str, str]]:
        """Reads CSV rows safely using utf-8-sig encoding."""
        filepath = self.data_dir / filename
        if not filepath.exists():
            raise FileNotFoundError(f"Required dataset file not found: {filepath}")

        rows = []
        with open(filepath, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
        return rows

    def load_rooms(self, report: Optional[IngestionReport] = None) -> List[Room]:
        """Loads and parses rooms.csv."""
        raw_rows = self._read_csv_rows(ROOMS_FILENAME)
        rooms: List[Room] = []
        for idx, row in enumerate(raw_rows, start=2):
            try:
                room = Room(
                    room_id=row["room_id"].strip(),
                    room_type=row["room_type"].strip(),
                    additional_uses=_clean_str(row.get("additional_uses")),
                    building_block=_clean_str(row.get("building_block")),
                    floor=_clean_str(row.get("floor")),
                    capacity=_clean_int(row.get("capacity")),
                    capacity_source=_clean_str(row.get("capacity_source")),
                    source_record=row["source_record"].strip(),
                    verification_status=row["verification_status"].strip(),
                    notes=row["notes"].strip(),
                )
                rooms.append(room)
            except Exception as e:
                msg = f"Error in {ROOMS_FILENAME} row {idx}: {e}"
                if report:
                    report.errors.append(msg)
                raise ValueError(msg) from e

        if report:
            report.files_loaded.append(ROOMS_FILENAME)
            report.record_counts[ROOMS_FILENAME] = len(rooms)
        return rooms

    def load_facilities(self, report: Optional[IngestionReport] = None) -> List[Facility]:
        """Loads and parses facilities.csv."""
        raw_rows = self._read_csv_rows(FACILITIES_FILENAME)
        facilities: List[Facility] = []
        for idx, row in enumerate(raw_rows, start=2):
            try:
                facility = Facility(
                    room_id=row["room_id"].strip(),
                    facility_type=row["facility_type"].strip(),
                    installation_status=row["installation_status"].strip(),
                    operational_status=row["operational_status"].strip(),
                    verification_status=row["verification_status"].strip(),
                    source=row["source"].strip(),
                    notes=row["notes"].strip(),
                )
                facilities.append(facility)
            except Exception as e:
                msg = f"Error in {FACILITIES_FILENAME} row {idx}: {e}"
                if report:
                    report.errors.append(msg)
                raise ValueError(msg) from e

        if report:
            report.files_loaded.append(FACILITIES_FILENAME)
            report.record_counts[FACILITIES_FILENAME] = len(facilities)
        return facilities

    def load_sessions(self, report: Optional[IngestionReport] = None) -> List[Session]:
        """Loads and parses sessions.csv."""
        raw_rows = self._read_csv_rows(SESSIONS_FILENAME)
        sessions: List[Session] = []
        for idx, row in enumerate(raw_rows, start=2):
            try:
                session = Session(
                    session_id=row["session_id"].strip(),
                    academic_cycle=row["academic_cycle"].strip(),
                    semester=row["semester"].strip(),
                    program=row["program"].strip(),
                    cohort_id=row["cohort_id"].strip(),
                    course=row["course"].strip(),
                    session_type=row["session_type"].strip(),
                    day=row["day"].strip(),
                    start_period=int(row["start_period"].strip()),
                    end_period=int(row["end_period"].strip()),
                    student_count=_clean_int(row.get("student_count")),
                    required_room_type=row["required_room_type"].strip(),
                    required_facilities=_clean_str(row.get("required_facilities")),
                    assigned_room_id=row["assigned_room_id"].strip(),
                    source_file=row["source_file"].strip(),
                    source_page=row["source_page"].strip(),
                    validation_status=row["validation_status"].strip(),
                    notes=row["notes"].strip(),
                )
                sessions.append(session)
            except Exception as e:
                msg = f"Error in {SESSIONS_FILENAME} row {idx}: {e}"
                if report:
                    report.errors.append(msg)
                raise ValueError(msg) from e

        if report:
            report.files_loaded.append(SESSIONS_FILENAME)
            report.record_counts[SESSIONS_FILENAME] = len(sessions)
        return sessions

    def load_availability(self, report: Optional[IngestionReport] = None) -> List[AvailabilityRecord]:
        """Loads and parses availability.csv."""
        raw_rows = self._read_csv_rows(AVAILABILITY_FILENAME)
        records: List[AvailabilityRecord] = []
        for idx, row in enumerate(raw_rows, start=2):
            try:
                rec = AvailabilityRecord(
                    room_id=row["room_id"].strip(),
                    academic_cycle=row["academic_cycle"].strip(),
                    day=row["day"].strip(),
                    period=int(row["period"].strip()),
                    status=row["status"].strip(),
                    session_id=_clean_str(row.get("session_id")),
                    source_status=row["source_status"].strip(),
                )
                records.append(rec)
            except Exception as e:
                msg = f"Error in {AVAILABILITY_FILENAME} row {idx}: {e}"
                if report:
                    report.errors.append(msg)
                raise ValueError(msg) from e

        if report:
            report.files_loaded.append(AVAILABILITY_FILENAME)
            report.record_counts[AVAILABILITY_FILENAME] = len(records)
        return records

    def load_travel_times(self, report: Optional[IngestionReport] = None) -> List[TravelTime]:
        """Loads and parses travel_times.csv."""
        raw_rows = self._read_csv_rows(TRAVEL_TIMES_FILENAME)
        records: List[TravelTime] = []
        for idx, row in enumerate(raw_rows, start=2):
            try:
                rec = TravelTime(
                    from_room_id=row["from_room_id"].strip(),
                    to_room_id=row["to_room_id"].strip(),
                    walking_time_minutes=_clean_float(row["walking_time_minutes"]),
                    source_status=row["source_status"].strip(),
                    notes=row["notes"].strip(),
                )
                records.append(rec)
            except Exception as e:
                msg = f"Error in {TRAVEL_TIMES_FILENAME} row {idx}: {e}"
                if report:
                    report.errors.append(msg)
                raise ValueError(msg) from e

        if report:
            report.files_loaded.append(TRAVEL_TIMES_FILENAME)
            report.record_counts[TRAVEL_TIMES_FILENAME] = len(records)
        return records

    def load_events(self, report: Optional[IngestionReport] = None) -> List[EventRecord]:
        """Loads and parses events.csv."""
        raw_rows = self._read_csv_rows(EVENTS_FILENAME)
        records: List[EventRecord] = []
        for idx, row in enumerate(raw_rows, start=2):
            try:
                rec = EventRecord(
                    event_id=row["event_id"].strip(),
                    room_id=row["room_id"].strip(),
                    academic_cycle=row["academic_cycle"].strip(),
                    start_day=row["start_day"].strip(),
                    start_period=int(row["start_period"].strip()),
                    end_day=row["end_day"].strip(),
                    end_period=int(row["end_period"].strip()),
                    event_type=row["event_type"].strip(),
                    description=row["description"].strip(),
                    status=row["status"].strip(),
                    source_status=row["source_status"].strip(),
                    related_session_id=row["related_session_id"].strip(),
                )
                records.append(rec)
            except Exception as e:
                msg = f"Error in {EVENTS_FILENAME} row {idx}: {e}"
                if report:
                    report.errors.append(msg)
                raise ValueError(msg) from e

        if report:
            report.files_loaded.append(EVENTS_FILENAME)
            report.record_counts[EVENTS_FILENAME] = len(records)
        return records

    def load_complaints(self, report: Optional[IngestionReport] = None) -> List[ComplaintRecord]:
        """Loads and parses complaints.csv."""
        raw_rows = self._read_csv_rows(COMPLAINTS_FILENAME)
        records: List[ComplaintRecord] = []
        for idx, row in enumerate(raw_rows, start=2):
            try:
                rec = ComplaintRecord(
                    complaint_id=row["complaint_id"].strip(),
                    location_type=row["location_type"].strip(),
                    location_id=row["location_id"].strip(),
                    reporter_role=row["reporter_role"].strip(),
                    issue_type=row["issue_type"].strip(),
                    description=row["description"].strip(),
                    assigned_department=row["assigned_department"].strip(),
                    priority=row["priority"].strip(),
                    status=row["status"].strip(),
                    resolution=_clean_str(row.get("resolution")),
                    created_at=row["created_at"].strip(),
                    updated_at=row["updated_at"].strip(),
                    source_status=row["source_status"].strip(),
                )
                records.append(rec)
            except Exception as e:
                msg = f"Error in {COMPLAINTS_FILENAME} row {idx}: {e}"
                if report:
                    report.errors.append(msg)
                raise ValueError(msg) from e

        if report:
            report.files_loaded.append(COMPLAINTS_FILENAME)
            report.record_counts[COMPLAINTS_FILENAME] = len(records)
        return records

    def load_snapshot(self) -> DatasetSnapshot:
        """Loads all seven CSV datasets into a single validated DatasetSnapshot."""
        report = IngestionReport()
        rooms = self.load_rooms(report)
        facilities = self.load_facilities(report)
        sessions = self.load_sessions(report)
        availability = self.load_availability(report)
        travel_times = self.load_travel_times(report)
        events = self.load_events(report)
        complaints = self.load_complaints(report)

        # Verify expected row counts
        for filename, expected in EXPECTED_ROW_COUNTS.items():
            actual = report.record_counts.get(filename, 0)
            if actual != expected:
                report.warnings.append(
                    f"Row count mismatch in {filename}: expected {expected}, actual {actual}"
                )

        report.is_success = len(report.errors) == 0

        return DatasetSnapshot(
            rooms=rooms,
            facilities=facilities,
            sessions=sessions,
            availability=availability,
            travel_times=travel_times,
            events=events,
            complaints=complaints,
            report=report,
        )
