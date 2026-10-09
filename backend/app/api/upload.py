"""Upload and Joint Allocation Endpoints for ClassroomIQ.

Governed by Document 05 revision v0.2.6 and PAR-CIQ-P7-ADDENDUM-01.
Provides preflight inspection, joint CP-SAT optimization, and timetable queries.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query, status

from backend.app.schemas.upload import (
    UploadPreflightRequest,
    UploadPreflightResponse,
    UploadAllocationRequest,
    UploadAllocationResponse,
    UploadTimetableResponse,
)
from backend.app.services.upload_service import UploadService
from backend.app.services.joint_allocation_service import JointAllocationService

router = APIRouter(prefix="/upload", tags=["Upload & Allocate"])


@router.post("/preflight", response_model=UploadPreflightResponse)
def preflight_upload(req: UploadPreflightRequest) -> UploadPreflightResponse:
    """Parses and inspects raw timetable CSV files, resolving column headers and validating period constraints."""
    upload_service = UploadService()
    try:
        return upload_service.process_preflight(req)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Preflight processing failed: {str(e)}",
        )


@router.post("/allocate", response_model=UploadAllocationResponse)
def allocate_upload(req: UploadAllocationRequest) -> UploadAllocationResponse:
    """Executes joint baseline allocation and CP-SAT optimization on a validated upload run."""
    allocation_service = JointAllocationService()
    try:
        return allocation_service.run_joint_allocation(req)
    except KeyError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Joint allocation failed: {str(e)}",
        )


@router.get("/timetable/{run_id}", response_model=UploadTimetableResponse)
def get_upload_timetable(
    run_id: str,
    day: str = Query("Monday", description="Filter by weekday"),
    group_by: str = Query("cohort", description="'cohort', 'room', or 'program'"),
    program: Optional[str] = Query(None, description="Optional program filter"),
    cohort_id: Optional[str] = Query(None, description="Optional cohort filter"),
    room_id: Optional[str] = Query(None, description="Optional room filter"),
) -> UploadTimetableResponse:
    """Returns the allocated weekly timetable grid for a specific upload run."""
    allocation_service = JointAllocationService()
    try:
        return allocation_service.get_upload_timetable_grid(
            run_id=run_id,
            day=day,
            group_by=group_by,
            program=program,
            cohort_id=cohort_id,
            room_id=room_id,
        )
    except KeyError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate upload timetable: {str(e)}",
        )
