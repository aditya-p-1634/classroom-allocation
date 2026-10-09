"""Independent Validator Audit Endpoints."""

from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from fastapi import APIRouter
from backend.app.services.data_loader import DataLoaderService
from backend.app.core.validator import IndependentValidator
from backend.app.schemas.validation import AllocationCandidate, ConstraintCategory, FindingStatus

router = APIRouter(prefix="/validation", tags=["Validation Inspector"])


class AuditRequest(BaseModel):
    academic_cycle: str = Field("even", description="'odd', 'even', or 'all'")
    assignments: Optional[Dict[str, str]] = Field(None, description="Optional assignment map to audit; if omitted, audits source timetable")
    allow_computing_lab_exception: bool = Field(False, description="Whether to allow computing lab exception")


@router.post("/audit", response_model=Dict[str, Any])
def audit_allocation(req: AuditRequest) -> Dict[str, Any]:
    """Independently audits an allocation candidate or the source timetable against all 5 hard constraints."""
    snapshot = DataLoaderService().load_snapshot()
    validator = IndependentValidator(
        snapshot=snapshot,
        allow_computing_lab_exception=req.allow_computing_lab_exception,
    )

    if req.assignments is not None:
        candidate = AllocationCandidate(
            academic_cycle=req.academic_cycle,
            assignments=req.assignments,
        )
    else:
        # Audit source timetable assignments directly
        if req.academic_cycle in ["odd", "even"]:
            cycle_sessions = [s for s in snapshot.sessions if s.academic_cycle == req.academic_cycle]
        else:
            cycle_sessions = snapshot.sessions
        source_assignments = {s.session_id: s.assigned_room_id for s in cycle_sessions if s.assigned_room_id}
        candidate = AllocationCandidate(
            academic_cycle=req.academic_cycle,
            assignments=source_assignments,
        )

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
