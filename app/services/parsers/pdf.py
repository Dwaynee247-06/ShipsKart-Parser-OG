"""
pdf.py
------
Parser for PDF files (.pdf).
Uses pdfplumber to extract tables page by page.

Multi-page table stitching
--------------------------
Two continuation strategies are used in order:

1. REPEATED HEADER  – page 2 starts with the same header row as page 1
   (e.g. engineering requisitions). Header is dropped, data rows appended.

2. NUMERIC SEQUENCE – page 2 starts directly with data rows (no repeated
   header), and the first column of the new page is a numeric serial that
   is greater than the last serial seen on page 1
   (e.g. provision/purchase quotations).  All rows on the new page are
   appended using the already-known headers.

If neither condition holds, the table on the new page is treated as a brand
new logical table.

Result keys: "table_1", "table_2", ... (logical tables, not physical pages).
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
    """Return True if first_row looks like the same header row (≥60% overlap)."""
    if not headers_a or not first_row:
        return False
    normalized_new = [normalize_header(v) for v in first_row]
    set_a = {h for h in headers_a if h}
    set_b = {h for h in normalized_new if h}
    if not set_a or not set_b:
        return False
    overlap = len(set_a & set_b) / max(len(set_a), len(set_b))
    return overlap >= 0.6


def _is_numeric(value: Any) -> bool:
    """Return True if value can be parsed as a positive integer."""
    try:
        return int(str(value).strip()) > 0
    except (ValueError, TypeError):
        return False


def _first_serial(row: list[Any]) -> int | None:
    """Return the integer value of the first cell if it looks like a serial number."""
    if row and _is_numeric(row[0]):
        return int(str(row[0]).strip())
    return None


def _is_data_continuation(
    last_serial: int | None,
    coerced_rows: list[list[Any]],
) -> bool:
    """
    Return True when the new page starts directly with numbered data rows
    that continue from the last serial seen on the previous page.
    Condition: first non-empty row has serial == last_serial + 1 (or close).
    """
    if last_serial is None:
        return False
    for row in coerced_rows:
        sn = _first_serial(row)
        if sn is not None:
            return sn > last_serial  # any increase means continuation
    return False


def _append_rows(
    existing: dict,
    last_headers: list[str],
    data_rows: list[list[Any]],
) -> int:
    """
    Append data_rows into existing["rows"] using last_headers as the column map.
    Returns the last serial number seen (from first column), or None.
    """
    header_index_map = {h: i for i, h in enumerate(last_headers) if h}
    last_serial = None
    for row in data_rows:
        if not any(v not in (None, "") for v in row):
            continue
        item = {
            header: clean_cell(row[idx] if idx < len(row) else None)
            for header, idx in header_index_map.items()
        }
        # Accept the row if it has ANY meaningful value in the first two columns
        first_vals = list(item.values())[:2]
        if any(v for v in first_vals):
            existing["rows"].append(item)
            sn = _first_serial(row)
            if sn is not None:
                last_serial = sn
    return last_serial


def parse_pdf(file_bytes: bytes) -> dict:
    """
    Parse all tables from every page of a PDF, stitching multi-page tables.
    """
    result: dict = {}
    table_counter = 0

    last_key: str | None = None
    last_headers: list[str] = []
    last_serial: int | None = None  # tracks highest sr_no seen so far

    with pdfplumber.open(BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()
            if not tables:
                continue

            for raw_table in tables:
                if not raw_table:
                    continue

                coerced = [_coerce_row(row) for row in raw_table]
                first_row = coerced[0] if coerced else []

                # ── Strategy 1: repeated header on this page ──────────────
                if last_key is not None and _headers_match(last_headers, first_row):
                    data_only = coerced[1:]
                    sn = _append_rows(result[last_key], last_headers, data_only)
                    if sn:
                        last_serial = sn
                    continue

                # ── Strategy 2: data-only continuation (no repeated header) ─
                if last_key is not None and _is_data_continuation(last_serial, coerced):
                    sn = _append_rows(result[last_key], last_headers, coerced)
                    if sn:
                        last_serial = sn
                    continue

                # ── Strategy 3: brand new table ───────────────────────────
                parsed = build_table_from_rows(coerced)
                if parsed is not None and parsed["rows"]:
                    table_counter += 1
                    key = f"table_{table_counter}"
                    result[key] = parsed
                    last_key = key
                    last_headers = parsed["headers"]
                    # Seed last_serial from the last row of this table
                    for row in reversed(coerced):
                        sn = _first_serial(row)
                        if sn:
                            last_serial = sn
                            break
                else:
                    last_key = None
                    last_headers = []
                    last_serial = None

    return result
