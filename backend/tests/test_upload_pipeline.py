"""Unit and Integration Tests for Milestone 1: Upload Schemas and Ingestion Service.

Governed by Document 05 revision v0.2.6 and PAR-CIQ-P7-ADDENDUM-01.
Tests period range bounds (1-8), ambiguous header confirmation, provenance,
cohort collision detection, and Session model domain compatibility.
"""

import pytest
from backend.app.schemas.models import Session
from backend.app.schemas.upload import (
    RawFilePayload,
    UploadPreflightRequest,
    UploadPreflightResponse,
    NormalizedUploadedSession,
)
from backend.app.services.upload_service import UploadService


SAMPLE_CYBER_CSV = """program,cohort_id,course,academic_cycle,day,start_period,end_period,required_room_type
M.Sc. Cyber Security,even_sem2_CY,Network Security Lab,even,Monday,1,2,laboratory
M.Sc. Cyber Security,even_sem2_CY,Discrete Math,even,Monday,3,3,classroom
M.Sc. Cyber Security,even_sem2_CY,Applied Cryptography,even,Tuesday,1,2,classroom
"""

SAMPLE_SOFTWARE_CSV = """program,cohort_id,course,academic_cycle,day,start_period,end_period,required_room_type
M.Sc. Software Systems,even_sem2_SS,Cloud Computing,even,Monday,1,2,classroom
M.Sc. Software Systems,even_sem2_SS,Database Lab,even,Monday,3,4,laboratory
"""


def test_unallocated_session_model_defaults():
    """Verifies that Session domain model allows assigned_room_id to be None."""
    sess = Session(
        session_id="TEST_001",
        academic_cycle="even",
        semester="2",
        program="Cyber Security",
        cohort_id="even_sem2_CY",
        course="Network Security",
        session_type="lecture",
        day="Monday",
        start_period=1,
        end_period=2,
        required_room_type="classroom",
    )
    assert sess.assigned_room_id is None
    assert sess.session_id == "TEST_001"
    assert sess.duration_periods == 2
    assert sess.period_range == [1, 2]


def test_upload_service_valid_csv_parsing_multi_file():
    """Verifies parsing two distinct program timetables into normalized sessions."""
    svc = UploadService()
    req = UploadPreflightRequest(
        files=[
            RawFilePayload(filename="cyber_sec.csv", content=SAMPLE_CYBER_CSV),
            RawFilePayload(filename="software_sys.csv", content=SAMPLE_SOFTWARE_CSV),
        ]
    )
    res = svc.process_preflight(req)

    assert res.is_valid is True
    assert res.total_files == 2
    assert res.total_sessions_accepted == 5
    assert len(res.errors) == 0
    assert "M.Sc. Cyber Security" in res.programs_detected
    assert "M.Sc. Software Systems" in res.programs_detected
    assert "even_sem2_CY" in res.cohorts_detected
    assert "even_sem2_SS" in res.cohorts_detected

    # Verify provenance and stable session IDs
    assert res.sample_sessions[0].session_id == "UPL-0001"
    assert res.sample_sessions[0].source_file == "cyber_sec.csv"
    assert res.sample_sessions[0].source_row == 2
    assert res.sample_sessions[0].assigned_room_id is None


def test_upload_service_enforces_period_1_to_8_bounds():
    """Verifies that periods outside 1-8 (e.g. period 9) are rejected with line-level diagnostics."""
    bad_csv = """program,cohort_id,course,academic_cycle,day,start_period,end_period,required_room_type
M.Sc. Cyber Security,even_sem2_CY,Evening Capstone,even,Monday,8,9,laboratory
"""
    svc = UploadService()
    req = UploadPreflightRequest(
        files=[RawFilePayload(filename="bad_period.csv", content=bad_csv)]
    )
    res = svc.process_preflight(req)

    assert res.is_valid is False
    assert len(res.errors) > 0
    err = next(e for e in res.errors if e.field == "periods")
    assert err.row_number == 2
    assert err.filename == "bad_period.csv"
    assert "Period-9 scheduling is not permitted in raw CSV uploads" in err.message


def test_upload_service_ambiguous_department_header_requires_confirmation():
    """Verifies that 'department' header is not silently mapped to program without confirmation."""
    dept_csv = """department,cohort_id,course,academic_cycle,day,start_period,end_period,required_room_type
Cyber Security Dept,even_sem2_CY,Math Lab,even,Monday,1,2,laboratory
"""
    svc = UploadService()
    req = UploadPreflightRequest(
        files=[RawFilePayload(filename="dept_file.csv", content=dept_csv)]
    )
    res = svc.process_preflight(req)

    # Must require explicit confirmation
    assert res.is_valid is False
    assert len(res.ambiguous_headers) == 1
    amb = res.ambiguous_headers[0]
    assert amb.raw_header == "department"
    assert amb.suggested_field == "program"
    assert amb.requires_confirmation is True


def test_upload_service_confirmed_ambiguous_header_resolves():
    """Verifies that once user confirms ambiguous mapping, preflight validation succeeds."""
    dept_csv = """department,cohort_id,course,academic_cycle,day,start_period,end_period,required_room_type
M.Sc. Cyber Security,even_sem2_CY,Math Lab,even,Monday,1,2,laboratory
"""
    svc = UploadService()
    req = UploadPreflightRequest(
        files=[RawFilePayload(filename="dept_file.csv", content=dept_csv)],
        confirmed_ambiguous_mappings={"dept_file.csv": {"department": "program"}},
    )
    res = svc.process_preflight(req)

    assert res.is_valid is True
    assert len(res.ambiguous_headers) == 0
    assert res.total_sessions_accepted == 1
    assert res.sample_sessions[0].program == "M.Sc. Cyber Security"


def test_upload_service_strict_room_type_rejection():
    """Verifies that missing or unmapped room types are rejected rather than silently guessed."""
    no_room_csv = """program,cohort_id,course,academic_cycle,day,start_period,end_period,required_room_type
M.Sc. Cyber Security,even_sem2_CY,Physics Lecture,even,Monday,1,2,
"""
    svc = UploadService()
    req = UploadPreflightRequest(
        files=[RawFilePayload(filename="no_room.csv", content=no_room_csv)]
    )
    res = svc.process_preflight(req)

    assert res.is_valid is False
    err = next(e for e in res.errors if e.field == "required_room_type")
    assert "Silent inference from course names is prohibited" in err.message


def test_upload_service_internal_cohort_overlap_rejection():
    """Verifies preflight catches internal cohort collisions where one cohort is double-booked."""
    overlapping_csv = """program,cohort_id,course,academic_cycle,day,start_period,end_period,required_room_type
M.Sc. Cyber Security,even_sem2_CY,Operating Systems,even,Monday,1,2,classroom
M.Sc. Cyber Security,even_sem2_CY,Computer Networks,even,Monday,2,3,classroom
"""
    svc = UploadService()
    req = UploadPreflightRequest(
        files=[RawFilePayload(filename="overlap.csv", content=overlapping_csv)]
    )
    res = svc.process_preflight(req)

    assert res.is_valid is False
    err = next(e for e in res.errors if e.field == "cohort_collision")
    assert "Cohort overlap detected" in err.message
    assert "even_sem2_CY" in err.message


def test_upload_service_to_session_models_conversion():
    """Verifies NormalizedUploadedSession models convert seamlessly to domain Session models."""
    svc = UploadService()
    req = UploadPreflightRequest(
        files=[RawFilePayload(filename="cyber.csv", content=SAMPLE_CYBER_CSV)]
    )
    res = svc.process_preflight(req)
    assert res.is_valid is True

    domain_sessions = svc.to_session_models(res.sample_sessions)
    assert len(domain_sessions) == 3
    for s in domain_sessions:
        assert isinstance(s, Session)
        assert s.assigned_room_id is None
        assert s.validation_status == "unallocated_upload"
        assert s.start_period >= 1
        assert s.end_period <= 8
