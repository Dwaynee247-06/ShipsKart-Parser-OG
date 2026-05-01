"""
Jobs router
-----------
POST   /jobs/parse              Upload an Excel file and parse it
GET    /jobs                    List all jobs (paginated)
GET    /jobs/{job_id}           Get job status
GET    /jobs/{job_id}/result    Download the JSON result
"""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import RESULT_DIR, UPLOAD_DIR, settings
from app.core.exceptions import (
    JobNotCompletedError,
    JobNotFoundError,
    ResultFileMissingError,
    UnsupportedFileTypeError,
)
from app.models.job_store import job_store
from app.schemas.job import JobStatusResponse, JobSubmitResponse
from app.services.files import save_upload, write_json
from app.services.parsers.excel import parse_excel as parse_excel_file
from app.utils.time import utc_now

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post(
    "/parse",
    response_model=JobSubmitResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload & parse an Excel file",
)
async def parse_excel(
    file: UploadFile = File(..., description="Excel workbook (.xlsx / .xlsm)"),
    db: Session = Depends(get_db),
) -> JobSubmitResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    ext = Path(file.filename).suffix.lower()
    if ext not in settings.allowed_extensions:
        raise UnsupportedFileTypeError()

    job_id = str(uuid.uuid4())
    upload_path = UPLOAD_DIR / f"{job_id}{ext}"
    result_path = RESULT_DIR / f"{job_id}.json"
    created = utc_now()

    job_store.create(
        db,
        {
            "job_id": job_id,
            "status": "processing",
            "filename": file.filename,
            "created_at": created,
            "completed_at": None,
            "error": None,
            "result_file": result_path.name,
            "groups": None,
            "total_rows": None,
        },
    )

    try:
        await save_upload(file, upload_path)
        file_bytes = upload_path.read_bytes()
        parsed = parse_excel_file(file_bytes)
        write_json(result_path, parsed)

        total_rows = sum(len(s["rows"]) for s in parsed.values())
        job_store.update(
            db, job_id,
            status="completed",
            completed_at=utc_now(),
            groups=len(parsed),
            total_rows=total_rows,
        )
    except Exception as exc:
        job_store.update(db, job_id, status="failed", completed_at=utc_now(), error=str(exc))
        raise HTTPException(status_code=500, detail=f"Parsing failed: {exc}") from exc
    finally:
        await file.close()

    job = job_store.get(db, job_id)
    return JobSubmitResponse(**job)


@router.get(
    "",
    response_model=list[JobStatusResponse],
    summary="List all parse jobs",
)
async def list_jobs(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[JobStatusResponse]:
    return [JobStatusResponse(**j) for j in job_store.list_all(db, limit=limit, offset=offset)]


@router.get(
    "/{job_id}",
    response_model=JobStatusResponse,
    summary="Get job status",
)
async def get_job(job_id: str, db: Session = Depends(get_db)) -> JobStatusResponse:
    job = job_store.get(db, job_id)
    if not job:
        raise JobNotFoundError(job_id)
    return JobStatusResponse(**job)


@router.get(
    "/{job_id}/result",
    summary="Download the parsed JSON result",
)
async def get_result(job_id: str, db: Session = Depends(get_db)) -> FileResponse:
    job = job_store.get(db, job_id)
    if not job:
        raise JobNotFoundError(job_id)
    if job["status"] != "completed":
        raise JobNotCompletedError(job["status"])

    result_path = RESULT_DIR / f"{job_id}.json"
    if not result_path.exists():
        raise ResultFileMissingError()

    return FileResponse(
        path=result_path,
        media_type="application/json",
        filename=f"result_{job_id}.json",
    )

@router.post(
    "/parse/direct",
    summary="Upload & instantly get parsed JSON",
)
async def parse_excel_direct(
    file: UploadFile = File(..., description="Excel workbook (.xlsx / .xlsm)"),
) -> dict:
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    ext = Path(file.filename).suffix.lower()
    if ext not in settings.allowed_extensions:
        raise UnsupportedFileTypeError()

    try:
        file_bytes = await file.read()
        parsed = parse_excel_file(file_bytes)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Parsing failed: {exc}") from exc
    finally:
        await file.close()

    return parsed