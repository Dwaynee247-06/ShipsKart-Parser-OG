"""
parse.py
--------
All file-upload routes.

Endpoints
---------
POST  /parse/match   Upload file → parse → match items against Product DB → return enriched JSON

Supported file types: .xlsx, .xlsm, .xltx, .xltm, .docx, .doc, .pdf
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings
from app.core.exceptions import UnsupportedFileTypeError
from app.services.matcher import match_document
from app.services.parsers import dispatch_parser

router = APIRouter(tags=["Parse"])


@router.post(
    "/parse/match",
    summary="Upload a file, parse it, and match every item against the Product DB",
    description=(
        "Upload an Excel, Word, or PDF document. "
        "Every line item is parsed and matched against the Product master database. "
        "Returns the structured rows **plus** the top-N matches (with score %) for each item."
    ),
)
async def parse_and_match(
    file: UploadFile = File(
        ...,
        description="Excel (.xlsx / .xlsm), Word (.docx / .doc), or PDF (.pdf)",
    ),
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
                    {
                      "rank": 1,
                      "score_pct": 97.5,
                      "product_id": 1,
                      "product_name": "Chicken Dressed Broiler",
                      "category": "Non-Veg",
                      "brand": "Generic",
                      "unit": "Kg"
                    },
                    ... (up to top_n)
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
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")
    if Path(file.filename).suffix.lower() not in settings.allowed_extensions:
        raise UnsupportedFileTypeError()

    try:
        file_bytes = await file.read()
        parsed = dispatch_parser(file_bytes, Path(file.filename).suffix.lower())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Parsing failed: {exc}") from exc
    finally:
        await file.close()

    try:
        return match_document(db, parsed, top_n=top_n)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Matching failed: {exc}") from exc
