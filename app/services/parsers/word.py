"""
word.py
-------
Parser for Word documents (.docx).
Extracts all tables from the document and passes each one through the
shared table-building logic in _shared.py.

Each Word table becomes one entry in the result dict, keyed as
"table_1", "table_2", etc.
"""
from __future__ import annotations

from io import BytesIO
from typing import Any

from docx import Document
from docx.table import Table

from app.services.parsers._shared import build_table_from_rows, clean_cell


def _table_to_raw_rows(table: Table) -> list[list[Any]]:
    """
    Convert a python-docx Table object into a plain list-of-lists.
    Merged cells are read by their display text (python-docx handles this
    transparently via cell.text).
    """
    raw_rows: list[list[Any]] = []
    for row in table.rows:
        raw_row = []
        for cell in row.cells:
            text = cell.text.strip()
            raw_row.append(text if text else None)
        raw_rows.append(raw_row)
    return raw_rows


def parse_word(file_bytes: bytes) -> dict:
    """
    Parse all tables inside a .docx file.
    Returns a dict keyed by "table_1", "table_2", ... for each table found.
    Each value follows the same shape as the Excel parser output::

        {
            "document_info": { ...metadata above the table header... },
            "headers":       [ ...canonical column names... ],
            "rows":          [ { col: value, ... }, ... ],
        }

    Tables with no detectable header are skipped.
    """
    doc = Document(BytesIO(file_bytes))
    result: dict = {}
    table_counter = 0

    for table in doc.tables:
        raw_rows = _table_to_raw_rows(table)
        parsed = build_table_from_rows(raw_rows)
        if parsed is not None and parsed["rows"]:
            table_counter += 1
            result[f"table_{table_counter}"] = parsed

    return result
