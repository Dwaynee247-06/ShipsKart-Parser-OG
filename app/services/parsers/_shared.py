"""
_shared.py
----------
Shared table-parsing utilities used by all parsers (Excel, Word, PDF).
Contains header aliases, scoring, normalization, and metadata extraction.
Do NOT import parser-specific libraries here.
"""
from __future__ import annotations

import re
from collections import Counter
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

# ---------------------------------------------------------------------------
# Value-fingerprint signatures  →  canonical field name
#
# Each frozenset contains known VALUES (not headers) that strongly identify
# a column type when the header itself is unrecognised.
# The check is: if ≥ 50% of non-empty values in a column hit this set,
# that column is inferred as the canonical field.
#
# Priority order (most specific first) matters — see infer_columns_from_values().
# ---------------------------------------------------------------------------

# Unit-of-measurement: physical units that appear as cell values
_UOM_VALUES: frozenset[str] = frozenset({
    # Weight
    "kg", "kgs", "kilogram", "kilograms",
    "g", "gm", "gms", "gram", "grams",
    "mg", "milligram", "milligrams",
    "lb", "lbs", "pound", "pounds",
    "oz", "ounce", "ounces",
    "ton", "tons", "tonne", "tonnes", "mt",
    # Volume
    "l", "ltr", "ltrs", "litre", "litres", "liter", "liters",
    "ml", "millilitre", "millilitres", "milliliter", "milliliters",
    "cl", "dl",
    "gal", "gallon", "gallons",
    "fl oz",
    # Count / packs
    "pcs", "pc", "piece", "pieces",
    "nos", "no", "number",
    "pkt", "pkts", "packet", "packets",
    "box", "boxes",
    "ctn", "carton", "cartons",
    "bag", "bags",
    "tin", "tins",
    "btl", "btls", "bottle", "bottles",
    "can", "cans",
    "roll", "rolls",
    "set", "sets",
    "pair", "pairs",
    "dozen", "doz",
    "bundle", "bundles",
    "tray", "trays",
    "each", "ea",
    # Length / area
    "m", "mtr", "mtrs", "metre", "metres", "meter", "meters",
    "cm", "mm",
    "ft", "feet", "foot",
    "inch", "inches",
    "sqm", "sqft",
})

# Category: provision category labels used in maritime docs
_CATEGORY_VALUES: frozenset[str] = frozenset({
    "veg", "non-veg", "nonveg", "non veg",
    "dry", "dry store", "dry stores",
    "frozen", "fresh", "chilled",
    "dairy", "dairy products",
    "beverages", "beverage",
    "cleaning", "cleaning material", "cleaning materials",
    "deck", "engine", "cabin", "galley",
    "provisions", "provision",
    "fruits", "vegetables", "meat", "seafood", "poultry",
    "bakery", "bread", "cereals", "spices", "condiments",
    "oil", "oils",
})

# SR number column: small integers 1,2,3... or strings like "1.", "2."
# (detected differently — see _looks_like_sr_no_column)

# Combine into a priority-ordered list of (frozenset, canonical_field)
# Most specific / least ambiguous first.
COLUMN_VALUE_SIGNATURES: list[tuple[frozenset[str], str]] = [
    (_UOM_VALUES,      "unit_of_measurement"),
    (_CATEGORY_VALUES, "category"),
]

# Minimum fraction of non-empty column values that must match the signature
_SIGNATURE_THRESHOLD: float = 0.50   # 50 %


# ---------------------------------------------------------------------------
# Fields that signal a row is an item row
# ---------------------------------------------------------------------------
EXPECTED_ITEM_HEADERS: frozenset[str] = frozenset({
    "sr_no", "items", "unit_of_measurement", "quantity", "category",
    "skrt_code", "rate", "gst", "amount", "remarks", "part_no_impa_code",
    "rob", "make_req", "purchase_remark", "unit_price", "technical_remark",
    "vessel_remarks",
})

PRIMARY_ITEM_KEYS: frozenset[str] = frozenset({"items", "part_no_impa_code", "sr_no"})

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


# ---------------------------------------------------------------------------
# Value-fingerprint inference
# ---------------------------------------------------------------------------

def _column_values(data_rows: list[dict[str, Any]], col_key: str) -> list[str]:
    """Return lowercased, stripped non-empty string values for one column."""
    out = []
    for row in data_rows:
        v = row.get(col_key)
        if v is not None and str(v).strip():
            out.append(str(v).strip().lower())
    return out


def _looks_like_sr_no_column(values: list[str]) -> bool:
    """
    True if the column looks like a serial-number column:
    values are small positive integers (possibly with trailing dots/brackets)
    and they increment sequentially starting near 1.
    """
    if not values:
        return False
    cleaned = [re.sub(r"[^\d]", "", v) for v in values]
    numeric = [int(c) for c in cleaned if c.isdigit()]
    if len(numeric) < max(2, len(values) * 0.6):
        return False
    # Must start at 1 (or close) and be mostly sequential
    numeric.sort()
    return numeric[0] <= 3 and numeric[-1] <= len(values) + 5


def _looks_like_quantity_column(values: list[str]) -> bool:
    """
    True if the column is purely numeric (integers or decimals)
    and values are in a realistic quantity range (0.01 – 100,000).
    """
    if not values:
        return False
    numeric = []
    for v in values:
        try:
            numeric.append(float(v.replace(",", "")))
        except ValueError:
            return False   # any non-numeric kills it
    if not numeric:
        return False
    return all(0.01 <= n <= 100_000 for n in numeric)


def infer_columns_from_values(
    header_index_map: dict[str, int],
    data_rows: list[list[Any]],
) -> dict[str, int]:
    """
    Look at each column that was NOT recognised by header name (i.e. its
    canonical key is not in EXPECTED_ITEM_HEADERS) and try to infer the
    correct canonical field from the actual cell values underneath it.

    Returns an updated copy of header_index_map with inferred remappings.
    Already-recognised columns are never overwritten.
    """
    if not data_rows:
        return header_index_map

    # Build a quick col_index → list-of-values lookup from raw rows
    # header_index_map: canonical_name → col_index
    index_to_key: dict[int, str] = {v: k for k, v in header_index_map.items()}
    num_cols = max(header_index_map.values()) + 1 if header_index_map else 0

    # Pre-extract per-column values from raw data rows
    col_raw: dict[int, list[str]] = {}
    for col_idx in range(num_cols):
        vals = []
        for row in data_rows:
            if col_idx < len(row):
                v = row[col_idx]
                if v is not None and str(v).strip():
                    vals.append(str(v).strip().lower())
        col_raw[col_idx] = vals

    already_claimed: set[str] = set(header_index_map.keys()) & EXPECTED_ITEM_HEADERS
    updated = dict(header_index_map)

    for col_idx, values in col_raw.items():
        current_key = index_to_key.get(col_idx, "")
        # Skip columns already mapped to a known canonical field
        if current_key in EXPECTED_ITEM_HEADERS:
            continue
        if not values:
            continue

        inferred: str | None = None

        # ── 1. Value-signature check (UOM, category, …) ──────────────────
        for sig_set, canonical in COLUMN_VALUE_SIGNATURES:
            if canonical in already_claimed:
                continue
            hits = sum(1 for v in values if v in sig_set)
            if hits / len(values) >= _SIGNATURE_THRESHOLD:
                inferred = canonical
                break

        # ── 2. SR-number column ───────────────────────────────────────────
        if inferred is None and "sr_no" not in already_claimed:
            if _looks_like_sr_no_column(values):
                inferred = "sr_no"

        # ── 3. Pure-numeric → quantity (only if quantity not yet claimed) ─
        if inferred is None and "quantity" not in already_claimed:
            if _looks_like_quantity_column(values):
                inferred = "quantity"

        if inferred:
            # Remove the old unknown key and remap the column index
            if current_key and current_key in updated:
                del updated[current_key]
            updated[inferred] = col_idx
            already_claimed.add(inferred)

    return updated


# ---------------------------------------------------------------------------
# Row-level helpers
# ---------------------------------------------------------------------------

def is_section_heading(item: dict[str, Any]) -> bool:
    filled = [v for v in item.values() if v not in (None, "")]
    if len(filled) == 1:
        only_value = str(filled[0]).strip()
        return len(only_value) > 3 and only_value.replace(" ", "").isupper()
    return False


def is_valid_item_row(item: dict[str, Any]) -> bool:
    return any(item.get(k) for k in PRIMARY_ITEM_KEYS)


def is_total_row(item: dict[str, Any]) -> bool:
    items_raw = str(item.get("items") or "").strip()
    items_lower = items_raw.lower()
    for kw in _TOTAL_ROW_KEYWORDS:
        if items_lower == kw:
            return True
    sr = item.get("sr_no")
    if not sr and "total" in items_lower:
        return True
    return False


def extract_total_amount(item: dict[str, Any]) -> float | None:
    raw = item.get("amount")
    if raw is not None:
        try:
            return float(raw)
        except (TypeError, ValueError):
            pass
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

    After header detection, any unrecognised columns are re-examined using
    value-fingerprint inference (infer_columns_from_values).
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

    doc_info = _extract_metadata(raw_rows[:best_idx])

    # ── Value-fingerprint inference ────────────────────────────────────────
    # Pass the raw data rows (below header) so we can inspect actual values
    raw_data_rows = raw_rows[best_idx + 1:]
    header_index_map = infer_columns_from_values(header_index_map, raw_data_rows)

    # ── Extract structured data rows ───────────────────────────────────────
    data_rows: list[dict[str, Any]] = []
    total_amount: float | None = None

    for row in raw_data_rows:
        if not any(v not in (None, "") for v in row):
            continue

        item = {
            header: clean_cell(row[idx] if idx < len(row) else None)
            for header, idx in header_index_map.items()
        }

        if is_total_row(item):
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
