"""
pdf.py
------
Parser for PDF files (.pdf).
Uses pdfplumber to extract tables page by page. pdfplumber is preferred over
pdfminer or PyMuPDF for tabular PDFs because it reconstructs table structure
from the actual line/cell geometry rather than just raw text streams.

Multi-page table stitching
--------------------------
When a table spans more than one page, pdfplumber returns a partial table
per page. This parser detects continuation tables by comparing the first
row of the new page against the last-seen header row. If they match, the
new rows are appended to the existing table entry instead of creating a
new one. If they don't match (new table), a fresh entry is created.

Result keys follow the pattern "table_1", "table_2", ... so the numbering
reflects logical tables, not physical pages.
"""
from __future__ import annotations

from io import BytesIO
from typing import Any

import pdfplumber

from app.services.parsers._shared import (
    build_table_from_rows,
    clean_cell,
    normalize_header,
    score_header_row,
)


def _coerce_row(row: list[Any]) -> list[Any]:
    """Normalize a pdfplumber row — replace empty strings / None with None."""
    result = []
    for v in row:
        if v is None:
            result.append(None)
        elif isinstance(v, str):
            stripped = v.strip()
            result.append(stripped if stripped else None)
        else:
            result.append(v)
    return result


def _headers_match(headers_a: list[str], first_row: list[Any]) -> bool:
    """
    Return True if the first row of a new page looks like the same header
    row that opened the previous table (i.e. the table continues across pages).
    We normalize both sides and require at least 60% overlap.
    """
    if not headers_a or not first_row:
        return False
    normalized_new = [normalize_header(v) for v in first_row]
    set_a = {h for h in headers_a if h}
    set_b = {h for h in normalized_new if h}
    if not set_a or not set_b:
        return False
    overlap = len(set_a & set_b) / max(len(set_a), len(set_b))
    return overlap >= 0.6


def parse_pdf(file_bytes: bytes) -> dict:
    """
    Parse all tables from every page of a PDF, stitching multi-page tables.

    Returns a dict keyed by "table_1", "table_2", ... for each logical table.
    Each value follows the same shape as the Excel/Word parser output::

        {
            "document_info": { ...metadata above the table header... },
            "headers":       [ ...canonical column names... ],
            "rows":          [ { col: value, ... }, ... ],
        }
    """
    result: dict = {}
    table_counter = 0

    # Track last table key and its header list for stitching
    last_key: str | None = None
    last_headers: list[str] = []

    with pdfplumber.open(BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            if not tables:
                continue

            for raw_table in tables:
                if not raw_table:
                    continue

                coerced = [_coerce_row(row) for row in raw_table]

                # Check if this is a continuation of the previous table
                first_row = coerced[0] if coerced else []
                is_continuation = (
                    last_key is not None
                    and _headers_match(last_headers, first_row)
                )

                if is_continuation:
                    # Skip the repeated header row and append data rows only
                    data_only = coerced[1:]  # drop the duplicated header
                    existing = result[last_key]
                    header_index_map = {
                        h: i for i, h in enumerate(last_headers) if h
                    }
                    for row in data_only:
                        if not any(v not in (None, "") for v in row):
                            continue
                        item = {
                            header: clean_cell(row[idx] if idx < len(row) else None)
                            for header, idx in header_index_map.items()
                        }
                        if any(item.get(k) for k in ("items", "part_no_impa_code", "sr_no")):
                            existing["rows"].append(item)
                else:
                    # Brand new table
                    parsed = build_table_from_rows(coerced)
                    if parsed is not None and parsed["rows"]:
                        table_counter += 1
                        key = f"table_{table_counter}"
                        result[key] = parsed
                        last_key = key
                        last_headers = parsed["headers"]
                    else:
                        # No valid rows — reset stitching context
                        last_key = None
                        last_headers = []

    return result
