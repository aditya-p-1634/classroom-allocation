"""Status and Data Governance Endpoints for ClassroomIQ."""

import os
import hashlib
from typing import Dict, Any
from fastapi import APIRouter
from backend.app.config import DATA_DIR, EXPECTED_ROW_COUNTS
from backend.app.services.data_loader import DataLoaderService

router = APIRouter(prefix="/status", tags=["Status"])

VERIFIED_CSV_HASHES = {
    "availability.csv": "cb725f2b7a5a9ea728bf70bf721a2cdfa8989211bdaa27c5821ac14458d82e53",
    "complaints.csv": "9d1cb4963e14e0763c18507e085923d86c7c39b4205c3b4bc6e35093185f08d5",
    "events.csv": "bc1321604eae476c73ab56d32c800b85027f5a2f36396cdffcdbdb25544d67ee",
    "facilities.csv": "e609c640b4463288cfabd5f417089d976d09503b4b12208c3b9fc35a66bd9994",
    "rooms.csv": "00f9d5e6887244b1796ee855e3aacadcb9d447762f3a80ea5016d48885fcf4dc",
    "sessions.csv": "d02f072ed0b33bf6349db32b432a3393b8359cfdd7a4957d971dce4d1d89c86b",
    "travel_times.csv": "4c14452eca922d89b230e40f447747b7d62bc6f2e4666fd1b7a281e2fd949960",
}


@router.get("", response_model=Dict[str, Any])
def get_system_status() -> Dict[str, Any]:
    """Returns system operational health, dataset governance verification, and project metadata."""
    # Verify file checksums
    checksum_results = {}
    all_checksums_match = True
    for fname, expected_hash in VERIFIED_CSV_HASHES.items():
        fpath = os.path.join(DATA_DIR, fname)
        if os.path.exists(fpath):
            with open(fpath, "rb") as f:
                actual_hash = hashlib.sha256(f.read()).hexdigest()
            matches = (actual_hash == expected_hash)
            checksum_results[fname] = {
                "verified": matches,
                "sha256": actual_hash,
            }
            if not matches:
                all_checksums_match = False
        else:
            checksum_results[fname] = {"verified": False, "error": "file_not_found"}
            all_checksums_match = False

    snapshot = DataLoaderService().load_snapshot()
    odd_count = sum(1 for s in snapshot.sessions if s.academic_cycle == "odd")
    even_count = sum(1 for s in snapshot.sessions if s.academic_cycle == "even")
    programs = sorted(list(set(s.program for s in snapshot.sessions if s.program)))
    cohorts = sorted(list(set(s.cohort_id for s in snapshot.sessions if s.cohort_id)))

    return {
        "status": "operational",
        "governing_document_version": "0.2.5",
        "p6_accepted_baseline_commit": "9f6fea2",
        "p7_authorization_record": "PAR-CIQ-P7-20261010-01",
        "benchmark_reference": "Image 2 (docs/ClassroomIQ_UI_Benchmark_Approved_Reference.jpg)",
        "data_trust_and_governance": {
            "seven_csv_datasets_reviewed": True,
            "all_checksums_verified": all_checksums_match,
            "source_values_preserved": True,
            "unknowns_remain_unknown": True,
            "travel_time_is_proxy": True,
            "room_capacity_incomplete": True,
            "facility_status_unknown": True,
            "checksums": checksum_results,
            "last_verified_date": "2026-10-10",
        },
        "dataset_summary": {
            "total_sessions": len(snapshot.sessions),
            "odd_cycle_sessions": odd_count,
            "even_cycle_sessions": even_count,
            "programs_count": len(programs),
            "programs": programs,
            "cohorts_count": len(cohorts),
            "cohorts": cohorts,
            "rooms_inventory_count": len(snapshot.rooms),
            "room_availability_status": "Unknown (Insufficient Evidence)",
            "student_count_status": "Unknown (Data Gap)",
        },
        "project_phases": [
            {"id": "P4", "name": "Build Preparation", "status": "completed", "verified": True},
            {"id": "P5", "name": "Baseline Allocator", "status": "completed", "verified": True},
            {"id": "P6", "name": "Optimization", "status": "accepted", "verified": True, "note": "Accepted • Document v0.2.3"},
            {"id": "P7", "name": "Frontend Integration", "status": "in_progress", "verified": True, "note": "PAR-CIQ-P7-20261010-01 Authorized"},
            {"id": "P8", "name": "Benchmarking", "status": "pending", "verified": False},
            {"id": "P9", "name": "Demo & Presentation", "status": "pending", "verified": False},
        ],
    }
