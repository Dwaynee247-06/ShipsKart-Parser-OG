"""
Excel Table Parser
==================
- Reads workbooks in read-only mode (memory-efficient for large files)
- Detects multiple visual table blocks per sheet (not just one table per sheet)
- Normalizes headers via canonical aliases
- Preserves blank cells as None (→ JSON null)
- Groups tables with the same header signature into requirementsN buckets
- Designed to be extended later with PDF/DOCX/Image parsers using the same interface

Example output shape:
  {
    "requirements1": {
      "requirement_name": "requirements1",
      "headers": ["sr_no", "product_name", "unit_of_measurement", "quantity", "remarks"],
      "tables": [ { "sheet_name": "Sheet1", "rows": [...] } ]
    }
  }
"""
from __future__ import annotations

import hashlib
import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from openpyxl import load_workbook
from pydantic import BaseModel

from app.core.config import settings
from app.schemas.job import ExtractedTable, GroupedRequirement, RowRecord

logger = logging.getLogger(__name__)

# ── Header alias map ──────────────────────────────────────────────────────────
# Add or extend aliases here as you encounter new workbook conventions.
HEADER_ALIASES: dict[str, str] = {
    # Serial number variants
    "sr_no": "sr_no", "srno": "sr_no", "sr": "sr_no",
    "serial_no": "sr_no", "serial_number": "sr_no", "s_no": "sr_no",
    "no": "sr_no", "s_n": "sr_no",
    # Product / item name
    "product_name": "product_name", "product": "product_name",
    "item_name": "product_name", "item": "product_name",
    "description": "product_name", "material": "product_name",
    # Unit of measurement
    "unit_of_measurement": "unit_of_measurement", "unit": "unit_of_measurement",
    "uom": "unit_of_measurement", "units": "unit_of_measurement",
    "measure": "unit_of_measurement",
    # Quantity
    "quantity": "quantity", "qty": "quantity", "amount": "quantity", "count": "quantity",
    # Remarks
    "remarks": "remarks", "remark": "remarks", "notes": "remarks", "note": "remarks",
    "comments": "remarks", "comment": "remarks",
}


# ── Internal data model ───────────────────────────────────────────────────────
class _TableBlock(BaseModel):
    start_row: int
    end_row: int
    start_col: int
    end_col: int
    headers: list[str]
    rows: list[dict[str, Any]]


# ── Helper functions ──────────────────────────────────────────────────────────
def _normalize_header(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return HEADER_ALIASES.get(text, text)


def _normalize_cell(value: Any) -> Any:
    """Return value as-is; blank strings become None so JSON shows null."""
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped if stripped else None
    return value


def _is_nonempty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return True


def _nonempty_count(row: Iterable[Any]) -> int:
    return sum(1 for v in row if _is_nonempty(v))


def _col_letter(col_idx: int) -> str:
    result = ""
    while col_idx:
        col_idx, rem = divmod(col_idx - 1, 26)
        result = chr(65 + rem) + result
    return result


def _excel_range(sr: int, sc: int, er: int, ec: int) -> str:
    return f"{_col_letter(sc)}{sr}:{_col_letter(ec)}{er}"


def _make_table_id(sheet_name: str, block_idx: int, signature: str) -> str:
    digest = hashlib.sha1(f"{sheet_name}|{block_idx}|{signature}".encode()).hexdigest()[:10]
    return f"{sheet_name}__block_{block_idx}_{digest}"


def _build_signature(headers: list[str]) -> str:
    return "|".join(headers)


# ── Table block detector ──────────────────────────────────────────────────────
def _find_blocks(ws) -> list[_TableBlock]:
    """
    Scan a worksheet row-by-row and extract rectangular table blocks.
    A block starts at the first row with >= min_headers non-empty cells
    and ends when blank_row_tolerance consecutive blank rows are found.
    """
    raw_rows = list(ws.iter_rows(values_only=True))
    if not raw_rows:
        return []

    max_cols = max((len(r) for r in raw_rows), default=0)
    rows = [list(r) + [None] * (max_cols - len(r)) for r in raw_rows]
    blocks: list[_TableBlock] = []
    r = 0

    while r < len(rows):
        current = rows[r]
        nonempty_pos = [i for i, v in enumerate(current) if _is_nonempty(v)]

        if len(nonempty_pos) < settings.min_headers:
            r += 1
            continue

        sc = min(nonempty_pos)
        ec = max(nonempty_pos)
        raw_headers = current[sc : ec + 1]
        headers = [_normalize_header(v) for v in raw_headers]

        valid = sum(1 for h in headers if h)
        unique = len({h for h in headers if h})
        if valid < settings.min_headers or unique < settings.min_headers:
            r += 1
            continue

        data_rows: list[dict[str, Any]] = []
        blank_streak = 0
        rr = r + 1

        while rr < len(rows):
            candidate = rows[rr][sc : ec + 1]
            if _nonempty_count(candidate) == 0:
                blank_streak += 1
                if blank_streak > settings.blank_row_tolerance:
                    break
                rr += 1
                continue

            blank_streak = 0
            row_dict: dict[str, Any] = {}
            for idx, header in enumerate(headers):
                key = header if header else f"column_{idx + 1}"
                row_dict[key] = _normalize_cell(candidate[idx] if idx < len(candidate) else None)
            data_rows.append(row_dict)
            rr += 1

        if data_rows:
            blocks.append(
                _TableBlock(
                    start_row=r + 1,
                    end_row=rr,
                    start_col=sc + 1,
                    end_col=ec + 1,
                    headers=[h if h else f"column_{i + 1}" for i, h in enumerate(headers)],
                    rows=data_rows,
                )
            )
            r = rr
        else:
            r += 1

    return blocks


# ── Public API ────────────────────────────────────────────────────────────────
def extract_workbook(path: Path) -> dict[str, GroupedRequirement]:
    """
    Parse an Excel workbook and return tables grouped by header signature.

    Returns a dict like:
      { "requirements1": GroupedRequirement, "requirements2": GroupedRequirement, ... }
    """
    wb = load_workbook(filename=str(path), read_only=True, data_only=True)
    grouped: dict[str, list[ExtractedTable]] = defaultdict(list)

    try:
        for ws in wb.worksheets:
            logger.info("Scanning sheet: %s", ws.title)
            blocks = _find_blocks(ws)
            logger.info("  → Found %d table block(s) in sheet '%s'", len(blocks), ws.title)

            for idx, block in enumerate(blocks, start=1):
                signature = _build_signature(block.headers)
                extracted = ExtractedTable(
                    sheet_name=ws.title,
                    table_id=_make_table_id(ws.title, idx, signature),
                    headers=block.headers,
                    header_signature=signature,
                    source_range=_excel_range(block.start_row, block.start_col, block.end_row, block.end_col),
                    rows=[RowRecord.model_validate(row).model_dump() for row in block.rows],
                )
                grouped[signature].append(extracted)
    finally:
        wb.close()

    result: dict[str, GroupedRequirement] = {}
    for i, (signature, tables) in enumerate(grouped.items(), start=1):
        req_name = f"requirements{i}"
        result[req_name] = GroupedRequirement(
            requirement_name=req_name,
            headers=tables[0].headers,
            header_signature=signature,
            tables=tables,
            total_rows=sum(len(t.rows) for t in tables),
        )
        logger.info(
            "Group '%s': %d table(s), %d row(s) | signature: %s",
            req_name, len(tables), result[req_name].total_rows, signature,
        )

    return result
