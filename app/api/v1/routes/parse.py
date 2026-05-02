"""
parse.py
--------
All file-upload and job-management routes.

Endpoints
---------
POST   /parse              Upload file → parse → save job → return job id
POST   /parse/match        Upload file → parse → match items against Product DB
GET    /jobs               List all parse jobs (paginated)
GET    /jobs/{job_id}      Get job status
GET    /jobs/{job_id}/result  Download the raw parsed JSON result

Supported file types: .xlsx, .xlsm, .xltx, .xltm, .docx, .doc, .pdf
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
from app.services.matcher import match_document
from app.services.parsers import dispatch_parser
from app.utils.time import utc_now

router = APIRouter(tags=["Parse & Jobs"])


# ---------------------------------------------------------------------------
# POST /parse/match  — MUST be declared before POST /parse to avoid shadowing
# ---------------------------------------------------------------------------

@router.post(
    "/parse/match",
    summary="Upload a file, parse it, and match every item against the Product DB",
    description=(
        "Returns the full parsed table **plus** the top-5 Product DB matches "
        "(with score %) for every row. No job record is created."
    ),
)
async def parse_and_match(
    file: UploadFile = File(..., description="Excel (.xlsx/.xlsm) or PDF (.pdf)"),
    top_n: int = Query(5, ge=1, le=20, description="Number of top matches to return per item"),
    db: Session = Depends(get_db),
) -> dict:
    """
    Response shape::

        {
          "tables": {
            "table_1": {
              "document_info": { ... },
              "headers": [ ... ],
              "rows": [
                {
                  "sr_no": "1",
                  "items": "Chicken Dressed Broiler",
                  ...,
                  "matches": [
                    { "rank": 1, "score_pct": 97.5, "skrt_code": "PROVIN001150",
                      "product_name": "Chicken Dressed Broiler",
                      "category": "Non-Veg", "brand": "Generic",
                      "unit": "Kg", "gst_pct": 0.0, "remarks": "..." },
                    ...
                  ]
                }
              ]
            }
          },
          "summary": {
            "total_items": 50,
            "matched_above_80": 46,
            "matched_above_50": 3,
            "unmatched": 1
          }
        }
    """
    _check_file(file)
    ext = Path(file.filename).suffix.lower()

    try:
        file_bytes = await file.read()
        parsed = dispatch_parser(file_bytes, ext)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Parsing failed: {exc}") from exc
    finally:
        await file.close()

    try:
        return match_document(db, parsed, top_n=top_n)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Matching failed: {exc}") from exc


# ---------------------------------------------------------------------------
# POST /parse  — async job with DB tracking
# ---------------------------------------------------------------------------

@router.post(
    "/parse",
    response_model=JobSubmitResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload a file, parse it, and save the result as a job",
    description="Creates a job record in the DB. Poll `/jobs/{job_id}` for status, then fetch `/jobs/{job_id}/result` for the full JSON.",
)
async def parse_file(
    file: UploadFile = File(..., description="Excel (.xlsx/.xlsm), Word (.docx), or PDF (.pdf)"),
    db: Session = Depends(get_db),
) -> JobSubmitResponse:
    _check_file(file)
    ext = Path(file.filename).suffix.lower()

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
        parsed = dispatch_parser(file_bytes, ext)
        write_json(result_path, parsed)
        total_rows = sum(len(t["rows"]) for t in parsed.values())
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

    return JobSubmitResponse(**job_store.get(db, job_id))


# ---------------------------------------------------------------------------
# GET /jobs
# ---------------------------------------------------------------------------

@router.get(
    "/jobs",
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
    "/jobs/{job_id}",
    response_model=JobStatusResponse,
    summary="Get job status",
)
async def get_job(job_id: str, db: Session = Depends(get_db)) -> JobStatusResponse:
    job = job_store.get(db, job_id)
    if not job:
        raise JobNotFoundError(job_id)
    return JobStatusResponse(**job)


@router.get(
    "/jobs/{job_id}/result",
    summary="Download the parsed JSON result for a completed job",
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


# ---------------------------------------------------------------------------
# Internal guard
# ---------------------------------------------------------------------------

def _check_file(file: UploadFile) -> None:
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")
    ext = Path(file.filename).suffix.lower()
    if ext not in settings.allowed_extensions:
        raise UnsupportedFileTypeError()
