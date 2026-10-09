"""Integration Tests for ClassroomIQ REST API Bridge (Phase P7)."""

import pytest
from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def test_health_check_endpoint():
    """Verifies that the health check endpoint returns 200 OK."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == "0.2.5"


def test_status_endpoint_data_integrity():
    """Verifies that the status endpoint confirms 7 CSV checksums and correct dataset counts."""
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "operational"
    assert data["governing_document_version"] == "0.2.5"
    assert data["p6_accepted_baseline_commit"] == "9f6fea2"
    assert data["benchmark_reference"] == "Image 2 (docs/ClassroomIQ_UI_Benchmark_Approved_Reference.jpg)"

    # Verify CSV checksum integrity
    gov = data["data_trust_and_governance"]
    assert gov["seven_csv_datasets_reviewed"] is True
    assert gov["all_checksums_verified"] is True
    assert gov["source_values_preserved"] is True
    assert gov["travel_time_is_proxy"] is True

    # Verify exact reconciled data dimensions
    summary = data["dataset_summary"]
    assert summary["total_sessions"] == 1250
    assert summary["odd_cycle_sessions"] == 680
    assert summary["even_cycle_sessions"] == 570
    assert summary["programs_count"] == 5
    assert summary["cohorts_count"] == 45
    assert summary["rooms_inventory_count"] == 86

    # Verify Schedule Slot Coverage metrics (Defect 1)
    slot_cov = summary["slot_coverage"]
    assert slot_cov["total_slots"] == 6880
    assert slot_cov["occupied_slots"] == 1490
    assert slot_cov["unscheduled_slots"] == 2990
    assert slot_cov["unknown_slots"] == 2400


def test_inventory_rooms_endpoint():
    """Verifies that /api/inventory/rooms returns exactly 86 physical rooms."""
    response = client.get("/api/inventory/rooms")
    assert response.status_code == 200
    rooms = response.json()
    assert len(rooms) == 86

    # Verify laboratory count
    labs = [r for r in rooms if r["room_type"] == "laboratory"]
    assert len(labs) == 20

    # Verify M601 is among laboratories
    m601 = next((r for r in labs if r["room_id"] == "M601"), None)
    assert m601 is not None


def test_inventory_programs_and_cohorts_endpoints():
    """Verifies the 5 programs and 45 cohorts."""
    resp_p = client.get("/api/inventory/programs")
    assert resp_p.status_code == 200
    programs = resp_p.json()
    assert len(programs) == 5

    resp_c = client.get("/api/inventory/cohorts")
    assert resp_c.status_code == 200
    cohorts = resp_c.json()
    assert len(cohorts) == 45


def test_inventory_sessions_cycles():
    """Verifies session filtering by cycle: 680 odd and 570 even."""
    resp_odd = client.get("/api/inventory/sessions?academic_cycle=odd")
    assert resp_odd.status_code == 200
    assert len(resp_odd.json()) == 680

    resp_even = client.get("/api/inventory/sessions?academic_cycle=even")
    assert resp_even.status_code == 200
    assert len(resp_even.json()) == 570


def test_inventory_timetable_grid():
    """Verifies that /api/inventory/timetables returns a populated weekly grid."""
    response = client.get("/api/inventory/timetables?academic_cycle=odd&day=Monday")
    assert response.status_code == 200
    data = response.json()
    assert data["academic_cycle"] == "odd"
    assert data["total_sessions_filtered"] == 145
    assert len(data["row_keys"]) > 0
    first_rk = data["row_keys"][0]
    assert first_rk in data["grid"]
    assert 1 in data["grid"][first_rk] or "1" in data["grid"][first_rk]


def test_allocation_baseline_execution():
    """Verifies greedy baseline allocation run via API."""
    payload = {"academic_cycle": "even", "allow_computing_lab_exception": False}
    response = client.post("/api/allocation/baseline", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["allocator_name"] == "BaselineGreedyAllocator"
    assert data["assigned_count"] == 570
    assert data["validation"]["is_valid"] is True


def test_allocation_compare_even_cycle_shows_improvement():
    """Verifies that Even cycle allocation comparison achieves >= 50% walking time reduction."""
    payload = {"academic_cycle": "even", "time_limit_seconds": 10.0}
    response = client.post("/api/allocation/compare", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["academic_cycle"] == "even"
    assert data["walking_time_reduction_percentage"] >= 50.0
    assert data["fallback_to_baseline"] is False
    assert data["improvement_achieved"] is True
    assert data["selected_allocator_name"] == "CPSATRoomOptimizer"


def test_allocation_compare_odd_cycle_preserves_baseline_protection():
    """Verifies that Odd cycle comparison preserves baseline fallback and truthful reporting."""
    payload = {"academic_cycle": "odd", "time_limit_seconds": 10.0}
    response = client.post("/api/allocation/compare", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["academic_cycle"] == "odd"
    assert data["baseline_walking_time"] == 1248.0
    # Selected walking time must be <= baseline (never worse)
    assert data["optimized_walking_time"] <= data["baseline_walking_time"]
    assert data["raw_solver_status"] in ["FEASIBLE", "OPTIMAL"]
    if data["fallback_to_baseline"]:
        assert data["selected_allocator_name"] == "BaselineGreedyAllocator_Retained"
        assert data["optimized_walking_time"] == 1248.0
        assert data["improvement_achieved"] is False
    else:
        assert data["selected_allocator_name"] == "CPSATRoomOptimizer"
        assert data["improvement_achieved"] is True


def test_validation_audit_baseline_target():
    """Verifies independent validator audit on greedy baseline allocation (P5) returns valid_complete."""
    payload = {"academic_cycle": "even", "target": "baseline"}
    response = client.post("/api/validation/audit", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["target"] == "baseline"
    assert data["status"] == "valid_complete"
    assert data["fail_count"] == 0
    assert data["total_sessions_checked"] == 570
    assert "room_time_exclusivity" in data["category_breakdown"]
    assert data["category_breakdown"]["room_capability"]["fail"] == 0


def test_validation_audit_source_target_truthfully_reports_anomalies():
    """Verifies independent validator audit on raw source timetable catches known room-type anomalies (Defect 3)."""
    payload = {"academic_cycle": "even", "target": "source"}
    response = client.post("/api/validation/audit", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["target"] == "source"
    assert data["status"] == "invalid_candidate"
    assert data["fail_count"] == 8
    assert data["category_breakdown"]["room_capability"]["fail"] == 8


def test_simulation_events_catalog():
    """Verifies simulation events list contains 5 documented events + 1 synthetic fixture."""
    response = client.get("/api/simulation/events")
    assert response.status_code == 200
    events = response.json()
    assert len(events) == 6
    evt_ids = [e["event_id"] for e in events]
    assert "EVT-DEMO-001" in evt_ids
    assert "EVT-SYNTH-CLOSURE-FEASIBLE" in evt_ids


def test_simulation_m601_infeasible_diagnosis():
    """Verifies that EVT-DEMO-001 (M601 lab closure) truthfully diagnoses infeasibility."""
    payload = {"event_id": "EVT-DEMO-001", "academic_cycle": "even"}
    response = client.post("/api/simulation/trigger", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "infeasible_repair"
    assert data["is_repaired"] is False
    assert "Mathematically infeasible to repair" in data["diagnosis_explanation"]
    assert data["rollback_verified"] is True


def test_simulation_feasible_closure_recovers():
    """Verifies that synthetic feasible classroom closure repairs successfully with 0 ripple."""
    payload = {"event_id": "EVT-SYNTH-CLOSURE-FEASIBLE", "academic_cycle": "even"}
    response = client.post("/api/simulation/trigger", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "repaired"
    assert data["is_repaired"] is True
    assert data["ripple_count"] == 0
    assert data["is_ripple_limit_satisfied"] is True


def test_simulation_rollback():
    """Verifies simulation rollback endpoint."""
    response = client.post("/api/simulation/rollback")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "rolled_back"
    assert data["success"] is True


def test_inventory_profile_endpoint():
    """Verifies synthetic demo profile documentation endpoint."""
    response = client.get("/api/inventory/profile")
    assert response.status_code == 200
    data = response.json()
    assert data["profile_name"] == "SYNTHETIC DEMO PROFILE"
    assert "classroom_capacity" in data["defaults"]
    assert data["defaults"]["classroom_capacity"] == 65


def test_inventory_room_detail_endpoint():
    """Verifies room detail endpoint returns weekly occupancy schedule and utilization."""
    response = client.get("/api/inventory/room-detail/M601?academic_cycle=even&mode=synthetic")
    assert response.status_code == 200
    data = response.json()
    assert data["room_id"] == "M601"
    assert data["room_type"] == "laboratory"
    assert "Block M" in data["building_block"]
    assert "schedule" in data
    assert "Monday" in data["schedule"]
    assert data["total_weekly_periods"] == 45


def test_inventory_timetable_allocation_source_baseline():
    """Verifies timetable grid updates room assignments when allocation_source=baseline."""
    response = client.get("/api/inventory/timetables?academic_cycle=even&allocation_source=baseline&day=Monday")
    assert response.status_code == 200
    data = response.json()
    assert data["allocation_source"] == "baseline"
    assert "Selected Baseline Allocation" in data["allocation_status_label"]
    assert len(data["days"]) == 5
    assert len(data["periods"]) == 9


def test_inventory_timetable_allocation_source_optimized_odd_preserves_fallback():
    """Verifies timetable grid handles allocation_source=optimized on odd cycle."""
    response = client.get("/api/inventory/timetables?academic_cycle=odd&allocation_source=optimized&day=Monday")
    assert response.status_code == 200
    data = response.json()
    assert data["allocation_source"] == "optimized"
    if data["is_fallback"]:
        assert "Safe Fallback" in data["allocation_status_label"]
    else:
        assert "Selected Optimized Allocation" in data["allocation_status_label"]


def test_validation_audit_synthetic_mode_passes_capacity():
    """Verifies that in synthetic demo profile, capacity evaluation passes cleanly."""
    payload = {"academic_cycle": "even", "target": "baseline", "mode": "synthetic"}
    response = client.post("/api/validation/audit", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "synthetic"
    assert data["status"] == "valid_complete"
    assert data["category_breakdown"]["capacity"]["fail"] == 0
    assert data["category_breakdown"]["capacity"]["pass"] > 0
    assert data["category_breakdown"]["capacity"]["insufficient_evidence"] == 0

