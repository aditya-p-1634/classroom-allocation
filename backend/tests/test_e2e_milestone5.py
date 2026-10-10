"""End-to-End Milestone 5 Verification Suite for ClassroomIQ.

Governed by Document 05 revision v0.2.6 and PAR-CIQ-P7-ADDENDUM-01.
Performs rigorous end-to-end testing of:
1. The five real Semester III raw timetable CSV input files:
   - computational_finance_semester_iii.csv
   - cyber_security_semester_iii.csv
   - data_science_semester_iii.csv
   - software_systems_semester_iii.csv
   - theoretical_computer_science_semester_iii.csv
2. Preflight validation, session extraction, and schema compliance.
3. Joint multi-program room allocation against the shared 86-room inventory.
4. Independent validator verification of hard constraints (zero clashes, room capabilities).
5. Timetable retrieval and multi-dimensional grouping (cohort, room, program).
6. Combined CSV export and ZIP package export integrity and audit certificates.
7. Distinguishing Synthetic Demo Profile vs. Factual Mode.
8. Truthful infeasibility diagnostics when resource contention exceeds inventory.
9. Error handling: invalid period bounds (outside 1-8), cohort collisions, unknown run IDs.
10. Regression safety: ensuring existing seed endpoints and core algorithms remain pristine.
"""

import io
import zipfile
from collections import defaultdict
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.schemas.upload import (
    RawFilePayload,
    UploadPreflightRequest,
    UploadAllocationRequest,
)
from backend.app.services.upload_service import UploadService
from backend.app.services.joint_allocation_service import JointAllocationService
from backend.app.services.export_service import ExportService
from backend.app.services.data_loader import DataLoaderService

FIXTURE_DIR = Path("test_fixtures/semester_iii_raw_timetables")
REAL_SEMESTER_III_FILES = [
    "computational_finance_semester_iii.csv",
    "cyber_security_semester_iii.csv",
    "data_science_semester_iii.csv",
    "software_systems_semester_iii.csv",
    "theoretical_computer_science_semester_iii.csv",
]


@pytest.fixture
def client():
    """FastAPI test client fixture."""
    return TestClient(app)


@pytest.fixture
def real_semester_iii_payloads():
    """Loads all 5 real Semester III CSV fixtures as RawFilePayloads."""
    payloads = []
    for fname in REAL_SEMESTER_III_FILES:
        fpath = FIXTURE_DIR / fname
        assert fpath.exists(), f"Required fixture {fname} not found in {FIXTURE_DIR}"
        content = fpath.read_text(encoding="utf-8")
        payloads.append(RawFilePayload(filename=fname, content=content))
    return payloads


# ==============================================================================
# 1. Real 5 Semester III Fixtures: Preflight, Ingestion & Provenance
# ==============================================================================

def test_e2e_real_semester_iii_preflight(client, real_semester_iii_payloads):
    """Verifies that all 5 real Semester III timetables pass preflight cleanly."""
    payload_dicts = [p.model_dump() for p in real_semester_iii_payloads]
    req_body = {
        "files": payload_dicts,
        "column_mappings": {},
        "confirmed_ambiguous_mappings": {},
    }
    
    resp = client.post("/api/upload/preflight", json=req_body)
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["is_valid"] is True
    assert data["total_files"] == 5
    assert data["total_sessions_accepted"] == 140
    assert data["academic_cycle"] == "odd"
    assert len(data["errors"]) == 0
    assert len(data["warnings"]) == 0
    assert len(data["ambiguous_headers"]) == 0

    # Verify all 5 programs and cohorts detected
    expected_programs = {
        "Computational Finance",
        "Cyber Security",
        "Data Science",
        "Software Systems",
        "Theoretical Computer Science",
    }
    assert set(data["programs_detected"]) == expected_programs

    expected_cohorts = {
        "odd_sem3_CF",
        "odd_sem3_CY",
        "odd_sem3_DS",
        "odd_sem3_SS",
        "odd_sem3_TCS",
    }
    assert set(data["cohorts_detected"]) == expected_cohorts

    # Verify each file's individual summary: exactly 28 sessions
    for f_sum in data["files_summary"]:
        assert f_sum["total_rows"] == 28
        assert f_sum["accepted_rows"] == 28
        assert f_sum["error_count"] == 0


def test_e2e_real_semester_iii_provenance_preservation(real_semester_iii_payloads):
    """Verifies that source filename and row numbers survive into normalized domain sessions."""
    svc = UploadService()
    preflight = svc.process_preflight(UploadPreflightRequest(files=real_semester_iii_payloads))
    run_ctx = svc.get_run_context(preflight.run_id)
    assert run_ctx is not None

    assert len(run_ctx.normalized_sessions) == 140
    for sess in run_ctx.normalized_sessions:
        assert sess.source_file in REAL_SEMESTER_III_FILES
        assert sess.source_row >= 2  # Row 1 is header
        assert 1 <= sess.start_period <= 8
        assert 1 <= sess.end_period <= 8
        assert sess.start_period <= sess.end_period
        assert sess.academic_cycle == "odd"
        assert sess.semester == "3"


# ==============================================================================
# 2. Joint Multi-Program Allocation & Hard Constraint Invariants
# ==============================================================================

def test_e2e_real_semester_iii_joint_allocation_synthetic(client, real_semester_iii_payloads):
    """Executes joint room allocation in Synthetic Demo Profile and validates zero clashes."""
    # Step A: Preflight
    payload_dicts = [p.model_dump() for p in real_semester_iii_payloads]
    preflight_resp = client.post("/api/upload/preflight", json={"files": payload_dicts})
    assert preflight_resp.status_code == 200
    run_id = preflight_resp.json()["run_id"]

    # Step B: Allocate
    alloc_req = {
        "run_id": run_id,
        "evaluation_mode": "synthetic",
        "time_limit_seconds": 10.0,
        "allow_computing_lab_exception": False,
    }
    alloc_resp = client.post("/api/upload/allocate", json=alloc_req)
    assert alloc_resp.status_code == 200, alloc_resp.text
    alloc_data = alloc_resp.json()

    # Verify allocation KPIs
    assert alloc_data["status"] == "completed"
    assert alloc_data["selected_allocator"] == "CPSATRoomOptimizer"
    assert alloc_data["fallback_to_baseline"] is False
    assert alloc_data["total_sessions"] == 140
    assert alloc_data["assigned_count"] == 140
    assert alloc_data["unassigned_count"] == 0
    assert alloc_data["assignments_count"] == 140
    assert alloc_data["evaluation_mode"] == "synthetic"
    assert alloc_data["evaluation_mode_label"] == "SYNTHETIC DEMO PROFILE"
    assert alloc_data["validation"]["is_valid"] is True

    # Step C: Independent Invariant Verification
    snapshot = DataLoaderService().load_snapshot()
    rooms_map = {r.room_id: r for r in snapshot.rooms}
    run_ctx = UploadService.get_run_context(run_id)

    room_time_occupancy = defaultdict(list)
    cohort_time_occupancy = defaultdict(list)

    for sess in run_ctx.normalized_sessions:
        room_id = run_ctx.allocated_assignments.get(sess.session_id)
        assert room_id is not None, f"Session {sess.session_id} not allocated"
        room = rooms_map[room_id]

        # Verify Room Capability
        if sess.required_room_type == "laboratory":
            assert room.room_type == "laboratory", (
                f"Lab session {sess.session_id} placed in non-lab room {room_id} ({room.room_type})"
            )
        elif sess.required_room_type == "classroom":
            assert room.room_type in {"classroom", "assembly_hall"}, (
                f"Classroom session {sess.session_id} placed in room {room_id} ({room.room_type})"
            )

        # Check Room-Time & Cohort-Time Exclusivity
        for period in range(sess.start_period, sess.end_period + 1):
            rt_key = (room_id, sess.day, period)
            ct_key = (sess.cohort_id, sess.day, period)
            room_time_occupancy[rt_key].append(sess.session_id)
            cohort_time_occupancy[ct_key].append(sess.session_id)

    # Invariant 1: Zero Room Double-Bookings
    room_clashes = {k: v for k, v in room_time_occupancy.items() if len(v) > 1}
    assert len(room_clashes) == 0, f"Detected room double-bookings: {room_clashes}"

    # Invariant 2: Zero Cohort Overlaps
    cohort_clashes = {k: v for k, v in cohort_time_occupancy.items() if len(v) > 1}
    assert len(cohort_clashes) == 0, f"Detected cohort time clashes: {cohort_clashes}"


def test_e2e_real_semester_iii_joint_allocation_factual_mode(client, real_semester_iii_payloads):
    """Executes joint room allocation in Factual Mode, validating that unverified facts are flagged."""
    payload_dicts = [p.model_dump() for p in real_semester_iii_payloads]
    preflight_resp = client.post("/api/upload/preflight", json={"files": payload_dicts})
    run_id = preflight_resp.json()["run_id"]

    alloc_req = {
        "run_id": run_id,
        "evaluation_mode": "factual",
        "time_limit_seconds": 10.0,
    }
    alloc_resp = client.post("/api/upload/allocate", json=alloc_req)
    assert alloc_resp.status_code == 200
    alloc_data = alloc_resp.json()

    assert alloc_data["status"] == "completed"
    assert alloc_data["evaluation_mode"] == "factual"
    assert alloc_data["evaluation_mode_label"] == "FACTUAL MODE"
    
    # Evidence limitations must be truthfully reported in Factual Mode
    evidence_lims = alloc_data["validation"].get("evidence_limitations", [])
    assert len(evidence_lims) > 0
    assert any("Capacity feasibility unverified" in lim for lim in evidence_lims)
    assert any("physical room operational availability" in lim.lower() for lim in evidence_lims)


# ==============================================================================
# 3. Interactive Timetable Explorer API
# ==============================================================================

def test_e2e_real_semester_iii_timetable_grid_inspection(client, real_semester_iii_payloads):
    """Verifies retrieval of allocated timetable grid across cohort, room, and program groupings."""
    payload_dicts = [p.model_dump() for p in real_semester_iii_payloads]
    preflight_resp = client.post("/api/upload/preflight", json={"files": payload_dicts})
    run_id = preflight_resp.json()["run_id"]

    client.post(
        "/api/upload/allocate",
        json={"run_id": run_id, "evaluation_mode": "synthetic", "time_limit_seconds": 5.0},
    )

    # Test Cohort Grouping
    tt_resp = client.get(f"/api/upload/timetable/{run_id}?group_by=cohort&day=Monday")
    assert tt_resp.status_code == 200
    tt_data = tt_resp.json()
    assert tt_data["target_day"] == "Monday"
    assert tt_data["group_by"] == "cohort"
    assert len(tt_data["row_keys"]) == 5  # 5 cohorts
    assert set(tt_data["cohorts"]) == {"odd_sem3_CF", "odd_sem3_CY", "odd_sem3_DS", "odd_sem3_SS", "odd_sem3_TCS"}
    assert tt_data["periods"] == [1, 2, 3, 4, 5, 6, 7, 8]

    # Verify Session Tile Provenance in Grid
    grid = tt_data["grid"]
    first_cohort = tt_data["row_keys"][0]
    cell_sessions = grid[first_cohort]["1"]  # Period 1
    assert len(cell_sessions) > 0
    cell = cell_sessions[0]
    assert cell["assigned_room_id"] is not None
    assert cell["source_file"] in REAL_SEMESTER_III_FILES
    assert "Row" in cell["source_page"]

    # Test Room Grouping
    room_tt = client.get(f"/api/upload/timetable/{run_id}?group_by=room&day=Tuesday")
    assert room_tt.status_code == 200
    assert room_tt.json()["group_by"] == "room"

    # Test Program Grouping
    prog_tt = client.get(f"/api/upload/timetable/{run_id}?group_by=program&day=Wednesday")
    assert prog_tt.status_code == 200
    assert prog_tt.json()["group_by"] == "program"


# ==============================================================================
# 4. Export Engine & Deliverable Package Integrity
# ==============================================================================

def test_e2e_real_semester_iii_exports(client, real_semester_iii_payloads):
    """Verifies combined CSV export and full ZIP deliverable package containing all files."""
    payload_dicts = [p.model_dump() for p in real_semester_iii_payloads]
    preflight_resp = client.post("/api/upload/preflight", json={"files": payload_dicts})
    run_id = preflight_resp.json()["run_id"]

    client.post(
        "/api/upload/allocate",
        json={"run_id": run_id, "evaluation_mode": "synthetic", "time_limit_seconds": 5.0},
    )

    # 1. Test Combined CSV Export
    csv_resp = client.get(f"/api/upload/export/{run_id}?format=csv")
    assert csv_resp.status_code == 200
    assert "text/csv" in csv_resp.headers["content-type"]
    csv_text = csv_resp.text
    lines = csv_text.strip().splitlines()
    assert len(lines) == 141  # 1 header + 140 sessions
    header = lines[0]
    assert "session_id,source_file,source_row,program,cohort_id,course" in header
    assert "assigned_room_id,allocation_status" in header

    # Verify no session is missing an assigned room
    for line in lines[1:]:
        fields = line.split(",")
        assigned_room = fields[15]
        status = fields[16]
        assert assigned_room != "", f"Missing room in export: {line}"
        assert status == "allocated", f"Invalid status in export: {line}"

    # 2. Test Complete ZIP Package Export
    zip_resp = client.get(f"/api/upload/export/{run_id}?format=zip")
    assert zip_resp.status_code == 200
    assert "application/zip" in zip_resp.headers["content-type"]

    with zipfile.ZipFile(io.BytesIO(zip_resp.content)) as z:
        names = z.namelist()
        # Should contain: combined CSV, 5 program CSVs, 5 source CSVs, 1 audit certificate = 12 files
        assert len(names) == 12

        # Check for Audit Certificate
        cert_names = [n for n in names if "ClassroomIQ_Audit_Certificate" in n]
        assert len(cert_names) == 1
        cert_text = z.read(cert_names[0]).decode("utf-8")
        assert run_id in cert_text
        assert "Total Uploaded Sessions: 140" in cert_text
        assert "Successfully Allocated:  140" in cert_text
        assert "Unassigned Sessions:     0" in cert_text
        assert "Hard Constraint Integrity:    PASS (0 hard violations)" in cert_text

        # Check for Program Timetables
        assert "programs/Computational_Finance_timetable.csv" in names
        assert "programs/Cyber_Security_timetable.csv" in names
        assert "programs/Data_Science_timetable.csv" in names
        assert "programs/Software_Systems_timetable.csv" in names
        assert "programs/Theoretical_Computer_Science_timetable.csv" in names

        # Check for Source File Breakdown
        assert "source_files/computational_finance_semester_iii_allocated.csv" in names
        assert "source_files/cyber_security_semester_iii_allocated.csv" in names


# ==============================================================================
# 5. Error Handling & Infeasibility Truthfulness
# ==============================================================================

def test_e2e_error_handling_periods_outside_bounds(client):
    """Verifies that periods outside 1-8 are rejected by preflight validation."""
    invalid_csv = """program,cohort_id,course,academic_cycle,day,start_period,end_period,required_room_type
Data Science,odd_sem3_DS,Big Data Analytics,odd,Monday,1,9,classroom
"""
    req = {
        "files": [{"filename": "invalid_p9.csv", "content": invalid_csv}],
        "column_mappings": {},
        "confirmed_ambiguous_mappings": {},
    }
    resp = client.post("/api/upload/preflight", json=req)
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_valid"] is False
    assert len(data["errors"]) > 0
    err_msgs = [e["message"] for e in data["errors"]]
    assert any("out of bounds" in m.lower() for m in err_msgs)


def test_e2e_error_handling_ambiguous_department_header(client):
    """Verifies that an unconfirmed 'department' header requires explicit user confirmation."""
    dept_csv = """department,cohort_id,course,academic_cycle,day,start_period,end_period,required_room_type
Computer Science,odd_sem3_CS,Algorithms,odd,Monday,1,2,classroom
"""
    req = {
        "files": [{"filename": "dept.csv", "content": dept_csv}],
        "column_mappings": {},
        "confirmed_ambiguous_mappings": {},
    }
    resp = client.post("/api/upload/preflight", json=req)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["ambiguous_headers"]) == 1
    prompt = data["ambiguous_headers"][0]
    assert prompt["raw_header"] == "department"
    assert prompt["requires_confirmation"] is True


def test_e2e_error_handling_cohort_overlap(client):
    """Verifies that internal cohort time overlaps are caught and rejected by preflight."""
    overlap_csv = """program,cohort_id,course,academic_cycle,day,start_period,end_period,required_room_type
Cyber Security,odd_sem3_CY,Network Security,odd,Monday,1,3,classroom
Cyber Security,odd_sem3_CY,Cryptography,odd,Monday,2,4,classroom
"""
    req = {
        "files": [{"filename": "overlap.csv", "content": overlap_csv}],
        "column_mappings": {},
        "confirmed_ambiguous_mappings": {},
    }
    resp = client.post("/api/upload/preflight", json=req)
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_valid"] is False
    assert any("Cohort overlap detected" in e["message"] for e in data["errors"])


def test_e2e_error_handling_unknown_run_id(client):
    """Verifies 404 response when querying nonexistent run ID."""
    resp = client.get("/api/upload/timetable/NONEXISTENT-RUN-ID")
    assert resp.status_code == 404

    resp_export = client.get("/api/upload/export/NONEXISTENT-RUN-ID?format=csv")
    assert resp_export.status_code == 404


def test_e2e_truthful_infeasibility_reporting(client):
    """Verifies that infeasible resource contention reports partial/infeasible outcome truthfully."""
    # Create 25 simultaneous laboratory sessions on Monday period 1 (inventory only has 20 labs)
    rows = [
        "program,cohort_id,course,academic_cycle,day,start_period,end_period,required_room_type"
    ]
    for i in range(25):
        rows.append(f"Prog_{i},cohort_{i},Lab Course {i},odd,Monday,1,2,laboratory")
    infeasible_csv = "\n".join(rows)

    preflight_resp = client.post(
        "/api/upload/preflight",
        json={"files": [{"filename": "massive_labs.csv", "content": infeasible_csv}]},
    )
    assert preflight_resp.status_code == 200
    run_id = preflight_resp.json()["run_id"]

    alloc_resp = client.post(
        "/api/upload/allocate",
        json={"run_id": run_id, "evaluation_mode": "synthetic", "time_limit_seconds": 3.0},
    )
    assert alloc_resp.status_code == 200
    data = alloc_resp.json()

    # Must truthfully state infeasible status and identify unassigned sessions
    assert data["status"] in {"infeasible", "partial", "fallback"}
    assert data["unassigned_count"] > 0
    assert len(data["unassigned_session_ids"]) == data["unassigned_count"]
    assert data["infeasibility_diagnosis"] is not None
    assert "capacity exceeded" in data["infeasibility_diagnosis"].lower() or "unassigned" in data["infeasibility_diagnosis"].lower()


# ==============================================================================
# 6. Regression Integrity: Seed Data Endpoints Still Function Pristine
# ==============================================================================

def test_e2e_regression_existing_endpoints_functional(client):
    """Verifies that P4-P7 existing seed endpoints continue to function without degradation."""
    status_resp = client.get("/api/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "operational"
    assert status_resp.json()["dataset_summary"]["rooms_inventory_count"] == 86
    assert status_resp.json()["dataset_summary"]["total_sessions"] == 1250

    rooms_resp = client.get("/api/inventory/rooms")
    assert rooms_resp.status_code == 200
    assert len(rooms_resp.json()) == 86

    events_resp = client.get("/api/simulation/events")
    assert events_resp.status_code == 200
    assert len(events_resp.json()) >= 5
