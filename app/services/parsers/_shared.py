"""
_shared.py
----------
Shared table-parsing utilities used by all parsers (Excel, Word, PDF).
Contains header aliases, scoring, normalization, and metadata extraction.
Do NOT import parser-specific libraries here.
"""
from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Header alias map  →  canonical field name
# ---------------------------------------------------------------------------
HEADER_ALIASES: dict[str, str] = {
    # Serial number
    "sr no": "sr_no",
    "sr. no.": "sr_no",
    "sr.no.": "sr_no",
    "s no": "sr_no",
    "s.no": "sr_no",
    "sno": "sr_no",
    "no": "sr_no",

    # Item / description
    "items": "items",
    "item": "items",
    "product": "items",
    "product name": "items",
    "part details": "items",
    "description": "items",
    "name": "items",
    "material": "items",

    # Unit of measurement
    "unit": "unit_of_measurement",
    "units": "unit_of_measurement",
    "uom": "unit_of_measurement",
    "unit of": "unit_of_measurement",
    "unit of measurement": "unit_of_measurement",

    # Quantity
    "qty": "quantity",
    "quantity": "quantity",
    "qty req": "quantity",
    "qty required": "quantity",
    "required qty": "quantity",
    "req qty": "quantity",
    "ordered qty": "quantity",

    # ROB / Rate / Price
    "rob": "rob",
    "rate": "rate",
    "unit price": "unit_price",
    "price": "rate",

    # Tax
    "gst": "gst",
    "tax": "gst",
    "vat": "gst",

    # Amount / total
    "amount": "amount",
    "amt": "amount",
    "total": "amount",
    "total price": "amount",
    "total amount": "amount",
    "net amount": "amount",

    # Category / codes
    "category": "category",
    "cat": "category",
    "skrt code": "skrt_code",
    "skrt_code": "skrt_code",
    "part no / impa / code": "part_no_impa_code",
    "part no impa code": "part_no_impa_code",
    "part no": "part_no_impa_code",
    "impa code": "part_no_impa_code",
    "impa": "part_no_impa_code",
    "part number": "part_no_impa_code",
    "code": "part_no_impa_code",

    # Make / brand
    "make req": "make_req",
    "make": "make_req",
    "brand": "make_req",
    "make required": "make_req",

    # Remarks
    "remarks": "remarks",
    "remark": "remarks",
    "purchase remark": "purchase_remark",
    "purchase reamrk": "purchase_remark",   # intentional typo in source docs
    "purchase remarks": "purchase_remark",
    "technical remark": "technical_remark",
    "vessel remarks": "vessel_remarks",
    "vessel remark": "vessel_remarks",
    "notes": "remarks",

    # Consumption history
    "last supplied date and qty": "last_supplied_date_qty",
    "last supplied": "last_supplied_date_qty",
    "last 3 months consumptions": "last_3_months_consumptions",

    # Document-level metadata
    "ref request no": "ref_request_no",
    "ref. request no": "ref_request_no",
    "ref request no.": "ref_request_no",
    "vessel": "vessel",
    "department": "department",
    "dept": "department",
    "port": "port",
    "date": "date",
    "ordered by": "ordered_by",
    "approved by": "approved_by",
    "equipment": "equipment",
}

# Fields that signal a row is an item row (used for scoring & primary-key check)
EXPECTED_ITEM_HEADERS: frozenset[str] = frozenset({
    "sr_no", "items", "unit_of_measurement", "quantity", "category",
    "skrt_code", "rate", "gst", "amount", "remarks", "part_no_impa_code",
    "rob", "make_req", "purchase_remark", "unit_price", "technical_remark",
    "vessel_remarks",
})

# At least one of these must be present for a row to count as a data row
PRIMARY_ITEM_KEYS: frozenset[str] = frozenset({"items", "part_no_impa_code", "sr_no"})

# Keywords that identify a grand-total footer row (case-insensitive)
_TOTAL_ROW_KEYWORDS: tuple[str, ...] = (
    "total (inr)",
    "grand total",
    "total amount",
    "total inr",
    "net total",
    "total cost",
    "overall total",
    "total",
)


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def normalize_header(value: Any) -> str:
    """Normalize a raw cell/cell-text value to a canonical field name."""
    if value is None:
        return ""
    text = str(value).strip().lower()
    text = text.replace("\n", " ")
    text = re.sub(r"[\/\\\-:]+", " ", text)   # strip slashes, dashes, colons
    text = re.sub(r"\s+", " ", text).strip()
    if text in HEADER_ALIASES:
        return HEADER_ALIASES[text]
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def clean_cell(value: Any) -> Any:
    """Return None for blank/empty values, otherwise return the value as-is."""
    if value is None:
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


def score_header_row(row_values: list[Any]) -> tuple[int, list[str]]:
    """Score a row by how many values match known item-table header names."""
    normalized = [normalize_header(v) for v in row_values]
    unique_non_empty = {x for x in normalized if x}
    score = len(unique_non_empty & EXPECTED_ITEM_HEADERS)
    return score, normalized


def is_section_heading(item: dict[str, Any]) -> bool:
    """
    Return True if an item row contains only a single ALL-CAPS value
    (e.g. section labels like 'FUEL OIL INJECTION PUMP').
    """
    filled = [v for v in item.values() if v not in (None, "")]
    if len(filled) == 1:
        only_value = str(filled[0]).strip()
        return len(only_value) > 3 and only_value.replace(" ", "").isupper()
    return False


def is_valid_item_row(item: dict[str, Any]) -> bool:
    """Return True if the row has at least one primary item key filled."""
    return any(item.get(k) for k in PRIMARY_ITEM_KEYS)


def is_total_row(item: dict[str, Any]) -> bool:
    """
    Return True if this row is a grand-total footer row and should NOT be
    treated as a regular item.

    Detection rules (any one is sufficient):
      1. The 'items' field matches a known total-row keyword (e.g. "TOTAL (INR)").
      2. 'sr_no' is empty/None AND 'items' contains the word "total".
    """
    items_raw = str(item.get("items") or "").strip()
    items_lower = items_raw.lower()

    # Rule 1 – exact keyword match
    for kw in _TOTAL_ROW_KEYWORDS:
        if items_lower == kw:
            return True

    # Rule 2 – no sr_no AND "total" appears anywhere in the items cell
    sr = item.get("sr_no")
    if not sr and "total" in items_lower:
        return True

    return False


def extract_total_amount(item: dict[str, Any]) -> float | None:
    """
    Pull the numeric total amount out of a detected total row.
    Tries the 'amount' field first, then any numeric field in the row.
    Returns None if no numeric value is found.
    """
    # Prefer the mapped 'amount' column
    raw = item.get("amount")
    if raw is not None:
        try:
            return float(raw)
        except (TypeError, ValueError):
            pass

    # Fallback: scan all values for a large numeric
    for v in item.values():
        if v is None:
            continue
        try:
            f = float(v)
            if f > 0:
                return f
        except (TypeError, ValueError):
            continue

    return None


# ---------------------------------------------------------------------------
# Table builder  (shared by all parsers)
# ---------------------------------------------------------------------------

def build_table_from_rows(
    raw_rows: list[list[Any]],
    min_header_score: int = 2,
    max_header_scan: int = 40,
) -> dict[str, Any] | None:
    """
    Given a list of raw rows (each row is a list of cell values),
    detect the header row, extract document metadata above it,
    and return a structured dict with document_info, headers, rows,
    and an optional total_amount field.

    Returns None if no valid header row is found.
    """
    best_idx = None
    best_score = 0
    best_headers: list[str] = []

    scan_limit = min(max_header_scan, len(raw_rows))
    for i, row in enumerate(raw_rows[:scan_limit]):
        score, headers = score_header_row(row)
        if score > best_score:
            best_score = score
            best_idx = i
            best_headers = headers

    if best_idx is None or best_score < min_header_score:
        # Fallback: first non-empty row
        for i, row in enumerate(raw_rows):
            if any(v not in (None, "") for v in row):
                best_idx = i
                best_headers = [normalize_header(v) for v in row]
                break

    if best_idx is None:
        return None

    # Build header → column-index map (first occurrence wins)
    header_index_map: dict[str, int] = {}
    for idx, h in enumerate(best_headers):
        if h and h not in header_index_map:
            header_index_map[h] = idx

    # Extract metadata from rows above the header
    doc_info = _extract_metadata(raw_rows[:best_idx])

    # Extract data rows below the header
    data_rows: list[dict[str, Any]] = []
    total_amount: float | None = None

    for row in raw_rows[best_idx + 1:]:
        if not any(v not in (None, "") for v in row):
            continue   # skip fully blank rows

        item = {
            header: clean_cell(row[idx] if idx < len(row) else None)
            for header, idx in header_index_map.items()
        }

        # ── Total row detection ────────────────────────────────────────────
        if is_total_row(item):
            # Extract the amount value and skip adding to data_rows
            extracted = extract_total_amount(item)
            if extracted is not None:
                total_amount = extracted
            continue

        if is_section_heading(item):
            continue
        if not is_valid_item_row(item):
            continue

        data_rows.append(item)

    return {
        "document_info": doc_info,
        "headers": list(header_index_map.keys()),
        "rows": data_rows,
        "total_amount": total_amount,
    }


def _extract_metadata(rows: list[list[Any]]) -> dict[str, Any]:
    """
    Extract document-level key-value pairs from rows above the header.
    Handles both 2-cell (key, value) and multi-column (k1,v1,k2,v2,...) rows.
    """
    metadata: dict[str, Any] = {}
    for row in rows:
        values = [v for v in row if v not in (None, "")]
        if len(values) < 2:
            continue
        pairs = list(zip(values[::2], values[1::2]))
        for k, v in pairs:
            key = normalize_header(k)
            if key:
                metadata[key] = clean_cell(v)
    return metadata
