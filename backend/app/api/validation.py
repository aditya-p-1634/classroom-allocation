"""Independent Validator Audit Endpoints."""

from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from fastapi import APIRouter
from backend.app.services.data_loader import DataLoaderService
from backend.app.core.validator import IndependentValidator
from backend.app.schemas.validation import AllocationCandidate, ConstraintCategory, FindingStatus

router = APIRouter(prefix="/validation", tags=["Validation Inspector"])


class AuditRequest(BaseModel):
    academic_cycle: str = Field("even", description="'odd' or 'even'")
    target: str = Field("baseline", description="'source', 'baseline', 'optimizer', or 'custom'")
    assignments: Optional[Dict[str, str]] = Field(None, description="Optional assignment map to audit")
    allow_computing_lab_exception: bool = Field(False, description="Whether to allow computing lab exception")
    time_limit_seconds: float = Field(10.0, ge=1.0, le=10.0, description="Solver time limit if target is optimizer")
    mode: str = Field("factual", description="'synthetic' or 'factual'")


@router.post("/audit", response_model=Dict[str, Any])
def audit_allocation(req: AuditRequest) -> Dict[str, Any]:
    """Independently audits an allocation candidate or source timetable against hard constraints and mode profile."""
    from backend.app.config import CapacityPolicyMode
    from backend.app.services.synthetic_profile import SyntheticProfileService

    snapshot = DataLoaderService().load_snapshot()
    if req.mode == "synthetic":
        syn_caps = SyntheticProfileService.build_synthetic_room_capacities_map(snapshot)
        syn_demands = SyntheticProfileService.build_synthetic_session_demands_map(snapshot)
        validator = IndependentValidator(
            snapshot=snapshot,
            capacity_mode=CapacityPolicyMode.SYNTHETIC_EVALUATION,
            allow_computing_lab_exception=req.allow_computing_lab_exception,
            synthetic_room_capacities=syn_caps,
            synthetic_session_demands=syn_demands,
        )
    else:
        validator = IndependentValidator(
            snapshot=snapshot,
            capacity_mode=CapacityPolicyMode.FACTUAL,
            allow_computing_lab_exception=req.allow_computing_lab_exception,
        )

    target_display_name = "Custom Candidate Allocation"
    if req.assignments is not None:
        candidate = AllocationCandidate(
            academic_cycle=req.academic_cycle,
            assignments=req.assignments,
        )
        target_display_name = f"Custom Submitted Allocation • {req.academic_cycle.upper()} Cycle"
    elif req.target == "baseline":
        from backend.app.services.allocation_service import AllocationService
        service = AllocationService()
        base_res = service.run_baseline_allocation(
            academic_cycle=req.academic_cycle,
            allow_computing_lab_exception=req.allow_computing_lab_exception,
        )
        candidate = base_res.candidate
        target_display_name = f"Greedy Baseline Allocation (P5) • {req.academic_cycle.upper()} Cycle"
    elif req.target == "optimizer":
        from backend.app.services.allocation_service import AllocationService
        service = AllocationService()
        opt_res = service.run_optimized_allocation(
            academic_cycle=req.academic_cycle,
            allow_computing_lab_exception=req.allow_computing_lab_exception,
            time_limit_seconds=req.time_limit_seconds,
        )
        candidate = opt_res.candidate
        target_display_name = f"CP-SAT Optimized Allocation (P6) • {req.academic_cycle.upper()} Cycle"
    else:  # source
        cycle_sessions = [s for s in snapshot.sessions if s.academic_cycle == req.academic_cycle]
        source_assignments = {s.session_id: s.assigned_room_id for s in cycle_sessions if s.assigned_room_id}
        candidate = AllocationCandidate(
            academic_cycle=req.academic_cycle,
            assignments=source_assignments,
        )
        target_display_name = f"Original Source Timetable (Seed Data) • {req.academic_cycle.upper()} Cycle"

    summary = validator.validate_candidate(candidate)

    # Category breakdown
    category_breakdown: Dict[str, Dict[str, int]] = {
        c.value: {"pass": 0, "fail": 0, "insufficient_evidence": 0}
        for c in ConstraintCategory
    }
    for f in summary.findings:
        cat_key = f.constraint.value
        status_key = f.status.value
        if cat_key in category_breakdown and status_key in category_breakdown[cat_key]:
            category_breakdown[cat_key][status_key] += 1

    sample_findings = []
    # prioritize fails and insufficient evidence
    not_pass = [f for f in summary.findings if f.status != FindingStatus.PASS]
    pass_findings = [f for f in summary.findings if f.status == FindingStatus.PASS]
    for f in (not_pass + pass_findings)[:25]:
        sample_findings.append({
            "constraint": f.constraint.value,
            "status": f.status.value,
            "severity": f.severity.value,
            "session_id": f.session_id,
            "room_id": f.room_id,
            "day": f.day,
            "period": f.period,
            "message": f.message,
        })

    return {
        "status": summary.status.value,
        "is_valid": summary.is_valid,
        "is_complete": summary.is_complete,
        "target": req.target,
        "target_display_name": target_display_name,
        "academic_cycle": req.academic_cycle,
        "mode": req.mode,
        "mode_label": "SYNTHETIC DEMO PROFILE" if req.mode == "synthetic" else "FACTUAL MODE",
        "total_sessions_checked": summary.total_sessions_checked,
        "assigned_sessions_count": summary.assigned_sessions_count,
        "unassigned_sessions_count": summary.unassigned_sessions_count,
        "pass_count": summary.pass_count,
        "fail_count": summary.fail_count,
        "insufficient_evidence_count": summary.insufficient_evidence_count,
        "category_breakdown": category_breakdown,
        "evidence_limitations": summary.evidence_limitations,
        "sample_findings": sample_findings,
    }
