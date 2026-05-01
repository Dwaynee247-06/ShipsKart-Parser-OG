
import re
from io import BytesIO
from openpyxl import load_workbook

HEADER_ALIASES = {
    "sr no": "sr_no",
    "sr. no.": "sr_no",
    "sr.no.": "sr_no",
    "s no": "sr_no",
    "s.no": "sr_no",
    "sno": "sr_no",
    "no": "sr_no",

    "items": "items",
    "item": "items",
    "product": "items",
    "product name": "items",
    "part details": "items",
    "description": "items",
    "name": "items",
    "material": "items",

    "unit": "unit_of_measurement",
    "units": "unit_of_measurement",
    "uom": "unit_of_measurement",
    "unit of": "unit_of_measurement",
    "unit of measurement": "unit_of_measurement",

    "qty": "quantity",
    "quantity": "quantity",
    "qty req": "quantity",
    "qty required": "quantity",
    "required qty": "quantity",
    "req qty": "quantity",
    "ordered qty": "quantity",

    "rob": "rob",

    "rate": "rate",
    "unit price": "unit_price",
    "price": "rate",

    "gst": "gst",
    "tax": "gst",
    "vat": "gst",

    "amount": "amount",
    "amt" : "amount",
    "total": "amount",
    "total price": "amount",
    "total amount": "amount",
    "net amount": "amount",

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

    "make req": "make_req",
    "make": "make_req",
    "brand": "make_req",
    "make required": "make_req",

    "remarks": "remarks",
    "remark": "remarks",
    "purchase remark": "purchase_remark",
    "purchase reamrk": "purchase_remark",
    "purchase remarks": "purchase_remark",
    "technical remark": "technical_remark",
    "vessel remarks": "vessel_remarks",
    "vessel remark": "vessel_remarks",
    "notes": "remarks",

    "last supplied date and qty": "last_supplied_date_qty",
    "last supplied": "last_supplied_date_qty",
    "last 3 months consumptions": "last_3_months_consumptions",

    "ref request no": "ref_request_no",
    "vessel": "vessel",
    "department": "department",
    "port": "port",
}

EXPECTED_HEADERS = {
    "sr_no", "items", "unit_of_measurement", "quantity", "category",
    "skrt_code", "rate", "gst", "amount", "remarks", "part_no_impa_code",
    "rob", "make_req", "purchase_remark", "unit_price", "technical_remark",
    "vessel_remarks",
}


def _normalize_header(value):
    if value is None:
        return ""
    text = str(value).strip().lower()
    text = text.replace("\n", " ")
    text = re.sub(r"[\/\\\-]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if text in HEADER_ALIASES:
        return HEADER_ALIASES[text]
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def _cell_value(v):
    if v is None or (isinstance(v, str) and v.strip() == ""):
        return None
    return v


def _score_header_row(row_values):
    normalized = [_normalize_header(v) for v in row_values]
    unique_non_empty = {x for x in normalized if x}
    score = len(unique_non_empty & EXPECTED_HEADERS)
    return score, normalized


def _find_best_header_row(ws, max_scan_rows=40):
    best_row_idx = None
    best_score = 0
    best_headers = None

    for row_idx, row in enumerate(
        ws.iter_rows(min_row=1, max_row=max_scan_rows, values_only=True), start=1
    ):
        score, headers = _score_header_row(row)
        if score > best_score:
            best_score = score
            best_row_idx = row_idx
            best_headers = headers

    if best_row_idx is None or best_score < 3:
        return None, None

    return best_row_idx, best_headers


def _is_section_heading(item):
    filled = [v for v in item.values() if v not in (None, "")]
    if len(filled) == 1:
        only_value = str(filled[0]).strip()
        return len(only_value) > 3 and only_value.replace(" ", "").isupper()
    return False


def _extract_metadata_above(ws, header_row_idx):
    metadata = {}
    for row in ws.iter_rows(min_row=1, max_row=header_row_idx - 1, values_only=True):
        values = [v for v in row if v not in (None, "")]
        if len(values) == 2:
            key = _normalize_header(values[0])
            metadata[key] = _cell_value(values[1])
    return metadata


def parse_excel(file_bytes: bytes) -> dict:
    wb = load_workbook(BytesIO(file_bytes), data_only=True)
    result = {}

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]

        header_row_idx, normalized_headers = _find_best_header_row(ws)

        if header_row_idx is None:
            for row_idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
                if any(v not in (None, "") for v in row):
                    header_row_idx = row_idx
                    normalized_headers = [_normalize_header(v) for v in row]
                    break

        if header_row_idx is None:
            continue

        header_index_map = {}
        for idx, h in enumerate(normalized_headers):
            if h and h not in header_index_map:
                header_index_map[h] = idx

        doc_info = _extract_metadata_above(ws, header_row_idx)

        rows_data = []
        for row in ws.iter_rows(min_row=header_row_idx + 1, values_only=True):
            if not any(v not in (None, "") for v in row):
                continue

            item = {}
            for header, idx in header_index_map.items():
                item[header] = _cell_value(row[idx] if idx < len(row) else None)

            if _is_section_heading(item):
                continue

            primary_keys = {"items", "part_no_impa_code", "sr_no"}
            if not any(item.get(k) for k in primary_keys):
                continue

            rows_data.append(item)

        result[sheet_name] = {
            "document_info": doc_info,
            "headers": list(header_index_map.keys()),
            "rows": rows_data,
        }

    return result