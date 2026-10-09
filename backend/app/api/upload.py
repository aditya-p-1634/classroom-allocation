"""Upload and Joint Allocation Endpoints for ClassroomIQ.

Governed by Document 05 revision v0.2.6 and PAR-CIQ-P7-ADDENDUM-01.
Provides preflight inspection, joint CP-SAT optimization, and timetable queries.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Response, status

from backend.app.schemas.upload import (
    UploadPreflightRequest,
    UploadPreflightResponse,
    UploadAllocationRequest,
    UploadAllocationResponse,
    UploadTimetableResponse,
)
from backend.app.services.upload_service import UploadService
from backend.app.services.joint_allocation_service import JointAllocationService
from backend.app.services.export_service import ExportService

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


@router.get("/export/{run_id}")
def export_upload_results(
    run_id: str,
    format: str = Query("csv", description="Export format: 'csv' or 'zip'"),
):
    """Downloads allocation results as a combined CSV or self-contained ZIP archive."""
    context = UploadService.get_run_context(run_id)
    if not context:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Upload run ID '{run_id}' not found or session expired.",
        )
    if context.allocation_result is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Joint allocation has not been executed for run ID '{run_id}'. Please run /api/upload/allocate first.",
        )

    fmt = format.strip().lower()
    if fmt == "csv":
        csv_content = ExportService.generate_combined_csv(context)
        filename = f"ClassroomIQ_Combined_Allocation_{run_id}.csv"
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            },
        )
    elif fmt == "zip":
        zip_bytes = ExportService.generate_zip_archive(context)
        filename = f"ClassroomIQ_Allocation_{run_id}.zip"
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            },
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported export format '{format}'. Supported formats are 'csv' and 'zip'.",
        )
