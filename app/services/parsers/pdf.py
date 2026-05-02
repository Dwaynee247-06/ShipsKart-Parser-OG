"""
pdf.py
------
Parser for PDF files (.pdf).
Uses pdfplumber to extract tables page by page. pdfplumber is preferred over
pdfminer or PyMuPDF for tabular PDFs because it reconstructs table structure
from the actual line/cell geometry rather than just raw text streams.

Each detected table on each page becomes one entry in the result dict,
keyed as "page_{n}_table_{m}" so the origin is always traceable.
"""
from __future__ import annotations

from io import BytesIO
from typing import Any

import pdfplumber

from app.services.parsers._shared import build_table_from_rows, clean_cell


def _coerce_row(row: list[Any]) -> list[Any]:
    """Normalize a pdfplumber row — replace empty strings with None."""
    return [v.strip() if isinstance(v, str) and v.strip() else (None if not v else v) for v in row]


def parse_pdf(file_bytes: bytes) -> dict:
    """
    Parse all tables from every page of a PDF.
    Returns a dict keyed by "page_{n}_table_{m}" for each table found.
    Each value follows the same shape as the Excel/Word parser output::

        {
            "document_info": { ...metadata above the table header... },
            "headers":       [ ...canonical column names... ],
            "rows":          [ { col: value, ... }, ... ],
        }

    Strategy:
    - pdfplumber.extract_tables() detects tables per page using line geometry.
    - Each extracted table is a list of rows, each row a list of cell strings.
    - Rows are passed directly to build_table_from_rows() from _shared.py.
    - Tables with no detectable header or no valid data rows are skipped.
    """
    result: dict = {}

    with pdfplumber.open(BytesIO(file_bytes)) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            tables = page.extract_tables()
            if not tables:
                continue

            for table_num, raw_table in enumerate(tables, start=1):
                # raw_table is List[List[str | None]] from pdfplumber
                raw_rows = [_coerce_row(row) for row in raw_table]

                parsed = build_table_from_rows(raw_rows)
                if parsed is not None and parsed["rows"]:
                    key = f"page_{page_num}_table_{table_num}"
                    result[key] = parsed

    return result
