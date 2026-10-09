"""Allocation and Optimization Execution Endpoints."""

from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException
from backend.app.services.allocation_service import AllocationService
from backend.app.schemas.validation import AllocationResult

router = APIRouter(prefix="/allocation", tags=["Allocation & Optimization"])


class AllocationRequest(BaseModel):
    academic_cycle: str = Field("even", description="'odd' or 'even'")
    allow_computing_lab_exception: bool = Field(False, description="Whether to permit computing lab exceptions")
    time_limit_seconds: float = Field(10.0, ge=1.0, le=10.0, description="Solver search time limit in seconds (max 10.0)")


@router.post("/baseline", response_model=Dict[str, Any])
def run_baseline(req: AllocationRequest) -> Dict[str, Any]:
    """Executes the Phase P5 Greedy Baseline Allocator for the requested academic cycle."""
    if req.academic_cycle not in ["odd", "even"]:
        raise HTTPException(status_code=400, detail="academic_cycle must be 'odd' or 'even'")

    service = AllocationService()
    result = service.run_baseline_allocation(
        academic_cycle=req.academic_cycle,
        allow_computing_lab_exception=req.allow_computing_lab_exception,
    )

    return {
        "allocator_name": result.allocator_name,
        "academic_cycle": req.academic_cycle,
        "execution_time_ms": result.execution_time_ms,
        "assigned_count": len(result.candidate.assignments),
        "unassigned_count": len(result.candidate.unassigned_sessions),
        "assignments": result.candidate.assignments,
        "validation": {
            "status": result.validation.status.value,
            "is_valid": result.validation.is_valid,
            "is_complete": result.validation.is_complete,
            "fail_count": result.validation.fail_count,
            "insufficient_evidence_count": result.validation.insufficient_evidence_count,
        },
    }


@router.post("/optimize", response_model=Dict[str, Any])
def run_optimizer(req: AllocationRequest) -> Dict[str, Any]:
    """Executes the Phase P6 OR-Tools CP-SAT Room Optimizer under the strict 10s search limit."""
    if req.academic_cycle not in ["odd", "even"]:
        raise HTTPException(status_code=400, detail="academic_cycle must be 'odd' or 'even'")

    service = AllocationService()
    result = service.run_optimized_allocation(
        academic_cycle=req.academic_cycle,
        allow_computing_lab_exception=req.allow_computing_lab_exception,
        time_limit_seconds=req.time_limit_seconds,
    )

    return {
        "allocator_name": result.allocator_name,
        "academic_cycle": req.academic_cycle,
        "execution_time_ms": result.execution_time_ms,
        "solver_metadata": result.candidate.metadata,
        "assigned_count": len(result.candidate.assignments),
        "unassigned_count": len(result.candidate.unassigned_sessions),
        "assignments": result.candidate.assignments,
        "validation": {
            "status": result.validation.status.value,
            "is_valid": result.validation.is_valid,
            "is_complete": result.validation.is_complete,
            "fail_count": result.validation.fail_count,
            "insufficient_evidence_count": result.validation.insufficient_evidence_count,
        },
    }


@router.post("/compare", response_model=Dict[str, Any])
def compare_allocations(req: AllocationRequest) -> Dict[str, Any]:
    """Executes side-by-side Baseline vs. CP-SAT comparison, enforcing strict baseline protection fallback."""
    if req.academic_cycle not in ["odd", "even"]:
        raise HTTPException(status_code=400, detail="academic_cycle must be 'odd' or 'even'")

    service = AllocationService()
    comparison = service.compare_baseline_and_optimizer(
        academic_cycle=req.academic_cycle,
        allow_computing_lab_exception=req.allow_computing_lab_exception,
        time_limit_seconds=req.time_limit_seconds,
    )

    return {
        "academic_cycle": comparison.academic_cycle,
        "baseline_allocator_name": comparison.baseline_allocator_name,
        "optimized_allocator_name": comparison.optimized_allocator_name,
        "selected_allocator_name": comparison.selected_allocator_name,
        "baseline_walking_time": comparison.baseline_walking_time,
        "optimized_walking_time": comparison.optimized_walking_time,
        "walking_time_reduction_minutes": comparison.walking_time_reduction_minutes,
        "walking_time_reduction_percentage": comparison.walking_time_reduction_percentage,
        "baseline_same_room_count": comparison.baseline_same_room_count,
        "optimized_same_room_count": comparison.optimized_same_room_count,
        "baseline_specialized_misuse": comparison.baseline_specialized_misuse,
        "optimized_specialized_misuse": comparison.optimized_specialized_misuse,
        "raw_solver_status": comparison.raw_solver_status,
        "raw_solver_walking_time": comparison.raw_solver_walking_time,
        "fallback_to_baseline": comparison.fallback_to_baseline,
        "improvement_achieved": comparison.improvement_achieved,
        "baseline_execution_ms": comparison.baseline_execution_ms,
        "optimized_execution_ms": comparison.optimized_execution_ms,
        "evidence_limitations": comparison.evidence_limitations,
        "walking_proxy_notice": "Walking times are calculated using the synthetic prefix-distance matrix (3.0/8.0 min proxy), not GPS-measured routes.",
    }
