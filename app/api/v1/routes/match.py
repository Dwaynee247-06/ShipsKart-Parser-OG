"""
match.py
--------
POST /jobs/parse/match

Upload a PDF or Excel file → parse it → match every item against the
Product master DB → return enriched JSON with top-5 matches per row.

Response shape
--------------
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
            {
              "rank": 1,
              "score_pct": 97.5,
              "skrt_code": "PROVIN001150",
              "product_name": "Chicken Dressed Broiler",
              "category": "Non-Veg",
              "brand": "Generic",
              "unit": "Kg",
              "gst_pct": 0.0,
              "remarks": "Chicken Whole - Halal"
            },
            ...  (up to 5)
          ]
        },
        ...
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
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings
from app.core.exceptions import UnsupportedFileTypeError
from app.services.parsers import dispatch_parser
from app.services.matcher import match_document

router = APIRouter(prefix="/jobs", tags=["match"])


@router.post(
    "/parse/match",
    summary="Upload a file, parse it, and match every item against the Product DB (top-5 per item)",
)
async def parse_and_match(
    file: UploadFile = File(..., description="Excel (.xlsx/.xlsm) or PDF (.pdf)"),
    top_n: int = 5,
    db: Session = Depends(get_db),
) -> dict:
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    ext = Path(file.filename).suffix.lower()
    if ext not in settings.allowed_extensions:
        raise UnsupportedFileTypeError()

    try:
        file_bytes = await file.read()
        parsed = dispatch_parser(file_bytes, ext)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Parsing failed: {exc}") from exc
    finally:
        await file.close()

    try:
        result = match_document(db, parsed, top_n=top_n)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Matching failed: {exc}") from exc

    return result
